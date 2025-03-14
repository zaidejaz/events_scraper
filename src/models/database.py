from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from datetime import datetime, timedelta
import json

db = SQLAlchemy()

class Event(db.Model):
    __tablename__ = 'events'
    
    id = db.Column(db.Integer, primary_key=True)
    website = db.Column(db.String(255), nullable=False)
    event_id = db.Column(db.String(255), nullable=False, unique=True)
    todaytix_event_id = db.Column(db.String(255), nullable=True)
    todaytix_show_id = db.Column(db.String(255), nullable=True)
    ticketmaster_id = db.Column(db.String(255), nullable=True) 
    event_name = db.Column(db.String(255), nullable=False)
    city_id = db.Column(db.Integer, nullable=True)
    custom_city = db.Column(db.String(100), nullable=True)
    event_date = db.Column(db.Date, nullable=False)
    event_time = db.Column(db.String(50), nullable=False)
    venue_name = db.Column(db.String(255), nullable=True)
    markup = db.Column(db.Float, nullable=False, default=1.6)
    stock_type = db.Column(db.String(50), nullable=True) 
    in_hand_date = db.Column(db.Date, nullable=True)   
    in_hand = db.Column(db.String(25), nullable=True)
    internal_notes = db.Column(db.Text, nullable=True)
    double_check = db.Column(db.Boolean, default=False)
    first_scrape_completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        from ..constants import CITY_URL_MAP
        city_name = None
        for city, cid in CITY_URL_MAP.items():
            if cid == self.city_id:
                city_name = city
                break

        result = {
            'id': self.id,
            'website': self.website,
            'event_id': self.event_id,
            'todaytix_event_id': self.todaytix_event_id,
            'todaytix_show_id': self.todaytix_show_id,
            'event_name': self.event_name,
            'city_id': self.city_id,
            'city': city_name or 'Unknown',
            'event_date': self.event_date.isoformat() if self.event_date else None,
            'event_time': self.event_time,
            'venue_name': self.venue_name,
            'markup': self.markup,
            'stock_type': self.stock_type,
            'in_hand_date': self.in_hand_date.isoformat() if self.in_hand_date else None,
            'in_hand': self.in_hand,
            'internal_notes': self.internal_notes,
            'double_check': self.double_check,
            'first_scrape_completed': self.first_scrape_completed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

        result['rules'] = [rule.to_dict() for rule in self.rules]
        return result

    @property
    def city_name(self):
        """Helper property to get city name directly"""
        from ..constants import CITY_URL_MAP
        for city, cid in CITY_URL_MAP.items():
            if cid == self.city_id:
                return city
        return 'Unknown'
    
class ScraperJob(db.Model):
    __tablename__ = 'scraper_jobs'
    
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(50), nullable=False)
    interval_minutes = db.Column(db.Integer, nullable=False)
    concurrent_requests = db.Column(db.Integer, nullable=False, default=5)
    auto_upload = db.Column(db.Boolean, nullable=False, default=False)  
    last_run = db.Column(db.DateTime)
    next_run = db.Column(db.DateTime)
    events_processed = db.Column(db.Integer, default=0)
    total_tickets_found = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())
    
    def to_dict(self):
        return {
            'id': self.id,
            'status': self.status,
            'interval_minutes': self.interval_minutes,
            'concurrent_requests': self.concurrent_requests,
            'auto_upload': self.auto_upload,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'next_run': self.next_run.isoformat() if self.next_run else None,
            'events_processed': self.events_processed,
            'total_tickets_found': self.total_tickets_found,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
class EventRule(db.Model):
    __tablename__ = 'event_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    rule_type = db.Column(db.String(50), nullable=False)
    keyword = db.Column(db.String(100), nullable=False)  
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())
    
    event = db.relationship('Event', backref=db.backref('rules', cascade='all, delete-orphan'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'event_id': self.event_id,
            'rule_type': self.rule_type,
            'keyword': self.keyword,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
class VenueMapping(db.Model):
    __tablename__ = 'venue_mappings'
    
    id = db.Column(db.Integer, primary_key=True)
    event_name = db.Column(db.String(255), nullable=False)
    venue_name = db.Column(db.String(255), nullable=False)
    section = db.Column(db.String(255), nullable=False)
    row = db.Column(db.String(50), nullable=False)
    seats = db.Column(db.String(255), nullable=False)  # Comma-separated list of seats
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())
    
    def to_dict(self):
        return {
            'id': self.id,
            'event_name': self.event_name,
            'venue_name': self.venue_name,
            'section': self.section,
            'row': self.row,
            'seats': self.seats.split(','),  # Convert to list
            'active': self.active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @staticmethod
    def get_excluded_seats(event_name: str, venue_name: str):
        """Get all excluded seats for a specific event and venue"""
        mappings = VenueMapping.query.filter_by(
            event_name=event_name,
            venue_name=venue_name,
            active=True
        ).all()
        
        excluded_seats = {}
        for mapping in mappings:
            key = f"{mapping.section}_{mapping.row}"
            if key not in excluded_seats:
                excluded_seats[key] = set()
            excluded_seats[key].update(seat.strip() for seat in mapping.seats.split(','))
        
        return excluded_seats
        
class TicketmasterHeader(db.Model):
    __tablename__ = 'ticketmaster_headers'
    
    id = db.Column(db.Integer, primary_key=True)
    headers = db.Column(db.Text, nullable=False)  # JSON string of headers
    created_at = db.Column(db.DateTime, server_default=func.now())
    last_used = db.Column(db.DateTime, nullable=True)
    failures = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    
    def __init__(self, headers_dict):
        self.headers = json.dumps(headers_dict)
        self.failures = 0
        self.is_active = True
        
    @property
    def headers_dict(self):
        return json.loads(self.headers)
        
    def mark_used(self):
        self.last_used = datetime.now()
        db.session.commit()
        
    def mark_failure(self):
        self.failures += 1
        if self.failures >= 3:
            self.is_active = False
        db.session.commit()
        
    @classmethod
    def get_active_headers(cls):
        """Get all active headers less than 24 hours old"""
        expiry_time = datetime.now() - timedelta(hours=24)
        return cls.query.filter(
            cls.is_active == True,
            cls.created_at > expiry_time,
            cls.headers.like('%Cookie%')
        ).order_by(cls.last_used.asc().nullsfirst()).all()