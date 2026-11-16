from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, replace

class StayError(RuntimeError):
    pass

TRANSITIONS = {
    'held': {'confirmed','cancelled','expired'},
    'confirmed': {'checked_in','cancelled','no_show'},
    'checked_in': {'completed','early_departure'},
    'waitlisted': {'held','cancelled','expired'},
    'completed': set(), 'cancelled': set(), 'expired': set(), 'no_show': set(), 'early_departure': set(),
}

@dataclass(frozen=True)
class StayLifecycle:
    reservation_id: str
    state: str
    arrival: dt.date
    departure: dt.date
    checked_in_at: dt.datetime | None = None
    checked_out_at: dt.datetime | None = None
    version: int = 0

    def transition(self, target: str, now: dt.datetime) -> 'StayLifecycle':
        if target not in TRANSITIONS.get(self.state,set()):
            raise StayError(f'illegal transition {self.state}->{target}')
        values = {'state':target,'version':self.version+1}
        if target == 'checked_in':
            if now.date() < self.arrival or now.date() > self.departure:
                raise StayError('check-in outside arrival window')
            values['checked_in_at'] = now
        if target in {'completed','early_departure'}:
            if self.checked_in_at is None:
                raise StayError('cannot check out before check in')
            if now < self.checked_in_at:
                raise StayError('checkout before checkin')
            values['checked_out_at'] = now
        return replace(self, **values)

    def expire_if_due(self, now: dt.datetime, grace_hours: int = 6) -> 'StayLifecycle':
        if self.state not in {'held','confirmed','waitlisted'}:
            return self
        deadline = dt.datetime.combine(self.arrival, dt.time(hour=12), tzinfo=now.tzinfo) + dt.timedelta(hours=grace_hours)
        if now <= deadline:
            return self
        target = 'no_show' if self.state == 'confirmed' else 'expired'
        return replace(self,state=target,version=self.version+1)

    @property
    def consumed_nights(self) -> int:
        if self.state not in {'checked_in','completed','early_departure'}:
            return 0
        end = self.checked_out_at.date() if self.checked_out_at else self.departure
        return max(0,(min(end,self.departure)-self.arrival).days)
