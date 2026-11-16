import datetime as dt
import unittest
from shelter_exchange.allocation.coordination import ShelterCoordination
class CoordinationTests(unittest.TestCase):
 def setUp(self):self.flow=ShelterCoordination();self.payload={'application_id':'a1','applicant_id':'p1','arrival':'2026-11-20','departure':'2026-11-23','gender':'female'}
 def test_nights_are_half_open(self):self.assertEqual([x.isoformat() for x in self.flow.demand(self.payload).nights],['2026-11-20','2026-11-21','2026-11-22'])
 def test_adjacent_reservation_is_free(self):
  beds=[{'bed_id':'b1','station_id':'s1','status':'active','room_gender':'female','commute_minutes':5}];reservations=[{'bed_id':'b1','arrival':'2026-11-17','departure':'2026-11-20','status':'confirmed'}];self.assertTrue(self.flow.rank_beds(self.payload,beds,reservations)[0]['eligible'])
 def test_overlap_blocks_bed(self):
  beds=[{'bed_id':'b1','station_id':'s1','status':'active','room_gender':'female'}];reservations=[{'bed_id':'b1','arrival':'2026-11-22','departure':'2026-11-24','status':'checked_in'}];self.assertIn('night_conflict',self.flow.rank_beds(self.payload,beds,reservations)[0]['reasons'])
 def test_accessible_request_filters(self):self.assertFalse(self.flow.rank_beds({**self.payload,'accessible':True},[{'bed_id':'b1','status':'active','room_gender':'female','accessible':False}],[])[0]['eligible'])
 def test_waitlist_priority_then_time(self):
  rows=[{'application_id':'late','priority':1,'submitted_at':'2026-11-16T10:00:00+00:00'},{'application_id':'high','priority':2,'submitted_at':'2026-11-16T11:00:00+00:00'},{'application_id':'early','priority':1,'submitted_at':'2026-11-16T09:00:00+00:00'}];self.assertEqual(self.flow.waitlist_order(rows),['high','early','late'])
 def test_no_show_releases_all_nights(self):
  out=self.flow.release_for_no_show({'reservation_id':'r1','arrival':'2026-11-20','departure':'2026-11-23','status':'confirmed'},dt.datetime(2026,11,20,23,tzinfo=dt.timezone.utc));self.assertTrue(out['releasable']);self.assertEqual(out['released_nights'],3)
