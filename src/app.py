import time
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
    scheduler.start()
    logger.info("APScheduler started")
    
    # Initialize header service
    with app.app_context():
        from .services.header_service import HeaderService
        header_service = HeaderService()
        header_service.start_background_task()
        logger.info("Header service background task started")
    
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