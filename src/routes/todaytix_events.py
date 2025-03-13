from datetime import datetime
from flask import Blueprint, jsonify, render_template, request, current_app
from flask_login import login_required
import csv
from io import StringIO

from src.city_utils import CityMapper
from ..todaytix.api import TodayTixAPI
from ..constants import CITY_URL_MAP

bp = Blueprint('todaytix_events', __name__)
city_mapper = CityMapper()

@bp.route('/todaytix-events')
@login_required
def todaytix_events_page():
    return render_template('todaytix_events.html', cities=city_mapper.get_all_cities())

@bp.route('/api/todaytix-events/search', methods=['POST'])
@login_required
def search_events():
    try:
        data = request.json
        event_name = data.get('event_name')
        city = data.get('city')
        city_id = city_mapper.get_todaytix_id(city)
        start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()

        if not all([event_name, city_id, start_date, end_date]):
            return jsonify({
                'status': 'error',
                'message': 'All fields are required'
            }), 400

        api = TodayTixAPI()
        event = api.search_event(event_name, city_id)
        if not event:
            return jsonify({
                'status': 'error',
                'message': f'Event "{event_name}" not found'
            }), 404

        event_id = event['id']
        venue_name = event.get('venue', 'Unknown Venue')
        showtimes = api.get_showtimes(event_id)

        filtered_showtimes = []
        for showtime in showtimes:
            show_date = datetime.strptime(showtime.local_date, '%Y-%m-%d').date()
            if start_date <= show_date <= end_date:
                
                filtered_showtimes.append({
                    'website': 'TodayTix',
                    'event_id': "",
                    'todaytix_event_id': str(showtime.id),
                    'event_name': event_name,
                    'city': next((name for name, id_ in CITY_URL_MAP.items() if id_ == city_id), 'Unknown'),
                    'event_date': showtime.local_date,
                    'event_time': showtime.local_time,
                    'todaytix_show_id': str(event_id),
                    'venue_name': venue_name,
                    'markup': '1.6'
                })

        if not filtered_showtimes:
            return jsonify({
                'status': 'error',
                'message': 'No showtimes found in the specified date range'
            }), 404

        # Generate CSV
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'website', 'event_id', 'todaytix_event_id', 'event_name', 'city', 
            'event_date', 'event_time', 'todaytix_show_id', 'venue_name', 'markup'
        ])
        
        for show in filtered_showtimes:
            writer.writerow([
                show['website'],
                show['event_id'],
                show['todaytix_event_id'],
                show['event_name'],
                show['city'],
                show['event_date'],
                show['event_time'],
                show['todaytix_show_id'],
                show['venue_name'],
                show['markup']
            ])

        output.seek(0)
        return current_app.response_class(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                "Content-Disposition": f"attachment;filename=todaytix_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )
        
    except Exception as e:
        current_app.logger.error(f"Error searching events: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500