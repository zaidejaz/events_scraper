import json
import requests
import logging
import threading
import time
from datetime import datetime, timedelta
from ..models.database import db, TicketmasterHeader
import os
import random

logger = logging.getLogger(__name__)

class HeaderService:
    _instance = None
    _initialized = False
    _lock = threading.Lock()  
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(HeaderService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, api_url=None, api_key=None):
        if self._initialized:
            return
            
        self.api_url = api_url or os.getenv('HEADER_FETCHER_API_URL')
        self.api_key = api_key or os.getenv('HEADER_FETCHER_API_KEY')
        self.min_headers = int(os.getenv('MIN_HEADERS', '20'))
        self.refresh_threshold = int(os.getenv('REFRESH_THRESHOLD', '10'))
        self.check_interval = int(os.getenv('CHECK_INTERVAL', '300'))  # 5 minutes
        self._stop_event = threading.Event()
        self._thread = None
        self._initialized = True
        
    def fetch_new_header(self):
        """Fetch a new header from the API and store it in the database"""
        # First, check if we already have enough headers to avoid duplicate fetching
        with self._lock:
            active_count = self._count_active_headers()
            if active_count >= self.min_headers:
                logger.info(f"Already have {active_count} headers, skipping fetch")
                return None
        
        try:
            if not self.api_url or not self.api_key:
                logger.error("Header fetcher API URL or key not configured")
                return None
                
            response = requests.get(
                f"{self.api_url}/api/headers",
                headers={"X-API-Key": self.api_key},
                timeout=120
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch header: {response.status_code} - {response.text}")
                return None
                
            data = response.json()
            if not data.get("success"):
                logger.error(f"API returned error: {data.get('error')}")
                return None
                
            headers_dict = data.get("headers", {})
            
            # Check if the header contains a cookie
            if "Cookie" not in headers_dict or not headers_dict["Cookie"]:
                logger.warning("Fetched header doesn't contain a cookie, skipping")
                return None
            
            # Check if this header cookie already exists in the database
            cookie = headers_dict.get("Cookie", "")
            with self._lock:
                existing = TicketmasterHeader.query.filter(
                    TicketmasterHeader.headers.like(f'%{cookie}%')
                ).first()
                
                if existing:
                    logger.info(f"Header with this cookie already exists, skipping")
                    return existing
                
                # Store in database
                header = TicketmasterHeader(headers_dict)
                db.session.add(header)
                db.session.commit()
                
                logger.info(f"Added new header with ID {header.id}")
                return header
                
        except Exception as e:
            logger.error(f"Error fetching header: {str(e)}")
            return None
    
    def _count_active_headers(self):
        """Count active, non-expired headers"""
        expiry_time = datetime.now() - timedelta(hours=24)
        return TicketmasterHeader.query.filter(
            TicketmasterHeader.is_active == True,
            TicketmasterHeader.headers.like('%Cookie%'),
            TicketmasterHeader.created_at >= expiry_time
        ).count()
            
    def get_all_active_headers(self):
        """Get all active headers from the database"""
        headers = TicketmasterHeader.get_active_headers()
        
        # Only fetch more if we have ZERO headers
        if len(headers) == 0:
            logger.warning("No active headers found, fetching new ones")
            for _ in range(3):  # Fetch just a few to get things working
                with self._lock:
                    new_header = self.fetch_new_header()
                    if new_header:
                        headers.append(new_header)
                        
        return [h.headers_dict for h in headers]
        
    def cleanup_expired_headers(self):
        """Remove expired headers from the database"""
        with self._lock:
            expiry_time = datetime.now() - timedelta(hours=24)
            expired = TicketmasterHeader.query.filter(
                TicketmasterHeader.created_at < expiry_time
            ).all()
            
            for header in expired:
                db.session.delete(header)
                
            db.session.commit()
            return len(expired)
    
    def start_background_task(self):
        """Start background task to maintain headers"""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Background task already running")
            return
            
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._maintain_headers)
        self._thread.daemon = True
        self._thread.start()
        logger.info("Started background header maintenance task")
    
    def stop_background_task(self):
        """Stop the background task"""
        if self._thread is None or not self._thread.is_alive():
            return
            
        self._stop_event.set()
        self._thread.join(timeout=10)
        self._thread = None
        logger.info("Stopped background header maintenance task")
    
    def _maintain_headers(self):
        """Background task to maintain header pool"""
        logger.info("Header maintenance task started")
        
        # Add initial random delay to stagger worker startups
        time.sleep(random.uniform(1, 30))
        
        while not self._stop_event.is_set():
            try:
                # Add a lock to prevent race conditions
                with self._lock:
                    # Clean up expired headers
                    cleaned = self.cleanup_expired_headers()
                    if cleaned > 0:
                        logger.info(f"Cleaned up {cleaned} expired headers")
                    
                    # Count active headers
                    active_count = self._count_active_headers()
                    
                    logger.info(f"Active headers: {active_count}/{self.min_headers}")
                    
                    # Fetch more if below threshold
                    if active_count < self.refresh_threshold:
                        needed = self.min_headers - active_count
                        logger.info(f"Fetching {needed} new headers")
                        
                        # Wait a short random time to reduce chance of workers colliding
                        time.sleep(random.uniform(0, 3))
                        
                        success_count = 0
                        for _ in range(needed):
                            # Recheck count after each fetch to avoid overfetching
                            current_count = self._count_active_headers()
                            if current_count >= self.min_headers:
                                logger.info("Reached target header count, stopping fetch")
                                break
                                
                            header = self.fetch_new_header()
                            if header:
                                success_count += 1
                                
                            # Small delay to avoid overwhelming the API
                            time.sleep(2)
                            
                        logger.info(f"Added {success_count} new headers")
            
            except Exception as e:
                logger.error(f"Error in header maintenance task: {str(e)}")
            
            # Add some jitter to the sleep interval
            jitter = random.uniform(0, 30)  # Up to 30 seconds of jitter
            sleep_time = self.check_interval + jitter
            logger.debug(f"Sleeping for {sleep_time} seconds")
            
            # Sleep until next check
            self._stop_event.wait(sleep_time)