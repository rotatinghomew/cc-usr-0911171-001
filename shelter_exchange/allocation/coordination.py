from __future__ import annotations
import datetime as dt
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from ..inventory.calendar import BLOCKING_STATUSES

@dataclass(frozen=True)
class NightDemand:
    application_id: str
    applicant_id: str
    arrival: dt.date
    departure: dt.date
    gender: str
    accessible: bool
    priority: int
    @property
    def nights(self):
        return tuple(self.arrival + dt.timedelta(days=i) for i in range((self.departure-self.arrival).days))

class ShelterCoordination:
    def demand(self, payload: Mapping[str, Any]) -> NightDemand:
        arrival=dt.date.fromisoformat(str(payload['arrival'])); departure=dt.date.fromisoformat(str(payload['departure']))
        if departure <= arrival: raise ValueError('departure_must_follow_arrival')
        return NightDemand(str(payload['application_id']),str(payload['applicant_id']),arrival,departure,str(payload.get('gender','any')),bool(payload.get('accessible',False)),int(payload.get('priority',0)))
    def occupied_nights(self, reservations: Sequence[Mapping[str,Any]]):
        result={}
        for row in reservations:
            if row.get('status') not in BLOCKING_STATUSES: continue
            start=dt.date.fromisoformat(str(row['arrival'])); end=dt.date.fromisoformat(str(row['departure']))
            result.setdefault(str(row['bed_id']),set()).update(start+dt.timedelta(days=i) for i in range((end-start).days))
        return result
    def compatible(self, demand, bed):
        reasons=[]
        if bed.get('status')!='active': reasons.append('bed_inactive')
        if bed.get('room_gender') not in {None,'any',demand.gender}: reasons.append('gender_mismatch')
        if demand.accessible and not bed.get('accessible',False): reasons.append('accessibility_mismatch')
        if int(bed.get('maximum_stay',15)) < len(demand.nights): reasons.append('stay_too_long_for_bed')
        return not reasons,tuple(reasons)
    def rank_beds(self,payload,beds,reservations):
        demand=self.demand(payload); occupied=self.occupied_nights(reservations); ranked=[]
        for bed in beds:
            ok,reasons=self.compatible(demand,bed); conflicts=sorted(day.isoformat() for day in set(demand.nights)&occupied.get(str(bed.get('bed_id')),set()))
            if conflicts: reasons=(*reasons,'night_conflict');ok=False
            score=(int(bed.get('commute_minutes',999)),-int(bed.get('station_priority',0)),str(bed.get('bed_id','')))
            ranked.append({'bed_id':bed.get('bed_id'),'station_id':bed.get('station_id'),'eligible':ok,'reasons':list(reasons),'conflicts':conflicts,'score':score})
        return sorted(ranked,key=lambda row:(not row['eligible'],row['score']))
    def waitlist_order(self,applications):
        def key(row):return (-int(row.get('priority',0)),dt.datetime.fromisoformat(str(row.get('submitted_at','2026-11-16T00:00:00+00:00'))),str(row.get('application_id')))
        return [str(row['application_id']) for row in sorted(applications,key=key)]
    def release_for_no_show(self,reservation,observed_at,grace_minutes=120):
        arrival=dt.date.fromisoformat(str(reservation['arrival']));deadline=dt.datetime.combine(arrival,dt.time(20),tzinfo=observed_at.tzinfo)+dt.timedelta(minutes=grace_minutes);releasable=reservation.get('status')=='confirmed' and observed_at>deadline
        return {'reservation_id':reservation.get('reservation_id'),'releasable':releasable,'released_nights':(dt.date.fromisoformat(str(reservation['departure']))-arrival).days if releasable else 0,'deadline':deadline.isoformat()}
    def evaluate(self,payload,context,eligible:bool=True):
        ranked=self.rank_beds(payload,context.get('beds',()),context.get('reservations',()));chosen=next((row for row in ranked if row['eligible']),None) if eligible else None
        return {'requested_nights':len(self.demand(payload).nights),'selected':chosen,'candidate_count':len(ranked),'waitlist_position':(None if chosen else 1) if eligible else None}
