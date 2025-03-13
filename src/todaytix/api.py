import re
from flask import current_app
import requests
import logging
import os
import json
from typing import Dict, List, Optional
from .models import ShowTime, Seat

logger = logging.getLogger(__name__)

class TodayTixAPI:
    BASE_URL = "https://api.todaytix.com/api/v2"
    
    def __init__(self):
        self.proxy_url = os.getenv('PROXY_API_URL')
        self.proxy_api_key = os.getenv('PROXY_API_KEY')
        logger.info(f"Proxy URL: {self.proxy_url}")
        if not all([self.proxy_url, self.proxy_api_key]):
            raise ValueError("Missing proxy configuration in environment")
            
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-Api-Key': self.proxy_api_key
        })

    def _make_proxy_request(self, method: str, endpoint: str, params: Dict = None) -> Dict:
        """Make a request through the proxy service."""
        target_url = f"{self.BASE_URL}{endpoint}"
        proxy_params = {'url': target_url}
        
        if params:
            proxy_params.update(params)
        try:
            logger.info(f"Making proxy request to: {target_url}")
            response = self.session.request(
                method=method,
                url=f"{self.proxy_url}/api/proxy/request",
                params=proxy_params
            )
            response.raise_for_status()
            
            proxy_response = response.json()
            if not proxy_response.get('content'):
                logger.error("No content in proxy response")
                return None
                
            return json.loads(proxy_response['content'])
            
        except requests.RequestException as e:
            logger.error(f"Proxy request failed: {str(e)}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse response: {str(e)}")
            return None

    def search_event(self, event_name: str, location: int = 2) -> Optional[Dict]:
        """
        Search for an event and return its details.
        Handles punctuation in event names by normalizing strings before comparison.
        """
        def normalize_string(s: str) -> str:
            s = re.sub(r'[^\w\s]', '', s)
            return ' '.join(s.lower().split())
    
        params = {
            'fieldset': 'SHOW_SUMMARY',
            'query': normalize_string(event_name),
            'location': location,
            'limit': 5,
            'offset': 0,
            'includeAggregations': False,
        }
        
        data = self._make_proxy_request('GET', '/shows', params=params)
        if not data or 'data' not in data:
            return None
    
        
        for event in data['data']:
            if event['displayName'] == event_name:
                return event
        
        return None

    def get_showtimes(self, show_id: int) -> List[ShowTime]:
        """Get all available showtimes for an event."""
        data = self._make_proxy_request('GET', f'/shows/{show_id}/showtimes')
        if not data or 'data' not in data:
            return []
            
        return [
            ShowTime(
                id=show['id'],
                datetime=show['datetime'],
                local_date=show['localDate'],
                local_time=show['localTime'],
                day_of_week=show['dayOfWeek']
            )
            for show in data['data']
        ]

    def analyze_seat_pattern(self, seats):
        """
        If rules are provided, analyze patterns. Otherwise, create sorted pairs.
        Returns tuple of (pattern_type, seats_list) where pattern_type is 'even', 'odd', 'consecutive', or None
        """
        seat_numbers = []
        for seat in seats:
            try:
                # Extract numeric part of seat name
                num = int(''.join(filter(str.isdigit, seat['name'])))
                seat_numbers.append((num, seat))
            except (ValueError, TypeError):
                continue

        if not seat_numbers:
            return None, []

        # Sort by seat number for consistency
        seat_numbers.sort(key=lambda x: x[0])
        seats_list = [s[1] for s in seat_numbers]

        # Pattern analysis
        numbers = [x[0] for x in seat_numbers]
        
        if all(n % 2 == 0 for n in numbers):
            return 'even', seats_list
        if all(n % 2 == 1 for n in numbers):
            return 'odd', seats_list

        # Find consecutive pairs
        consecutive_pairs = []
        for i in range(len(numbers)-1):
            if numbers[i+1] == numbers[i] + 1:
                consecutive_pairs.append((seat_numbers[i][1], seat_numbers[i+1][1]))

        if consecutive_pairs:
            return 'consecutive', [s for pair in consecutive_pairs for s in pair]

        return None, seats_list

    def get_seats(self, show_id: int, showtime_id: int, rules: dict = None, excluded_seats: dict = None) -> List[Dict]:
        """
        Get available seats for a specific showtime.
        When rules exist, apply pattern matching.
        When no rules, get pairs of seats starting with lowest numbered seats.
        """
        params = {
            'allowMultipleGaSections': True,
            'quantity': 2,
            'groupSelectionBy': 'SAME_PROVIDER'
        }
        
        data = self._make_proxy_request(
            'GET',
            f'/shows/{show_id}/showtimes/{showtime_id}/sections',
            params=params
        )
        
        if not data or 'data' not in data:
            return []
    
        # Store all possible pairs with their prices for sorting
        all_pairs = []
        
        for section in data['data']:
            base_section_name = section['name']
            
            for block in section['seatBlocks']:
                row = block['row']
                price = block['salePrice']['value']
                
                non_restricted_seats = [
                    seat for seat in block['seats']
                    if not seat['isRestrictedView']
                ]
    
                # First check if these seats are excluded
                key = f"{base_section_name}_{row}"
                if excluded_seats and key in excluded_seats:
                    # Filter out excluded seats before pattern analysis
                    non_restricted_seats = [
                        seat for seat in non_restricted_seats
                        if not any(s.strip() == seat['name'] for s in excluded_seats[key])
                    ]
    
                if not non_restricted_seats:
                    continue
                
                pattern_type, pattern_seats = self.analyze_seat_pattern(non_restricted_seats)
                
                if not pattern_seats:
                    continue
                
                # Apply pattern rules to section name AFTER exclusion check
                section_name = base_section_name
                if rules and pattern_type in rules:
                    section_name = f"{base_section_name} {rules[pattern_type]}"
    
                # Create pairs while maintaining seat order
                for i in range(0, len(pattern_seats)-1, 2):
                    seat1, seat2 = pattern_seats[i], pattern_seats[i+1]
                    try:
                        seat_num1 = int(''.join(filter(str.isdigit, seat1['name'])))
                        seat_num2 = int(''.join(filter(str.isdigit, seat2['name'])))
                    except (ValueError, TypeError):
                        continue
                    
                    pair_data = {
                        'seats': f"{seat1['name']},{seat2['name']}",
                        'section': section_name,
                        'row': row,
                        'price': price,
                        'face_value': block['faceValue']['value'],
                        'is_restricted_view': False,
                        'pattern_type': pattern_type,
                        'fees': {
                            'convenience': block['feeSummary']['convenience']['value'],
                            'concierge': block['feeSummary']['concierge']['value'],
                            'order': block['feeSummary']['orderFee']['value']
                        },
                        'sort_key': (
                            price,                    
                            ord(row[0]) if row else 0, 
                            seat_num1                 
                        )
                    }
                    all_pairs.append(pair_data)
    
        all_pairs.sort(key=lambda x: x['sort_key'])
        
        seen_sections = set()
        final_pairs = []
        
        for pair in all_pairs:
            section_key = f"{pair['section']}_{pair['row']}"
            if section_key not in seen_sections:
                seen_sections.add(section_key)
                del pair['sort_key']
                final_pairs.append(pair)
    
        return final_pairs