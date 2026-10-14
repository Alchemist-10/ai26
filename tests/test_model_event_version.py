"""Persisted model versions follow exact loaded provenance with legacy fallback."""
from pathlib import Path
import os
import sys
import unittest

os.environ.setdefault("AI26_PROCESSING_ENABLED", "0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from processing import model_version_for_detection


class ModelEventVersionTests(unittest.TestCase):
    def test_exact_loaded_model_id_is_persisted_and_legacy_reads_keep_fallback(self):
        digest = "a" * 64
        self.assertEqual(model_version_for_detection({
            "kind": "vehicle", "model_metadata": {"model_id": f"ultralytics-yolo:canary:{digest}"}
        }), f"ultralytics-yolo:canary:{digest}")
        self.assertEqual(model_version_for_detection({"kind": "vehicle"}), "yolov8n.pt")
        self.assertEqual(model_version_for_detection({"kind": "plate"}),
                         "fast-alpr:global-plates-mobile-vit-v2")


if __name__ == "__main__":
    unittest.main()
