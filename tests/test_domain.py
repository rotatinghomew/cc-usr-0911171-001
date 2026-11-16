import datetime as dt
import unittest
from shelter_exchange.admission.eligibility import EligibilityPolicy
from shelter_exchange.inventory.calendar import InventoryCalendar,NightRange
from shelter_exchange.inventory.allocator import BedAllocator
from shelter_exchange.stays.lifecycle import StayError,StayLifecycle

class ShelterDomainTests(unittest.TestCase):
    def application(self,**changes):
        value={'application_id':'app-1','applicant_id':'person-1','arrival':'2026-11-20','departure':'2026-11-23','graduation_year':2026,'interview_invitation':'invite-123','diploma_reference':'degree-1','gender':'female'}; value.update(changes); return value
    def test_eligible_application(self): self.assertTrue(EligibilityPolicy().evaluate(self.application(),[],dt.date(2026,11,16)).eligible)
    def test_past_arrival(self): self.assertIn('arrival_in_past',EligibilityPolicy().evaluate(self.application(arrival='2026-11-10'),[],dt.date(2026,11,16)).reasons)
    def test_missing_invitation(self): self.assertIn('interview_invitation_missing',EligibilityPolicy().evaluate(self.application(interview_invitation=''),[],dt.date(2026,11,16)).reasons)
    def test_night_limit(self):
        prior=[{'applicant_id':'person-1','arrival':'2026-11-01','departure':'2026-11-15','status':'completed'}]; self.assertEqual(EligibilityPolicy().evaluate(self.application(),prior,dt.date(2026,11,16)).approved_nights,1)
    def test_overlap(self): self.assertTrue(NightRange(dt.date(2026,1,1),dt.date(2026,1,3)).overlaps(NightRange(dt.date(2026,1,2),dt.date(2026,1,4))))
    def test_adjacent_not_overlap(self): self.assertFalse(NightRange(dt.date(2026,1,1),dt.date(2026,1,3)).overlaps(NightRange(dt.date(2026,1,3),dt.date(2026,1,4))))
    def test_calendar_filters_conflict(self):
        beds=[{'bed_id':'b1','station_id':'s1','status':'active','room_gender':'female'}]; reservations=[{'reservation_id':'r1','bed_id':'b1','arrival':'2026-11-21','departure':'2026-11-24','status':'confirmed'}]
        self.assertEqual(InventoryCalendar().free_beds(beds,reservations,NightRange(dt.date(2026,11,20),dt.date(2026,11,23)),{}),[])
    def test_allocator_waitlists(self): self.assertEqual(BedAllocator().allocate(self.application(),[],[]).status,'waitlisted')
    def test_allocator_prefers_commute(self):
        beds=[{'bed_id':'b2','station_id':'s2','status':'active','room_gender':'female','commute_minutes':30},{'bed_id':'b1','station_id':'s1','status':'active','room_gender':'female','commute_minutes':10}]
        self.assertEqual(BedAllocator().allocate(self.application(),beds,[]).bed_id,'b1')
    def test_waitlist_prevents_double_allocation(self):
        beds=[{'bed_id':'b1','station_id':'s1','status':'active','room_gender':'female','commute_minutes':10}]; waiting=[self.application(application_id='a1',priority=2),self.application(application_id='a2',priority=1)]
        result=BedAllocator().promote_waitlist(waiting,beds,[]); self.assertEqual([x.status for x in result],['allocated','waitlisted'])
    def test_lifecycle(self):
        life=StayLifecycle('r1','confirmed',dt.date(2026,11,20),dt.date(2026,11,23)); checked=life.transition('checked_in',dt.datetime(2026,11,20,12,tzinfo=dt.timezone.utc)); self.assertEqual(checked.state,'checked_in')
    def test_illegal_lifecycle(self):
        with self.assertRaises(StayError): StayLifecycle('r1','confirmed',dt.date(2026,11,20),dt.date(2026,11,23)).transition('completed',dt.datetime.now(dt.timezone.utc))
