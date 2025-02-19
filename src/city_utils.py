class CityMapper:
    def __init__(self):
        self.todaytix_mappings = {
            "London": 2,
            "New York": 1,
            "Sydney": 17,
            "Los Angeles + OC": 5,
            "Brisbane": 19,
            "Chicago": 3,
            "Perth": 93,
            "SF Bay Area": 4,
            "Washington DC": 6,
            "Adelaide": 95,
            "Melbourne": 18,
            "Other Cities": 98
        }
        
        self.city_variations = {
            "london": "London",
            "new york": "New York",
            "nyc": "New York",
            "new york city": "New York",
            "los angeles": "Los Angeles + OC",
            "la": "Los Angeles + OC",
            "orange county": "Los Angeles + OC",
            "san francisco": "SF Bay Area",
            "sf": "SF Bay Area",
            "bay area": "SF Bay Area",
            "washington": "Washington DC",
            "dc": "Washington DC",
            "washington dc": "Washington DC",
            # Add more variations as needed
        }
        
        # Track custom cities
        self.custom_cities = set()

    def get_todaytix_id(self, city: str) -> int:
        """Get TodayTix city ID if it exists."""
        normalized_city = city.lower().strip()
        
        # Check if it's a known variation
        if normalized_city in self.city_variations:
            mapped_city = self.city_variations[normalized_city]
            return self.todaytix_mappings[mapped_city]
            
        # Check if it's a direct match
        for todaytix_city, city_id in self.todaytix_mappings.items():
            if normalized_city == todaytix_city.lower():
                return city_id
                
        # If not found, return Other Cities ID
        return self.todaytix_mappings["Other Cities"]

    def is_valid_city(self, city: str) -> bool:
        """Check if city is valid (either mapped or custom)."""
        normalized_city = city.lower().strip()
        return (normalized_city in self.city_variations or 
                normalized_city in {c.lower() for c in self.todaytix_mappings.keys()} or 
                normalized_city in self.custom_cities)

    def add_custom_city(self, city: str):
        """Add a new custom city."""
        self.custom_cities.add(city.lower().strip())

    def get_all_cities(self) -> list:
        """Get list of all valid cities (mapped + custom)."""
        all_cities = set(self.todaytix_mappings.keys())
        all_cities.update(self.custom_cities)
        return sorted(list(all_cities))
    
