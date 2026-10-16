import os
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fastapi.testclient import TestClient
import main
import privacy
import inference


class PrivacyMode(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.key = Path(self.folder.name) / "privacy.key"
        self.key.write_bytes(b"a" * 32)
        self.key.chmod(0o600)
        self.env = patch.dict(os.environ, {
            "AI26_PRIVACY_ENABLED": "1",
            "AI26_PRIVACY_KEY_FILE": str(self.key),
            "AI26_PROCESSING_ENABLED": "0",
            "AI26_AUTH_ENABLED": "0",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self._clear_key_cache)

    def _clear_key_cache(self):
        privacy._cached_path = None
        privacy._cached_key = None

    def test_alias_is_stable_keyed_and_payload_copy_preserves_storage_value(self):
        raw = "KA03MN1234"
        original = {"plate_norm": raw, "summary": f"vehicle {raw} seen"}
        with patch.dict(os.environ, {"AI26_PRIVACY_KEY_FILE": str(self.key)}):
            alias = privacy.plate_alias(raw)
            redacted = privacy.redact_analytics_payload(original)
            self.assertEqual(alias, privacy.plate_alias(raw))
            self.assertTrue(alias.startswith("PLATE-"))
            self.assertEqual(redacted["plate_norm"], alias)
            self.assertIn(alias, redacted["summary"])
            self.assertEqual(original["plate_norm"], raw)
            second = Path(self.folder.name) / "other.key"
            second.write_bytes(b"b" * 32); second.chmod(0o600)
            with patch.dict(os.environ, {"AI26_PRIVACY_KEY_FILE": str(second)}):
                privacy._cached_path = None; privacy._cached_key = None
                self.assertNotEqual(alias, privacy.plate_alias(raw))

    def test_key_rejects_weak_or_broad_permissions(self):
        with patch.dict(os.environ, {"AI26_PRIVACY_KEY_FILE": str(self.key)}):
            self.key.chmod(0o644)
            privacy._cached_path = None; privacy._cached_key = None
            with self.assertRaisesRegex(RuntimeError, "group or other"):
                privacy.validate_configuration()
            self.key.chmod(0o600); self.key.write_bytes(b"weak")
            privacy._cached_path = None; privacy._cached_key = None
            with self.assertRaisesRegex(RuntimeError, "32 random bytes"):
                privacy.validate_configuration()

    def test_pixelation_changes_only_detected_roi(self):
        frame = np.full((40, 60, 3), 127, dtype=np.uint8)
        frame[10:30, 10:30] = np.arange(20 * 20, dtype=np.uint8).reshape(20, 20, 1)
        before = frame.copy()
        privacy.pixelate_person_boxes(frame, [[10, 10, 30, 30]], padding=0)
        self.assertFalse(np.array_equal(frame[10:30, 10:30], before[10:30, 10:30]))
        self.assertTrue(np.array_equal(frame[:8], before[:8]))
        self.assertTrue(np.array_equal(frame[:, 40:], before[:, 40:]))

    def test_privacy_vehicle_preview_pixelates_the_detected_person_region(self):
        class EmptyTracker:
            def update(self, detections, timestamp=None):
                return []

        class PersonDetector:
            names = {0: "person"}

            def predict(self, frame, **kwargs):
                box = SimpleNamespace(cls=[0], conf=[0.99], xyxy=[[10, 10, 30, 30]])
                return [SimpleNamespace(boxes=[box])]

        camera = "PRIVACY-TEST"
        self.addCleanup(inference.reset_camera, camera)
        frame = np.zeros((48, 48, 3), dtype=np.uint8)
        frame[8:32, 8:32] = np.arange(24 * 24, dtype=np.uint8).reshape(24, 24, 1)
        before = frame.copy()
        trackers = defaultdict(EmptyTracker)
        trackers[camera] = EmptyTracker()
        with patch.object(inference, "_vehicle_model", return_value=PersonDetector()), \
             patch.object(inference, "_vehicle_trackers", trackers), \
             patch.object(inference, "privacy_enabled", return_value=True):
            observed, detections = inference.annotate_vehicle_frame(frame, camera)

        self.assertEqual(detections, [])
        self.assertEqual(inference._person_boxes[camera], [[10, 10, 30, 30]])
        self.assertFalse(np.array_equal(observed[8:32, 8:32], before[8:32, 8:32]))
        self.assertTrue(np.array_equal(observed[:6], before[:6]))

    def test_api_reports_privacy_and_blocks_raw_playback(self):
        client = TestClient(main.app)
        with client:
            self.assertTrue(client.get("/api/privacy/status").json()["enabled"])
            cameras = client.get("/api/cameras").json()
            self.assertTrue(cameras)
            self.assertTrue(all(camera["health"]["processing_enabled"] is False for camera in cameras))
            response = client.get("/api/video/CAM-07")
            self.assertEqual(response.status_code, 403)

    def test_events_api_redacts_plate_values_and_alert_text(self):
        raw = "KA03MN1234"
        with patch.object(main, "get_events", return_value=[{"plate": raw, "summary": f"matched {raw}"}]):
            with TestClient(main.app) as client:
                response = client.get("/api/events")
        self.assertEqual(response.status_code, 200)
        body = response.json()[0]
        self.assertEqual(body["plate"], privacy.plate_alias(raw))
        self.assertNotIn(raw, body["summary"])


if __name__ == "__main__":
    unittest.main()
