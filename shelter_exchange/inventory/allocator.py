from __future__ import annotations
import datetime as dt
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from .calendar import InventoryCalendar, NightRange

@dataclass(frozen=True)
class Allocation:
    application_id: str
    bed_id: str | None
    station_id: str | None
    status: str
    score: tuple[int, int, str]
    reasons: tuple[str, ...]

class BedAllocator:
    def __init__(self, calendar: InventoryCalendar | None = None):
        self.calendar = calendar or InventoryCalendar()

    def allocate(self, application: Mapping[str, Any], beds: Sequence[Mapping[str, Any]], reservations: Sequence[Mapping[str, Any]]) -> Allocation:
        period = NightRange(dt.date.fromisoformat(application['arrival']), dt.date.fromisoformat(application['departure']))
        requirements = {'accessible': bool(application.get('accessible')), 'female_only': application.get('gender') == 'female', 'station_ids': application.get('station_ids', [])}
        free = self.calendar.free_beds(beds, reservations, period, requirements)
        if not free:
            return Allocation(application['application_id'], None, None, 'waitlisted', (999,999,''), ('no_continuous_bed_available',))
        ranked = []
        for bed in free:
            commute = int(bed.get('commute_minutes', 999))
            accessibility_penalty = 0 if not application.get('accessible') or bed.get('accessible') else 1
            ranked.append(((accessibility_penalty, commute, bed['bed_id']), bed))
        score, selected = min(ranked, key=lambda item: item[0])
        return Allocation(application['application_id'], selected['bed_id'], selected['station_id'], 'allocated', score, ())

    def promote_waitlist(self, waiting: Sequence[Mapping[str, Any]], beds: Sequence[Mapping[str, Any]], reservations: list[Mapping[str, Any]]) -> list[Allocation]:
        allocations = []
        ordered = sorted(waiting, key=lambda item: (-int(item.get('priority',0)), item.get('submitted_at',''), item['application_id']))
        for application in ordered:
            allocation = self.allocate(application, beds, reservations)
            allocations.append(allocation)
            if allocation.bed_id:
                reservations.append({'reservation_id':'provisional:'+application['application_id'],'bed_id':allocation.bed_id,'arrival':application['arrival'],'departure':application['departure'],'status':'held'})
        return allocations
