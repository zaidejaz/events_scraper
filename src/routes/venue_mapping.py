from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required
from ..models.database import db, VenueMapping, Event

bp = Blueprint('mappings', __name__)

@bp.route('/venue-mappings')
@login_required
def mappings_page():
    # Get unique event names and venue names for dropdowns
    events = Event.query.with_entities(Event.event_name).distinct().all()
    event_names = sorted([event[0] for event in events])
    
    venue_names = Event.query.with_entities(Event.venue_name).distinct().all()
    venue_names = sorted([venue[0] for venue in venue_names if venue[0]])
    
    return render_template('venue_mapping.html', 
                         event_names=event_names,
                         venue_names=venue_names)

@bp.route('/api/venue-mappings', methods=['GET'])
@login_required
def get_mappings():
    event_name = request.args.get('event_name')
    venue_name = request.args.get('venue_name')
    
    query = VenueMapping.query
    
    if event_name:
        query = query.filter_by(event_name=event_name)
    if venue_name:
        query = query.filter_by(venue_name=venue_name)
        
    mappings = query.order_by(VenueMapping.created_at.desc()).all()
    return jsonify([mapping.to_dict() for mapping in mappings])

@bp.route('/api/venue-mappings/<int:id>', methods=['GET'])
@login_required
def get_mapping(id):
    mapping = VenueMapping.query.get_or_404(id)
    return jsonify(mapping.to_dict())

@bp.route('/api/venue-mappings', methods=['POST'])
@login_required
def create_mapping():
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['event_name', 'venue_name', 'section', 'row', 'seats']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Clean and validate seats format
        seats = [seat.strip() for seat in data['seats'].split(',') if seat.strip()]
        if not seats:
            return jsonify({'error': 'No valid seats provided'}), 400
            
        mapping = VenueMapping(
            event_name=data['event_name'],
            venue_name=data['venue_name'],
            section=data['section'],
            row=data['row'],
            seats=','.join(seats),
            active=data.get('active', True)
        )
        
        db.session.add(mapping)
        db.session.commit()
        
        return jsonify(mapping.to_dict()), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/venue-mappings/<int:id>', methods=['PUT'])
@login_required
def update_mapping(id):
    try:
        mapping = VenueMapping.query.get_or_404(id)
        data = request.json
        
        if 'event_name' in data:
            mapping.event_name = data['event_name']
        if 'venue_name' in data:
            mapping.venue_name = data['venue_name']
        if 'section' in data:
            mapping.section = data['section']
        if 'row' in data:
            mapping.row = data['row']
        if 'seats' in data:
            seats = [seat.strip() for seat in data['seats'].split(',') if seat.strip()]
            if not seats:
                return jsonify({'error': 'No valid seats provided'}), 400
            mapping.seats = ','.join(seats)
        if 'active' in data:
            mapping.active = data['active']
            
        db.session.commit()
        return jsonify(mapping.to_dict())
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/venue-mappings/<int:id>', methods=['DELETE'])
@login_required
def delete_mapping(id):
    try:
        mapping = VenueMapping.query.get_or_404(id)
        db.session.delete(mapping)
        db.session.commit()
        return '', 204
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/venue-mappings/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_mappings():
    try:
        data = request.json
        if not data or 'ids' not in data:
            return jsonify({'error': 'No mapping IDs provided'}), 400
            
        VenueMapping.query.filter(VenueMapping.id.in_(data['ids'])).delete(synchronize_session=False)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500