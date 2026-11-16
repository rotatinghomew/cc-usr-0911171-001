from __future__ import annotations
from ..allocation.coordination import ShelterCoordination
import datetime as dt
import hashlib
import uuid
from typing import Any, Mapping, Sequence
from ..admission.eligibility import EligibilityPolicy
from ..contracts import Event, fingerprint
from ..inventory.allocator import BedAllocator
from ..storage import Database

class ShelterService:
    def __init__(self, database: Database, today=lambda: dt.date.today()):
        self.database=database; self.today=today; self.eligibility=EligibilityPolicy(); self.allocator=BedAllocator(); self.coordination=ShelterCoordination()

    def submit(self, payload: Mapping[str,Any], beds: Sequence[Mapping[str,Any]], reservations: Sequence[Mapping[str,Any]], prior_stays: Sequence[Mapping[str,Any]], request_key: str) -> dict[str,Any]:
        digest=fingerprint(payload)
        recalled=self.database.recalled('submit_application',request_key,digest)
        if recalled is not None: return recalled
        decision=self.eligibility.evaluate(payload,prior_stays,self.today())
        if decision.eligible:
            allocation=self.allocator.allocate(payload,beds,reservations)
            state=allocation.status
        else:
            allocation=None; state='rejected'
        coordination=self.coordination.evaluate(payload,{'beds':beds,'reservations':reservations},eligible=decision.eligible)
        result={'application_id':payload['application_id'],'eligible':decision.eligible,'reasons':list(decision.reasons),'approved_nights':decision.approved_nights,'state':state,'bed_id':allocation.bed_id if allocation else None,'station_id':allocation.station_id if allocation else None,'coordination':coordination}
        with self.database.transaction() as connection:
            record={'application_id':payload['application_id'],'owner_id':payload['applicant_id'],'category':'talent_shelter','status':'active' if state in {'allocated','waitlisted'} else 'cancelled','effective_from':payload['arrival'],'effective_to':payload['departure'],'quantity':decision.approved_nights,'amount':'0.00','attributes':result}
            version=self.database.put_record(connection,'application',record)
            event=Event(str(uuid.uuid4()),'application',payload['application_id'],'application_submitted',dt.datetime.now(dt.timezone.utc),result,version)
            self.database.append_event(connection,event)
            self.database.enqueue(connection,'notice:'+payload['application_id'],'application.result',payload['application_id'],result)
            self.database.remember(connection,'submit_application',request_key,digest,result)
        return result

    def process(self, payload: Mapping[str,Any], context: Mapping[str,Any], request_key: str) -> dict[str,Any]:
        return self.submit(payload, context.get('beds', ()), context.get('reservations', ()), context.get('prior_stays', ()), request_key)

    def occupancy_report(self, beds, reservations, start: dt.date, end: dt.date):
        from ..inventory.calendar import NightRange, InventoryCalendar
        report=InventoryCalendar().utilization(beds,reservations,NightRange(start,end))
        report['pending_notifications']=len(self.database.pending_messages())
        report['applications']=len(self.database.list_applications())
        return report
