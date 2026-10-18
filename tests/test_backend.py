"""Backend regression checks without loading ML models."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
import cameras
import events
import nlquery
from repository import Repository
from plate_format import normalize_plate
from tracking import CentroidTracker


class ImportChecks(unittest.TestCase):
    def setUp(self):
        self.repository = Repository(':memory:')
        self.storage = patch.object(events, 'store', self.repository)
        self.storage.start()
        self.addCleanup(self.storage.stop)
        self.addCleanup(self.repository.close)

    def observation(self, camera, ts, time_basis=None):
        result = {"camera_id": camera, "kind": "plate", "plate": "KL07AB1234",
                "plate_norm": "KL07AB1234", "plate_raw": "KL 07 AB 1234",
                "confidence": 0.9, "bbox": [1, 2, 3, 4], "ts": ts}
        if time_basis is not None:
            result["time_basis"] = time_basis
        return result

    def test_plate_normalization_and_repairs(self):
        self.assertEqual(normalize_plate("kl 07 ab 1234")["plate_norm"], "KL07AB1234")
        repaired = normalize_plate("OL08AF5030")
        self.assertEqual(repaired["plate_norm"], "DL08AF5030")
        self.assertTrue(repaired["repairs"])
        self.assertFalse(normalize_plate("garbage")["format_valid"])
        self.assertTrue(normalize_plate("24 BH 1234 AA")["format_valid"])

    def test_tracker_keeps_id_and_separates_classes(self):
        tracker = CentroidTracker(max_distance=20, max_missing=1)
        first = tracker.update([{"label": "car", "bbox": [0, 0, 20, 20]}])[0]
        second = tracker.update([{"label": "car", "bbox": [4, 0, 24, 20]}])[0]
        other = tracker.update([{"label": "bus", "bbox": [4, 0, 24, 20]}])[0]
        self.assertEqual(first["track_id"], second["track_id"])
        self.assertNotEqual(second["track_id"], other["track_id"])
        tracker.update([])
        tracker.update([])
        new = tracker.update([{"label": "car", "bbox": [4, 0, 24, 20]}])[0]
        self.assertNotEqual(first["track_id"], new["track_id"])

    def test_local_vehicle_proxies_exist(self):
        for number in range(1, 7):
            camera_id = f"CAM-{number:02}"
            self.assertTrue(cameras.camera_playback_source(camera_id).is_file())
            self.assertTrue(cameras.camera_source(camera_id).is_file())

    def test_ai26_configuration_is_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ, AI26_FOOTAGE_ROOT=folder, SAKSHI_FOOTAGE_ROOT="/unused/sih")
            result = subprocess.check_output(
                [sys.executable, "-c", "import cameras; print(cameras.FOOTAGE_ROOT)"],
                cwd=BACKEND, env=env, text=True,
            ).strip()
            self.assertEqual(result, folder)

    def test_source_and_playback_priorities(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "original.mp4"
            proxy = root / "CAM-01.mp4"
            proxy.touch()
            with patch.dict(cameras.CAMERAS_BY_ID, {"CAM-01": {"path": str(source)}}), patch.object(cameras, "PLAYBACK_ROOT", root):
                self.assertEqual(cameras.camera_source("CAM-01"), proxy)
                source.touch()
                self.assertEqual(cameras.camera_source("CAM-01"), source)
                self.assertEqual(cameras.camera_playback_source("CAM-01"), proxy)

    def test_trajectory_rejects_impossible_travel(self):
        now = time.time()
        for camera in ('CAM-07','CAM-08','CAM-09'):
            config=self.repository.camera_configuration(camera)
            self.repository.update_camera(camera,{**config,'expected_revision':config['revision'],'location_confirmed':True,
                'reviewer':'fixture','reason':'configure accepted-link test'},now)
        self.repository.put_camera_pair_constraint({'from_camera_id':'CAM-07','to_camera_id':'CAM-08',
            'min_travel_seconds':0,'max_travel_seconds':3600,'enabled':True,'reviewer':'fixture','reason':'reachable test pair'},now)
        self.repository.put_camera_pair_constraint({'from_camera_id':'CAM-07','to_camera_id':'CAM-09',
            'min_travel_seconds':0,'max_travel_seconds':3600,'enabled':True,'reviewer':'fixture','reason':'impossible travel test pair'},now)
        good = events.build_trajectory([self.observation("CAM-07", now - 120, 'synchronized_capture_clock'),
                                        self.observation("CAM-08", now, 'synchronized_capture_clock')])
        self.assertEqual(good["status"], "candidate")
        self.assertEqual(len(good["accepted_links"]), 1)
        bad = events.build_trajectory([self.observation("CAM-07", now - 1, 'synchronized_capture_clock'),
                                       self.observation("CAM-09", now, 'synchronized_capture_clock')])
        self.assertEqual(bad["status"], "review_required")
        self.assertIn("impossible travel", bad["rejected_links"][0]["reason"])

    def test_alerts_queries_evidence_share_observations(self):
        now = time.time()
        for camera in ('CAM-07','CAM-09'):
            config=self.repository.camera_configuration(camera)
            self.repository.update_camera(camera,{**config,'expected_revision':config['revision'],'location_confirmed':True,
                'reviewer':'fixture','reason':'configure deterministic route-alert fixture'},now)
        events.add_events([self.observation("CAM-07", now - 1, 'synchronized_capture_clock'),
                           self.observation("CAM-09", now, 'synchronized_capture_clock')])
        self.assertEqual(len(events.get_events(plate="kl 07 ab 1234")), 2)
        self.assertEqual(len(events.get_events(camera_id="CAM-07")), 1)
        self.assertEqual(events.stats()["total_events"], 2)
        types = {alert["type"] for alert in events.derive_alerts()}
        self.assertTrue({"watchlist match", "zone sighting", "route review"}.issubset(types))
        self.assertIn("KL07AB1234", nlquery.answer("plates at CAM-07")["text"])
        report = events.evidence_report("KL07AB1234")
        digest = report.pop("package_hash")
        payload = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
        self.assertEqual(len(report["trajectory"]["observations"]), 2)

    def test_event_buffer_bounds(self):
        now = time.time()
        events.add_events([self.observation("CAM-07", now - 400), self.observation("CAM-08", now)])
        self.assertEqual(len(events.get_events()), 1)
        with patch.object(events, "MAX_EVENTS", 2):
            events.add_events([self.observation("CAM-07", now), self.observation("CAM-09", now)])
            self.assertEqual(len(events.get_events()), 2)


if __name__ == "__main__":
    unittest.main()
