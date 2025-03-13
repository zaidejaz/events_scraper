from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash

from src.constants import CITY_URL_MAP
from ..models.database import db, Event, EventRule
from flask_login import login_required

rules_bp = Blueprint('rules', __name__)

VALID_RULE_TYPES = ['even', 'odd', 'consecutive']
RULE_DESCRIPTIONS = {
    'even': 'Keyword for selecting even-numbered seats',
    'odd': 'Keyword for selecting odd-numbered seats',
    'consecutive': 'Keyword for selecting consecutive seats'
}

@rules_bp.route('/events/<int:event_id>/rules')
@login_required
def event_rules(event_id):
    event = Event.query.get_or_404(event_id)
    rules = {rule_type: next((rule for rule in event.rules if rule.rule_type == rule_type), None)
            for rule_type in VALID_RULE_TYPES}
    return render_template('event_rules.html', 
                         event=event, 
                         rules=rules, 
                         descriptions=RULE_DESCRIPTIONS)

@rules_bp.route('/events/<int:event_id>/rules/<rule_type>', methods=['POST'])
@login_required
def manage_rule(event_id, rule_type):
    if rule_type not in VALID_RULE_TYPES:
        return jsonify({'error': 'Invalid rule type'}), 400
    
    event = Event.query.get_or_404(event_id)
    keyword = request.form.get('keyword', '').strip()
    
    if not keyword:
        return jsonify({'error': 'Keyword is required'}), 400
    
    rule = EventRule.query.filter_by(event_id=event_id, rule_type=rule_type).first()
    
    if rule:
        rule.keyword = keyword
    else:
        rule = EventRule(
            event_id=event_id,
            rule_type=rule_type,
            keyword=keyword
        )
        db.session.add(rule)
        
    try:
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@rules_bp.route('/events/<int:event_id>/rules/<rule_type>', methods=['DELETE'])
@login_required
def delete_rule(event_id, rule_type):
    if rule_type not in VALID_RULE_TYPES:
        return jsonify({'error': 'Invalid rule type'}), 400
    
    rule = EventRule.query.filter_by(event_id=event_id, rule_type=rule_type).first()
    if rule:
        try:
            db.session.delete(rule)
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Rule not found'}), 404

@rules_bp.route('/mappings')
@login_required
def mappings_list():
    # Get unique events with their rules
    events = db.session.query(Event)\
        .group_by(Event.event_name, Event.city_id, Event.venue_name)\
        .all()
    
    # Get rules for each unique event combination
    rule_groups = {}
    for event in events:
        similar_events = Event.query.filter_by(
            event_name=event.event_name,
            city_id=event.city_id,
            venue_name=event.venue_name
        ).all()
        
        # Collect all rules from similar events
        all_rules = []
        for similar_event in similar_events:
            all_rules.extend(similar_event.rules)
            
        key = (event.event_name, event.city_id, event.venue_name)
        rule_groups[key] = all_rules

    return render_template('mappings.html', 
                         events=events,
                         rule_groups=rule_groups,
                         cities=CITY_URL_MAP,
                         rule_types=VALID_RULE_TYPES)

@rules_bp.route('/mappings/new', methods=['GET', 'POST'])
@login_required
def new_mapping():
    if request.method == 'POST':
        try:
            # Get all matching events
            matching_events = Event.query.filter_by(
                event_name=request.form['event_name'].strip(),
                city_id=int(request.form['city_id']),
                venue_name=request.form['venue_name'].strip() or None
            ).all()
            
            if not matching_events:
                flash('No matching events found', 'error')
                return redirect(url_for('rules.mappings_list'))
            
            # Process rules for all matching events
            form_data = request.form.to_dict()
            for event in matching_events:
                for rule_type in VALID_RULE_TYPES:
                    keyword = form_data.get(f'rules[{rule_type}]', '').strip()
                    if keyword:
                        # Find existing rule or create new one
                        rule = EventRule.query.filter_by(
                            event_id=event.id,
                            rule_type=rule_type
                        ).first()
                        
                        if rule:
                            rule.keyword = keyword
                        else:
                            rule = EventRule(
                                event_id=event.id,
                                rule_type=rule_type,
                                keyword=keyword
                            )
                            db.session.add(rule)
            
            db.session.commit()
            flash(f'Rules updated for {len(matching_events)} events', 'success')
            return redirect(url_for('rules.mappings_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating mappings: {str(e)}', 'error')
            
    events = Event.query.distinct(Event.event_name, Event.city_id, Event.venue_name).all()
    return render_template('mapping_form.html', 
                         events=events,
                         cities=CITY_URL_MAP,
                         rule_types=VALID_RULE_TYPES)

@rules_bp.route('/mappings/<int:id>/delete', methods=['POST'])
@login_required
def delete_mapping(id):
    rule = EventRule.query.get_or_404(id)
    try:
        # Get all matching events
        matching_events = Event.query.filter_by(
            event_name=rule.event.event_name,
            city_id=rule.event.city_id,
            venue_name=rule.event.venue_name
        ).all()
        
        # Delete rules for all matching events
        for event in matching_events:
            matching_rule = EventRule.query.filter_by(
                event_id=event.id,
                rule_type=rule.rule_type
            ).first()
            if matching_rule:
                db.session.delete(matching_rule)
                
        db.session.commit()
        flash('Rule mapping deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting mapping: {str(e)}', 'error')
    
    return redirect(url_for('rules.mappings_list'))

@rules_bp.route('/mappings/copy', methods=['POST'])
@login_required
def copy_rules():
    try:
        source_event_id = request.form.get('source_event_id')
        target_event_name = request.form.get('target_event_name')
        target_city_id = request.form.get('target_city_id')
        target_venue = request.form.get('target_venue')
        
        source_event = Event.query.get_or_404(source_event_id)
        target_event = Event.query.filter_by(
            event_name=target_event_name,
            city_id=target_city_id,
            venue_name=target_venue
        ).first()
        
        if not target_event:
            return jsonify({'error': 'Target event not found'}), 404
            
        # Copy rules
        for rule in source_event.rules:
            new_rule = EventRule(
                event_id=target_event.id,
                rule_type=rule.rule_type,
                keyword=rule.keyword
            )
            db.session.add(new_rule)
            
        db.session.commit()
        flash('Rules copied successfully', 'success')
        
    except Exception as e:
        flash(f'Error copying rules: {str(e)}', 'error')
        
    return redirect(url_for('rules.mappings_list'))