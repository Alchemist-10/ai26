import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from source_clock import normalize_recording_clock, source_capture_clock_fields, source_time_from_decoder, validate_recording_clock


class RecordingClock(unittest.TestCase):
    def test_decoder_timestamp_is_preferred_and_invalid_values_fall_back_explicitly(self):
        self.assertEqual(source_time_from_decoder(2375, 60, 25, 10),
                         (2.375, 'decoder_reported_position_msec'))
        self.assertEqual(source_time_from_decoder(0, 60, 25, 10),
                         (2.4, 'frame_index_divided_by_reported_fps'))
        self.assertEqual(source_time_from_decoder(float('nan'), 60, 25, 10),
                         (2.4, 'frame_index_divided_by_reported_fps'))
        self.assertEqual(source_time_from_decoder(20000, 60, 25, 10),
                         (2.4, 'frame_index_divided_by_reported_fps'))
        self.assertEqual(source_time_from_decoder(None, 0, 0, 10),
                         (None, 'source_time_unavailable'))

    def test_timezone_offset_normalizes_and_projects_source_offset_separately(self):
        clock = normalize_recording_clock('2026-10-14T12:00:00+05:30', 1.25)
        self.assertEqual(clock['start_utc'], '2026-10-14T06:30:00.000000Z')
        self.assertEqual(clock['provenance'], 'operator_claimed')
        self.assertEqual(clock['status'], 'unverified')
        self.assertEqual(validate_recording_clock(clock), clock)
        fields = source_capture_clock_fields(clock, 12.5)
        self.assertEqual(fields, {
            'claimed_source_capture_time_utc': '2026-10-14T06:30:12.500000Z',
            'source_offset_basis': 'frame_index_divided_by_reported_fps',
            'recording_clock_status': 'operator_claimed_unverified',
            'recording_clock_uncertainty_seconds': 1.25,
        })

    def test_missing_claim_and_invalid_or_forged_claims_fail_closed(self):
        self.assertIsNone(normalize_recording_clock(None))
        self.assertEqual(source_capture_clock_fields(None, 10), {})
        for start, uncertainty in (
                ('2026-10-14T12:00:00', None),
                ('not-a-time', None),
                (None, 1),
                ('2026-10-14T12:00:00Z', True),
                ('2026-10-14T12:00:00Z', float('inf')),
                ('2026-10-14T12:00:00Z', 86401),
                ('2026-10-14T12:00:00Z', 10**1000)):
            with self.subTest(start=start, uncertainty=uncertainty), self.assertRaises(ValueError):
                normalize_recording_clock(start, uncertainty)
        forged = normalize_recording_clock('2026-10-14T12:00:00Z')
        forged['status'] = 'verified'
        with self.assertRaises(ValueError):
            validate_recording_clock(forged)
        forged = normalize_recording_clock('2026-10-14T12:00:00Z')
        forged['start_epoch'] = 10**1000
        with self.assertRaises(ValueError):
            validate_recording_clock(forged)
        valid = normalize_recording_clock('2026-10-14T12:00:00Z')
        self.assertEqual(source_capture_clock_fields(valid, -1), {})
        self.assertEqual(source_capture_clock_fields(valid, 86401), {})


if __name__ == '__main__':
    unittest.main()
