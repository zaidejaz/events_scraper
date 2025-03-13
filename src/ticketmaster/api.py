from datetime import datetime
import os
import re
import requests
import logging
import uuid
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class TicketmasterAPI:
    BASE_URL = 'https://services.ticketmaster.com/api/ismds'

    def __init__(self):
        self.api_key = os.getenv('TICKETMASTER_API_KEY')
        self.api_secret = os.getenv('TICKETMASTER_API_SECRET')
        self.consumer_api = os.getenv('TICKETMASTER_CONSUMER_API')
        if not all([self.api_key, self.api_secret]):
            raise ValueError("Missing Ticketmaster API configuration in environment")

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'TMPS-Correlation-Id': str(uuid.uuid4()), 
            'Origin': 'https://www.ticketmaster.com',
            'Connection': 'keep-alive',
            'Referer': 'https://www.ticketmaster.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
            'TE': 'trailers'
        }

    def search_events(self, event_name: str, location: str, start_date: str, end_date: str) -> List[Dict]:
        """
        Search for events using the Ticketmaster Discovery API.

        Args:
            event_name (str): Name/keyword of the event to search for
            location (str): City name
            start_date (str): Start date in YYYY-MM-DD format  
            end_date (str): End date in YYYY-MM-DD format

        Returns:
            List[Dict]: List of matching events with relevant details
        """
        try:
            base_url = 'https://app.ticketmaster.com/discovery/v2/events'
            processed_events = []
            page = 0

            # Convert input dates to datetime objects for comparison
            start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
            end_datetime = datetime.strptime(end_date, '%Y-%m-%d')

            # Normalize event name for comparison
            normalized_event_name = event_name.lower().strip()

            while True:
                query_params = {
                    'apikey': self.consumer_api,
                    'keyword': event_name,
                    'locale': '*',
                    'city': location,
                    'size': 200,
                    'page': page
                }

                response = requests.get(
                    base_url,
                    params=query_params,
                    headers=self.headers
                )
                response.raise_for_status()
                data = response.json()

                if '_embedded' not in data or 'events' not in data['_embedded']:
                    break

                events = data['_embedded']['events']
                if not events:
                    break

                # Process events and filter by date and exact name match
                for event in events:
                    try:
                        # Check for exact name match (case-insensitive)
                        event_name_from_api = event.get('name', '').lower().strip()
                        if event_name_from_api != normalized_event_name:
                            continue

                        event_date = datetime.strptime(
                            event['dates']['start'].get('localDate', ''),
                            '%Y-%m-%d'
                        )

                        # Extract Ticketmaster ID from URL
                        ticketmaster_id = ''
                        event_url = event.get('url', '')
                        if event_url:
                            # Try to extract ID from the end of the URL
                            id_match = re.search(r'/event/([A-Z0-9]+)(?:\?|$)', event_url)
                            if id_match:
                                ticketmaster_id = id_match.group(1)

                        # Check if event is within date range
                        if start_datetime <= event_date <= end_datetime:
                            event_info = {
                                'website': 'Ticketmaster',
                                'event_id': '',
                                'ticketmaster_event_id': ticketmaster_id,
                                'event_name': event.get('name', ''),
                                'city': location,
                                'event_date': event['dates']['start'].get('localDate', ''),
                                'event_time': event['dates']['start'].get('localTime', ''),
                                'venue_name': event['_embedded']['venues'][0].get('name', '') if event.get('_embedded', {}).get('venues') else '',
                                'markup': '1.6'
                            }
                            processed_events.append(event_info)
                    except (ValueError, KeyError) as e:
                        logger.error(f"Error processing event: {str(e)}")
                        continue

                # Check if we need to go to next page
                page_info = data.get('page', {})
                total_pages = page_info.get('totalPages', 0)
                current_page = page_info.get('number', 0)

                if current_page >= total_pages - 1:
                    break

                page += 1

            return processed_events

        except requests.RequestException as e:
            logger.error(f"Error searching events: {str(e)}")
            if 'response' in locals() and hasattr(response, 'text'):
                logger.error(f"Response content: {response.text}")
            return []

    def get_seats(self, event_id: str) -> List[Dict]:
        """Get available seats for a specific event."""
        seats_data = []
        offset = 0
        limit = 40

        while True:
            try:
                base_url = f'{self.BASE_URL}/event/{event_id}/quickpicks'
                
                # Query parameters
                query_params = (
                    f'show=places+sections'
                    f'&mode=primary:ppsectionrow+resale:ga_areas+platinum:all'
                    f'&qty=2'
                    f"&q=not('accessible')"
                    f'&includeStandard=true'
                    f'&includeResale=false'
                    f'&includePlatinumInventoryType=false'
                    f'&ticketTypes=000000000001'
                    f'&embed=area&embed=offer&embed=description'
                    f'&apikey={self.api_key}'
                    f'&apisecret={self.api_secret}'
                    f'&resaleChannelId=internal.ecommerce.consumer.desktop.web.browser.ticketmaster.us'
                    f'&limit={limit}'
                    f'&offset={offset}'
                    f'&sort=listprice'
                )

                url = f"{base_url}?{query_params}"

                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()

                if not data.get('picks'):
                    break

                processed_seats = self._process_seats_data(data)
                seats_data.extend(processed_seats)

                if len(data['picks']) < limit:
                    break

                offset += limit

            except Exception as e:
                logger.error(f"Error fetching seats for event {event_id}: {str(e)}")
                if 'response' in locals() and hasattr(response, 'text'):
                    logger.error(f"Response content: {response.text}")
                break

        return seats_data

    def _process_seats_data(self, data: Dict) -> List[Dict]:
        """Process raw seats data into standardized format."""
        processed_seats = []
        offer_map = {offer['offerId']: offer for offer in data.get('_embedded', {}).get('offer', [])}

        for pick in data['picks']:
            if pick['selection'] != 'standard':
                continue

            # Handle GA event
            if pick['type'] == 'general-seating':
                offer_id = pick['offers'][0]
                offer = offer_map.get(offer_id, {})
                price = offer.get('listPrice', 0)
                face_value = offer.get('faceValue', 0)

                processed_seats.append({
                    'section': pick['section'],
                    'row': 'GA',
                    'seats': ','.join(map(str, range(20, 24))),  
                    'price': price,
                    'face_value': face_value,
                    'type': 'standard'
                })
                continue

            # Handle regular seats
            if pick['type'] == 'seat':
                for offer_group in pick['offerGroups']:
                    offer_id = offer_group['offers'][0]
                    offer = offer_map.get(offer_id, {})
                    
                    if not offer_group.get('seats'):
                        continue

                    price = offer.get('listPrice', 0)
                    face_value = offer.get('faceValue', 0)

                    processed_seats.append({
                        'section': pick['section'],
                        'row': pick['row'],
                        'seats': ','.join(map(str, offer_group['seats'])),
                        'price': price,
                        'face_value': face_value,
                        'type': 'standard'
                    })

        return processed_seats