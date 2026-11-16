from __future__ import annotations
import datetime as dt
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

@dataclass(frozen=True, order=True)
class NightRange:
    arrival: dt.date
    departure: dt.date
    def __post_init__(self):
        if self.departure <= self.arrival:
            raise ValueError('departure must follow arrival')
    @property
    def nights(self):
        return (self.departure - self.arrival).days
    def overlaps(self, other: 'NightRange') -> bool:
        return self.arrival < other.departure and other.arrival < self.departure
    def contains(self, day: dt.date) -> bool:
        return self.arrival <= day < self.departure
    def split(self) -> tuple[dt.date, ...]:
        return tuple(self.arrival + dt.timedelta(days=offset) for offset in range(self.nights))

class InventoryCalendar:
    def occupied(self, reservations: Iterable[Mapping[str, Any]], bed_id: str, period: NightRange, ignore: str | None = None) -> bool:
        for reservation in reservations:
            if reservation.get('bed_id') != bed_id or reservation.get('reservation_id') == ignore:
                continue
            if reservation.get('status') not in {'held','confirmed','checked_in'}:
                continue
            existing = NightRange(dt.date.fromisoformat(reservation['arrival']), dt.date.fromisoformat(reservation['departure']))
            if period.overlaps(existing):
                return True
        return False

    def free_beds(self, beds: Sequence[Mapping[str, Any]], reservations: Sequence[Mapping[str, Any]], period: NightRange, requirements: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        result = []
        for bed in beds:
            if bed.get('status') != 'active':
                continue
            if requirements.get('accessible') and not bed.get('accessible'):
                continue
            if requirements.get('female_only') and bed.get('room_gender') not in {'female','any'}:
                continue
            if requirements.get('station_ids') and bed.get('station_id') not in set(requirements['station_ids']):
                continue
            if not self.occupied(reservations, bed['bed_id'], period):
                result.append(bed)
        return sorted(result, key=lambda item: (not item.get('accessible',False), item.get('station_priority',99), item['bed_id']))

    def utilization(self, beds: Sequence[Mapping[str, Any]], reservations: Sequence[Mapping[str, Any]], period: NightRange) -> dict[str, float]:
        capacity = len(beds) * period.nights
        used = 0
        for reservation in reservations:
            if reservation.get('status') not in {'confirmed','checked_in','completed'}:
                continue
            stay = NightRange(dt.date.fromisoformat(reservation['arrival']), dt.date.fromisoformat(reservation['departure']))
            used += sum(1 for night in period.split() if stay.contains(night))
        return {'capacity_bed_nights': capacity, 'used_bed_nights': used, 'utilization': used / capacity if capacity else 0.0}
