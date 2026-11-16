import datetime as dt
import tempfile
import unittest
from pathlib import Path
from shelter_exchange.allocation.coordination import ShelterCoordination
from shelter_exchange.inventory.allocator import BedAllocator
from shelter_exchange.inventory.calendar import BLOCKING_STATUSES, InventoryCalendar, NightRange
from shelter_exchange.operations.service import ShelterService
from shelter_exchange.storage import Database

RELEASED_STATUSES = ('cancelled', 'expired', 'no_show', 'completed', 'early_departure')

class AvailabilityConsistencyTests(unittest.TestCase):
    """申请 -> 床位分析 -> 最终分配 -> 入住量核对 的一致性回归验证。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = ShelterService(Database(Path(self.temp.name) / 'db.sqlite3'), today=lambda: dt.date(2026, 11, 16))
        self.coordination = ShelterCoordination()
        self.allocator = BedAllocator()
        self.beds = [{'bed_id': 'bed-1', 'station_id': 'station-1', 'status': 'active', 'room_gender': 'female', 'commute_minutes': 10}]

    def tearDown(self):
        self.temp.cleanup()

    def application(self, **changes):
        payload = {'application_id': 'app-1', 'applicant_id': 'person-1', 'arrival': '2026-11-20', 'departure': '2026-11-23',
                   'graduation_year': 2026, 'interview_invitation': 'invite-1', 'diploma_reference': 'diploma-1', 'gender': 'female'}
        payload.update(changes)
        return payload

    def reservation(self, status, arrival='2026-11-21', departure='2026-11-22'):
        return {'reservation_id': f'res-{status}', 'bed_id': 'bed-1', 'arrival': arrival, 'departure': departure, 'status': status}

    def analysis_and_allocation(self, payload, reservations):
        analysis = self.coordination.evaluate(payload, {'beds': self.beds, 'reservations': reservations})
        allocation = self.allocator.allocate(payload, self.beds, reservations)
        return analysis, allocation

    def test_blocking_statuses_agree_between_analysis_and_allocation(self):
        for status in sorted(BLOCKING_STATUSES):
            with self.subTest(status=status):
                analysis, allocation = self.analysis_and_allocation(self.application(), [self.reservation(status)])
                self.assertIsNone(analysis['selected'])
                self.assertEqual(analysis['waitlist_position'], 1)
                self.assertEqual(allocation.status, 'waitlisted')

    def test_released_statuses_agree_between_analysis_and_allocation(self):
        for status in RELEASED_STATUSES:
            with self.subTest(status=status):
                analysis, allocation = self.analysis_and_allocation(self.application(), [self.reservation(status)])
                self.assertIsNotNone(analysis['selected'])
                self.assertEqual(analysis['selected']['bed_id'], 'bed-1')
                self.assertEqual(allocation.status, 'allocated')
                self.assertEqual(allocation.bed_id, 'bed-1')

    def test_adjacent_checkout_is_free_but_cross_day_overlap_blocks(self):
        adjacent = self.reservation('held', arrival='2026-11-18', departure='2026-11-20')
        analysis, allocation = self.analysis_and_allocation(self.application(), [adjacent])
        self.assertIsNotNone(analysis['selected'])
        self.assertEqual(allocation.status, 'allocated')
        overlap = self.reservation('held', arrival='2026-11-22', departure='2026-11-24')
        analysis, allocation = self.analysis_and_allocation(self.application(), [overlap])
        self.assertIsNone(analysis['selected'])
        self.assertEqual(allocation.status, 'waitlisted')

    def test_held_short_stay_no_longer_shows_as_first_choice(self):
        # 值班员场景：唯一床位某晚已有短时预留，分析与提交结论必须一致
        payload = self.application()
        result = self.service.submit(payload, self.beds, [self.reservation('held')], [], 'req-held-1')
        self.assertEqual(result['state'], 'waitlisted')
        self.assertIsNone(result['coordination']['selected'])
        self.assertEqual(result['coordination']['waitlist_position'], 1)
        self.assertIsNone(result['bed_id'])

    def test_ineligible_application_implies_no_vacancy(self):
        payload = self.application(interview_invitation='')
        result = self.service.submit(payload, self.beds, [], [], 'req-ineligible-1')
        self.assertEqual(result['state'], 'rejected')
        self.assertFalse(result['eligible'])
        self.assertIsNone(result['coordination']['selected'])
        self.assertIsNone(result['coordination']['waitlist_position'])

    def test_notification_and_duplicate_request_behavior_preserved(self):
        payload = self.application(interview_invitation='')
        first = self.service.submit(payload, self.beds, [], [], 'req-replay-1')
        replay = self.service.submit(payload, self.beds, [], [], 'req-replay-1')
        self.assertEqual(first, replay)
        pending = self.service.database.pending_messages()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['topic'], 'application.result')

    def test_waitlist_priority_order_preserved(self):
        waiting = [self.application(application_id='low', priority=1, submitted_at='2026-11-16T09:00:00+00:00'),
                   self.application(application_id='high', priority=2, submitted_at='2026-11-16T10:00:00+00:00')]
        results = self.allocator.promote_waitlist(waiting, self.beds, [])
        self.assertEqual([item.application_id for item in results], ['high', 'low'])
        self.assertEqual([item.status for item in results], ['allocated', 'waitlisted'])

    def test_occupancy_reconciliation_after_allocation(self):
        confirmed = [self.reservation('confirmed', arrival='2026-11-20', departure='2026-11-23')]
        report = self.service.occupancy_report(self.beds, confirmed, dt.date(2026, 11, 20), dt.date(2026, 11, 23))
        self.assertEqual(report['capacity_bed_nights'], 3)
        self.assertEqual(report['used_bed_nights'], 3)
        self.assertEqual(report['utilization'], 1.0)

    def test_held_blocks_availability_without_inflating_occupancy(self):
        held = [self.reservation('held', arrival='2026-11-21', departure='2026-11-22')]
        analysis, allocation = self.analysis_and_allocation(self.application(), held)
        self.assertIsNone(analysis['selected'])
        self.assertEqual(allocation.status, 'waitlisted')
        report = self.service.occupancy_report(self.beds, held, dt.date(2026, 11, 20), dt.date(2026, 11, 23))
        self.assertEqual(report['used_bed_nights'], 0)

    def test_end_to_end_application_analysis_occupancy_chain(self):
        payload = self.application()
        result = self.service.submit(payload, self.beds, [], [], 'req-chain-1')
        self.assertEqual(result['state'], 'allocated')
        self.assertEqual(result['coordination']['selected']['bed_id'], 'bed-1')
        confirmed = [self.reservation('confirmed')]
        report = self.service.occupancy_report(self.beds, confirmed, dt.date(2026, 11, 20), dt.date(2026, 11, 23))
        self.assertEqual(report['used_bed_nights'], 1)
        self.assertEqual(report['applications'], 1)
        self.assertEqual(report['pending_notifications'], 1)

if __name__ == '__main__':
    unittest.main()
