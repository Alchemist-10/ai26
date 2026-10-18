"""Pinned model configuration is explicit, path-free in health, and fail-closed."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

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

    def test_detector_preflight_checks_task_class_map_and_forward_result(self):
        detector = SimpleNamespace(
            task="detect",
            names={0:"person",2:"car",3:"motorcycle",5:"bus",7:"truck"},
            predict=Mock(return_value=[SimpleNamespace(boxes=SimpleNamespace(cls=np.asarray([],dtype=np.float32)))])
        )
        report = model_rollout.preflight_detector(detector, device="cpu", include_person=True)
        self.assertEqual(report, {
            "task":"detect", "class_map_status":"compatible", "preflight_status":"passed",
            "preflight_input":"synthetic_640x640_bgr", "required_class_ids":[0,2,3,5,7],
        })
        args,kwargs=detector.predict.call_args
        self.assertEqual(args[0].shape,(640,640,3))
        self.assertEqual(kwargs["classes"],[0,2,3,5,7])

    def test_detector_preflight_fails_closed_on_task_class_and_result_mismatch(self):
        base={0:"person",2:"car",3:"motorcycle",5:"bus",7:"truck"}
        for model in (
            SimpleNamespace(task="segment",names=base,predict=Mock()),
            SimpleNamespace(task="detect",names={**base,7:"airplane"},predict=Mock()),
            SimpleNamespace(task="detect",names={key:value for key,value in base.items() if key!=3},predict=Mock()),
        ):
            with self.subTest(model=model),self.assertRaises(RuntimeError):
                model_rollout.preflight_detector(model,device="cpu",include_person=True)

        no_boxes=SimpleNamespace(task="detect",names=base,
                                 predict=Mock(return_value=[SimpleNamespace(boxes=None)]))
        with self.assertRaisesRegex(RuntimeError,"detection boxes"):
            model_rollout.preflight_detector(no_boxes,device="cpu")

        wrong_class=SimpleNamespace(task="detect",names=base,
                                    predict=Mock(return_value=[SimpleNamespace(boxes=SimpleNamespace(cls=np.asarray([1]))) ]))
        with self.assertRaisesRegex(RuntimeError,"unsupported class ID"):
            model_rollout.preflight_detector(wrong_class,device="cpu")

        fractional_class=SimpleNamespace(task="detect",names=base,
                                         predict=Mock(return_value=[SimpleNamespace(boxes=SimpleNamespace(cls=np.asarray([2.5]))) ]))
        with self.assertRaisesRegex(RuntimeError,"invalid class tensor"):
            model_rollout.preflight_detector(fractional_class,device="cpu")

        invalid_map=SimpleNamespace(task="detect",names={2.5:"car",3:"motorcycle",5:"bus",7:"truck"},predict=Mock())
        with self.assertRaisesRegex(RuntimeError,"invalid class map"):
            model_rollout.preflight_detector(invalid_map,device="cpu")


if __name__ == "__main__":
    unittest.main()
