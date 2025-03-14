import json
import requests
import logging
import threading
import time
from datetime import datetime, timedelta
from ..models.database import db, TicketmasterHeader
import os

logger = logging.getLogger(__name__)

class HeaderService:
    _instance = None
    _initialized = False
    
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
                
            # Store in database
            header = TicketmasterHeader(headers_dict)
            db.session.add(header)
            db.session.commit()
            
            logger.info(f"Added new header with ID {header.id}")
            return header
                
        except Exception as e:
            logger.error(f"Error fetching header: {str(e)}")
            return None
            
    def get_all_active_headers(self):
        """Get all active headers from the database"""
        headers = TicketmasterHeader.get_active_headers()
        
        # If we don't have enough active headers, fetch more
        if len(headers) < 5:
            logger.info(f"Only {len(headers)} active headers found, fetching more")
            for _ in range(5 - len(headers)):
                new_header = self.fetch_new_header()
                if new_header:
                    headers.append(new_header)
                    
        return [h.headers_dict for h in headers]
        
    def cleanup_expired_headers(self):
        """Remove expired headers from the database"""
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
        
        while not self._stop_event.is_set():
            try:
                # Clean up expired headers
                cleaned = self.cleanup_expired_headers()
                if cleaned > 0:
                    logger.info(f"Cleaned up {cleaned} expired headers")
                
                # Count active headers
                active_count = TicketmasterHeader.query.filter(
                    TicketmasterHeader.is_active == True,
                    TicketmasterHeader.headers.like('%Cookie%'),
                    TicketmasterHeader.created_at > (datetime.now() - timedelta(hours=24))
                ).count()
                
                logger.info(f"Active headers: {active_count}/{self.min_headers}")
                
                # Fetch more if below threshold
                if active_count < self.refresh_threshold:
                    needed = self.min_headers - active_count
                    logger.info(f"Fetching {needed} new headers")
                    
                    for _ in range(needed):
                        self.fetch_new_header()
                        # Small delay to avoid overwhelming the API
                        time.sleep(2)
            
            except Exception as e:
                logger.error(f"Error in header maintenance task: {str(e)}")
            
            # Sleep until next check
            time.sleep(self.check_interval)