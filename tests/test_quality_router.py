import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np


MODULE_PATH = Path(__file__).parents[1] / "evaluation" / "quality_router.py"
spec = importlib.util.spec_from_file_location("quality_router", MODULE_PATH)
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


class QualityRouterTests(unittest.TestCase):
    def test_dark_flat_image_gets_candidates_without_weather_or_accuracy_claim(self):
        image = np.full((64, 64, 3), 24, dtype=np.uint8)
        report = router.inspect(image)
        self.assertIn("low_light_possible", report["flags"])
        self.assertIn("low_contrast_possible", report["flags"])
        self.assertIn("gamma", report["enhancement_candidates"])
        self.assertIn("clahe", report["enhancement_candidates"])
        self.assertEqual(report["weather_assessment"], "possible_haze_or_fog_like_appearance")
        self.assertFalse(report["weather_is_verified"])
        self.assertTrue(report["raw_reference_retained"])
        self.assertFalse(report["accuracy_claim"])

    def test_high_contrast_image_does_not_recommend_dehazing(self):
        image = np.zeros((64, 64, 3), dtype=np.uint8)
        image[:, 32:] = 255
        report = router.inspect(image)
        self.assertNotIn("dark_channel", report["enhancement_candidates"])
        self.assertEqual(report["weather_assessment"], "undetermined")

    def test_file_report_is_hashed_read_only_and_reports_invalid_data(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "raw.png"
            image = np.zeros((16, 16, 3), dtype=np.uint8)
            self.assertTrue(cv2.imwrite(str(source), image))
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            report = router.run(source)
            self.assertEqual(report["source"]["sha256"], before)
            self.assertEqual(report["source"]["status"], "read_only_raw_reference")
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        with self.assertRaises(ValueError):
            router.inspect(np.zeros((8, 8), dtype=np.uint8))


if __name__ == "__main__":
    unittest.main()
