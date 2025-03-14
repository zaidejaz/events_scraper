from flask import Flask
from src.routes import todaytix_events, upload
from .config import Config
from .models.database import db, Event
from .routes import events, scraper
from .constants import CITY_URL_MAP
from .scraper.scheduler import scheduler
from .routes.auth import auth_bp, login_manager
from .routes.rules import rules_bp
from .routes.venue_mapping import bp as venue_mapping_bp
from .routes.ticketmaster_events import bp as ticketmaster_events_bp
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = app.config['SECRET_KEY']

    # Enable session protection
    app.config['SESSION_COOKIE_SECURE'] = Config.SESSION_COOKIE_SECURE
    app.config['SESSION_COOKIE_HTTPONLY'] = Config.SESSION_COOKIE_HTTPONLY
    app.config['SESSION_COOKIE_SAMESITE'] = Config.SESSION_COOKIE_SAMESITE
    app.config['PERMANENT_SESSION_LIFETIME'] = Config.PERMANENT_SESSION_LIFETIME
    
    db.init_app(app)
    
    # Configure APScheduler
    app.config['SCHEDULER_API_ENABLED'] = True
    scheduler.init_app(app)
    
    # Define header refresh job function
    def refresh_ticketmaster_headers():
        try:
            from .services.header_service import HeaderService
            from .models.database import TicketmasterHeader
            
            logger.info("Running scheduled Ticketmaster header refresh")
            with app.app_context():
                header_service = HeaderService()
                
                # Get counts of headers
                expiry_time = datetime.now() - timedelta(hours=24)
                
                # Count expired headers (older than 24 hours)
                expired_count = TicketmasterHeader.query.filter(
                    TicketmasterHeader.created_at < expiry_time
                ).count()
                
                # Count active, non-expired headers
                active_count = TicketmasterHeader.query.filter(
                    TicketmasterHeader.is_active == True,
                    TicketmasterHeader.created_at >= expiry_time,
                    TicketmasterHeader.headers.like('%Cookie%')
                ).count()
                
                min_headers = int(app.config.get('HEADER_MIN_COUNT', 20))
                
                # First, clean up expired headers
                if expired_count > 0:
                    logger.info(f"Cleaning up {expired_count} expired headers")
                    header_service.cleanup_expired_headers()
                
                # Then, check if we need to fetch new headers
                headers_needed = min_headers - active_count
                
                if headers_needed > 0:
                    logger.info(f"Need {headers_needed} more headers to reach minimum of {min_headers}")
                    
                    success_count = 0
                    for _ in range(headers_needed):
                        header = header_service.fetch_new_header()
                        if header:
                            success_count += 1
                    
                    logger.info(f"Successfully fetched {success_count} new headers")
                else:
                    logger.info(f"Currently have {active_count} active headers, no refresh needed")
        except Exception as e:
            logger.error(f"Error in header refresh job: {str(e)}")
    
    # Add job to scheduler - run every 100 minutes
    scheduler.add_job(
        id='refresh_ticketmaster_headers',
        func=refresh_ticketmaster_headers,
        trigger='interval',
        minutes=100,
        replace_existing=True
    )
    
    # Also run immediately upon startup
    scheduler.add_job(
        id='initial_headers_refresh',
        func=refresh_ticketmaster_headers,
        trigger='date',
        run_date=datetime.now() + timedelta(seconds=15), 
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("APScheduler started with Ticketmaster header refresh jobs")
    
    # Initialize Flask-Login
    login_manager.init_app(app)

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(events.bp)
    app.register_blueprint(scraper.bp)
    app.register_blueprint(upload.bp)
    app.register_blueprint(todaytix_events.bp)
    app.register_blueprint(rules_bp)
    app.register_blueprint(venue_mapping_bp)
    app.register_blueprint(ticketmaster_events_bp)

    with app.app_context():
        db.create_all()
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5001)