from dataclasses import dataclass
from typing import Dict

@dataclass
class ShowTime:
    id: int
    datetime: str
    local_date: str
    local_time: str
    day_of_week: str

@dataclass
class Seat:
    section: str
    row: str
    seat_number: str
    price: float
    face_value: float
    is_restricted_view: bool
    seat_id: str
    fees: Dict[str, float]