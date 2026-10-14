"""Pinned model configuration is explicit, path-free in health, and fail-closed."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import model_rollout


class ModelRolloutTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.stable = self.root / "stable.pt"
        self.candidate = self.root / "candidate.pt"
        self.stable.write_bytes(b"stable checkpoint bytes")
        self.candidate.write_bytes(b"canary checkpoint bytes")
        self.stable_sha = hashlib.sha256(self.stable.read_bytes()).hexdigest()
        self.candidate_sha = hashlib.sha256(self.candidate.read_bytes()).hexdigest()

    def settings(self):
        return {
            "AI26_VEHICLE_MODEL_PATH": str(self.stable),
            "AI26_VEHICLE_MODEL_SHA256": self.stable_sha,
            "AI26_VEHICLE_CANARY_MODEL_PATH": str(self.candidate),
            "AI26_VEHICLE_CANARY_MODEL_SHA256": self.candidate_sha,
            "AI26_VEHICLE_CANARY_CAMERAS": "CAM-01, CAM-03",
        }

    def test_canary_assignment_is_camera_pinned_and_health_hides_paths(self):
        config = model_rollout.load_configuration(self.settings(), {"CAM-01", "CAM-02", "CAM-03"})
        self.assertEqual(model_rollout.profile_for_camera(config, "CAM-01"), "canary")
        self.assertEqual(model_rollout.profile_for_camera(config, "CAM-02"), "stable")
        self.assertEqual(config["canary"]["camera_ids"], ("CAM-01", "CAM-03"))
        health = model_rollout.status(config)
        self.assertEqual(health["mode"], "camera_allowlist_canary")
        self.assertEqual(health["canary"]["expected_sha256"], self.candidate_sha)
        self.assertNotIn(str(self.root), str(health))
        self.assertIn("restart", health["rollback"])

    def test_candidate_must_be_complete_and_known(self):
        config = self.settings()
        del config["AI26_VEHICLE_CANARY_CAMERAS"]
        with self.assertRaisesRegex(RuntimeError, "configured together"):
            model_rollout.load_configuration(config, {"CAM-01"})
        config = self.settings()
        config["AI26_VEHICLE_CANARY_CAMERAS"] = "CAM-99"
        with self.assertRaisesRegex(RuntimeError, "unknown camera"):
            model_rollout.load_configuration(config)

    def test_custom_stable_requires_valid_pin_and_candidate_path(self):
        config = self.settings()
        del config["AI26_VEHICLE_MODEL_SHA256"]
        with self.assertRaisesRegex(RuntimeError, "is required with"):
            model_rollout.load_configuration(config)
        config = self.settings()
        config["AI26_VEHICLE_CANARY_MODEL_SHA256"] = "A" * 64
        with self.assertRaisesRegex(RuntimeError, "lowercase SHA-256"):
            model_rollout.load_configuration(config)
        config = self.settings()
        config["AI26_VEHICLE_CANARY_MODEL_PATH"] = str(self.root / "missing.pt")
        with self.assertRaisesRegex(RuntimeError, "readable model file"):
            model_rollout.load_configuration(config)

    def test_allowlist_rejects_duplicate_camera_ids(self):
        config = self.settings()
        config["AI26_VEHICLE_CANARY_CAMERAS"] = "CAM-01,CAM-01"
        with self.assertRaisesRegex(RuntimeError, "unique camera IDs"):
            model_rollout.load_configuration(config, {"CAM-01"})


if __name__ == "__main__":
    unittest.main()
