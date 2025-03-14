from datetime import datetime
from io import StringIO
from flask import Blueprint, jsonify, redirect, request, render_template, current_app, url_for, make_response
from flask_login import login_required
from werkzeug.utils import secure_filename
import csv
import os
from ..models.database import db, Event
from ..constants import CITY_URL_MAP

bp = Blueprint('events', __name__)

def get_city_id_by_name(city_name):
    """Get city ID from city name"""
    return CITY_URL_MAP.get(city_name.strip())

def get_city_name_by_id(city_id):
    """Get city name from city ID"""
    for city_name, cid in CITY_URL_MAP.items():
        if cid == city_id:
            return city_name
    return None

def get_city_name(event):
    """Get city name from event, handling both mapped and custom cities"""
    if event.custom_city:
        return event.custom_city
    return get_city_name_by_id(event.city_id)

@bp.route('/')
@login_required
def index():
    return redirect(url_for('events.events_page'))

@bp.route('/events', methods=['GET'])
@login_required
def events_page():
    events = Event.query.all()
    # Create a reverse mapping for display purposes
    city_names = {cid: name for name, cid in CITY_URL_MAP.items()}
    return render_template('events.html', events=events, cities=CITY_URL_MAP, city_names=city_names)

@bp.route('/api/events', methods=['GET'])
@login_required
def get_events():
    events = Event.query.all()
    return jsonify([event.to_dict() for event in events])

@bp.route('/api/events', methods=['POST'])
@login_required
def create_event():
    try:
        data = request.json
        # Validate city_id
        city_id = int(data['city_id'])
        if city_id not in [cid for cid in CITY_URL_MAP.values()]:
            return jsonify({'error': 'Invalid city ID'}), 400

        # Validate in_hand value
        in_hand = data.get('in_hand', 'N').strip().upper()
        if in_hand not in ['Y', 'N']:
            return jsonify({'error': 'Invalid in_hand value. Use Y or N'}), 400

        event = Event(
            website=data['website'],
            event_id=data['event_id'],
            todaytix_event_id=data.get('todaytix_event_id'),
            todaytix_show_id=data.get('todaytix_show_id'),
            ticketmaster_id=data.get('ticketmaster_id'),
            event_name=data['event_name'],
            city_id=city_id,
            event_date=datetime.strptime(data['event_date'], '%Y-%m-%d').date(),
            event_time=data['event_time'],
            venue_name=data.get('venue_name'),
            markup=float(data['markup']),
            stock_type=data.get('stock_type'),
            in_hand=in_hand,
            in_hand_date=datetime.strptime(data['in_hand_date'], '%Y-%m-%d').date() if data.get('in_hand_date') else None,
            double_check=data.get('double_check', False),
            internal_notes=data.get('internal_notes'),
            first_scrape_completed=False
        )
        db.session.add(event)
        db.session.commit()
        return jsonify(event.to_dict()), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/events/<int:id>', methods=['GET'])
@login_required
def get_event(id):
    try:
        current_app.logger.info(f"Fetching event with ID: {id}")
        event = Event.query.get_or_404(id)
        current_app.logger.info(f"Found event: {event.event_name}")
        return jsonify(event.to_dict())
    except Exception as e:
        current_app.logger.error(f"Error fetching event {id}: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
@bp.route('/api/events/<int:id>', methods=['PUT'])
@login_required
def update_event(id):
    try:
        event = Event.query.get_or_404(id)
        data = request.json
        
        # Validate city_id
        city_id = int(data['city_id'])
        if city_id not in [cid for cid in CITY_URL_MAP.values()]:
            return jsonify({'error': 'Invalid city ID'}), 400

        # Validate in_hand value
        in_hand = data.get('in_hand', 'N').strip().upper()
        if in_hand not in ['Y', 'N']:
            return jsonify({'error': 'Invalid in_hand value. Use Y or N'}), 400

        event.website = data['website']
        event.event_id = data['event_id']
        event.todaytix_event_id = data.get('todaytix_event_id')
        event.todaytix_show_id = data.get('todaytix_show_id')
        event.ticketmaster_id = data.get('ticketmaster_id')
        event.event_name = data['event_name']
        event.city_id = city_id
        event.event_date = datetime.strptime(data['event_date'], '%Y-%m-%d').date()
        event.event_time = data['event_time']
        event.venue_name = data.get('venue_name')
        event.markup = float(data['markup'])
        event.stock_type = data.get('stock_type')
        event.in_hand = in_hand
        event.in_hand_date = datetime.strptime(data['in_hand_date'], '%Y-%m-%d').date() if data.get('in_hand_date') else None
        event.double_check = data.get('double_check', False)
        event.internal_notes = data.get('internal_notes')
        
        db.session.commit()
        return jsonify(event.to_dict())
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/events/<int:id>', methods=['DELETE'])
@login_required
def delete_event(id):
    event = Event.query.get_or_404(id)
    db.session.delete(event)
    db.session.commit()
    return '', 204

    
@bp.route('/api/events/template', methods=['GET'])
@login_required
def download_template():
    # Create a string buffer to write CSV data
    si = StringIO()
    writer = csv.writer(si)
    
    # Write headers
    writer.writerow([
        'website', 'event_id', 'event_name', 'city',
        'event_date', 'event_time', 'todaytix_event_id',
        'todaytix_show_id', 'ticketmaster_id', 'venue_name', 'markup',
        'stock_type', 'in_hand', 'in_hand_date', 'double_check', 'internal_notes'
    ])
    
    # Write sample rows
    writer.writerow([
        'TodayTix', 'EVT_001', 'Sample Event', 'New York',
        '2024-01-01', '19:30', '123456', '789', '', 'Sample Theater', '1.6',
        'ELECTRONIC', 'N', '2025-02-12', 'No', 'Sample notes'
    ])
    
    writer.writerow([
        'TicketMaster', 'EVT_002', 'Sample Event 2', 'New York',
        '2024-01-01', '19:30', '', '', 'TM123456', 'Sample Theater', '1.6',
        'ELECTRONIC', 'N', '2025-02-12', 'Yes', 'Double check needed'
    ])
    
    # Create the response
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=events_template.csv"
    output.headers["Content-type"] = "text/csv"
    return output


@bp.route('/api/events/import', methods=['POST'])
@login_required
def import_events():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'Only CSV files are allowed'}), 400
    
    try:
        filename = secure_filename(file.filename)
        temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        file.save(temp_path)
        
        imported_count = 0
        skipped_count = 0
        errors = []
        
        with open(temp_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row_num, row in enumerate(reader, start=2):
                try:
                    # Check if event already exists
                    existing_event = Event.query.filter_by(event_id=row['event_id'].strip()).first()
                    if existing_event:
                        skipped_count += 1
                        continue
                        
                    city_name = row['city'].strip()
                    city_id = get_city_id_by_name(city_name)
                    
                    # Parse dates
                    in_hand_date = None
                    if row.get('in_hand_date') and row['in_hand_date'].strip():
                        try:
                            in_hand_date = datetime.strptime(row['in_hand_date'].strip(), '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Row {row_num}: Invalid in_hand_date format. Use YYYY-MM-DD")
                            continue

                    # Validate in_hand value
                    in_hand = row.get('in_hand', '').strip().upper()
                    if in_hand and in_hand not in ['Y', 'N']:
                        errors.append(f"Row {row_num}: Invalid in_hand value. Use 'Y' or 'N'")
                        continue

                    event = Event(
                        website=row['website'].strip(),
                        event_id=row['event_id'].strip(),
                        todaytix_event_id=row['todaytix_event_id'].strip() if row.get('todaytix_event_id') else None,
                        todaytix_show_id=row['todaytix_show_id'].strip() if row.get('todaytix_show_id') else None,
                        ticketmaster_id=row['ticketmaster_id'].strip() if row.get('ticketmaster_id') else None,
                        event_name=row['event_name'].strip(),
                        city_id=city_id,  # This will be None for unmapped cities
                        custom_city=None if city_id else city_name,  # Store custom city name if not mapped
                        event_date=datetime.strptime(row['event_date'].strip(), '%Y-%m-%d').date(),
                        event_time=row['event_time'].strip(),
                        venue_name=row['venue_name'].strip() if row.get('venue_name') else None,
                        markup=float(row['markup'].strip()),
                        stock_type=row['stock_type'].strip() if row.get('stock_type') else None,
                        in_hand=in_hand or 'N',
                        in_hand_date=in_hand_date,
                        double_check=row.get('double_check', '').strip().lower() == 'yes',
                        internal_notes=row.get('internal_notes', '').strip(),
                        first_scrape_completed=False
                    )
                    
                    db.session.add(event)
                    imported_count += 1
                    
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
                    continue
            
            if imported_count > 0:
                db.session.commit()
        
        os.remove(temp_path)
        
        response = {
            'success': True,
            'imported_count': imported_count,
            'skipped_count': skipped_count,
            'errors': errors
        }
        
        if errors:
            response['status'] = 'partial'
        else:
            response['status'] = 'success'
            
        return jsonify(response)
        
    except Exception as e:
        if 'temp_path' in locals():
            os.remove(temp_path)
        return jsonify({'error': str(e)}), 500
    
@bp.route('/api/events/export', methods=['GET'])
@login_required
def export_events():
    try:
        events = Event.query.all()
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow([
            'website', 'event_id', 'event_name', 'city', 
            'event_date', 'event_time', 'todaytix_event_id', 
            'todaytix_show_id', 'ticketmaster_id', 'venue_name', 'markup',
            'stock_type', 'in_hand', 'in_hand_date'
        ])
        
        # Write data
        for event in events:
            city_name = get_city_name(event)  # Use the new function
            writer.writerow([
                event.website,
                event.event_id,
                event.event_name,
                city_name,
                event.event_date.strftime('%Y-%m-%d'),
                event.event_time,
                event.todaytix_event_id or '',
                event.todaytix_show_id or '',
                event.ticketmaster_id or '',
                event.venue_name or '',
                f"{event.markup:.2f}",
                event.stock_type or '',
                event.in_hand or 'N',
                event.in_hand_date.strftime('%Y-%m-%d') if event.in_hand_date else '',
                'Yes' if event.double_check else 'No',
                event.internal_notes or ''
            ])
        
        output.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'events_export_{timestamp}.csv'
        
        return current_app.response_class(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "text/csv; charset=utf-8"
            }
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@bp.route('/api/events/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_events():
    try:
        data = request.json
        if not data or 'ids' not in data:
            return jsonify({'error': 'No event IDs provided'}), 400
            
        event_ids = data['ids']
        if not event_ids:
            return jsonify({'error': 'Empty ID list'}), 400
            
        # Query all events at once
        events = Event.query.filter(Event.id.in_(event_ids)).all()
        
        # Delete all events
        for event in events:
            db.session.delete(event)
            
        db.session.commit()
        return jsonify({'success': True, 'count': len(events)}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500