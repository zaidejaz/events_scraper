import os
from .models.database import db

def reset_database(app):
    """Utility function to reset the database"""
    with app.app_context():
        # Get the database file path
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        
        # Remove the database file if it exists
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"Removed existing database: {db_path}")
        
        # Create all tables
        db.create_all()
        print("Created new database with updated schema")