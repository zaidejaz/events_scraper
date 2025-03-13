from datetime import timedelta
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_FILE = os.path.join(BASE_DIR, 'todaytix.db')

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///todaytix.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    OUTPUT_FILE_DIR = os.getenv('OUTPUT_FILE_DIR', 'data/output')
    STORE_API_BASE_URL = os.getenv('STORE_API_BASE_URL', '')
    STORE_API_KEY = os.getenv('STORE_API_KEY')
    COMPANY_ID = os.getenv('COMPANY_ID')
    PROXY_API_URL = os.getenv('PROXY_API_URL')
    PROXY_API_KEY = os.getenv('PROXY_API_KEY')
    MAX_CONCURRENT_REQUESTS = int(os.getenv('MAX_CONCURRENT_REQUESTS', '5'))
    SCHEDULER_API_ENABLED = True
    AUTH_USERNAME = os.getenv('AUTH_USERNAME')
    AUTH_PASSWORD = os.getenv('AUTH_PASSWORD')
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)  # Session lifetime
    SESSION_COOKIE_NAME = 'todaytix_session'
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'  
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'