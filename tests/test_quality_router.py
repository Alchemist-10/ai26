import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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

    def test_plate_box_gets_independent_review_only_quality_hints(self):
        image = np.full((100, 100, 3), 128, dtype=np.uint8)
        image[20:60, 30:80] = 24
        original = image.copy()
        report = router.inspect(image, [(30, 20, 80, 60)])
        region, = report["plate_region_assessments"]
        self.assertEqual(report["features"]["mean_luminance"], 107.2)
        self.assertGreater(report["features"]["mean_luminance"], 70)
        self.assertEqual(region["box_xyxy"], [30, 20, 80, 60])
        self.assertEqual((region["width"], region["height"]), (50, 40))
        self.assertLess(region["features"]["mean_luminance"], 70)
        self.assertIn("gamma", region["suggested_ocr_preprocessing"])
        self.assertEqual(region["suggested_ocr_preprocessing"][0], "raw")
        self.assertEqual(region["routing_status"], "review_only_no_live_route")
        self.assertFalse(region["weather_is_assessed"])
        self.assertTrue(report["raw_reference_retained"])
        self.assertTrue(np.array_equal(image, original))

    def test_plate_boxes_reject_invalid_or_out_of_bounds_coordinates(self):
        image = np.zeros((16, 16, 3), dtype=np.uint8)
        for box in ((0, 0, 0, 8), (-1, 0, 4, 4), (0, 0, 17, 4), (1, 1, 4.5, 5)):
            with self.subTest(box=box), self.assertRaises(ValueError):
                router.inspect(image, [box])
        with self.assertRaises(router.argparse.ArgumentTypeError):
            router.parse_plate_box("1,2,3")

    def test_file_report_is_hashed_read_only_and_reports_invalid_data(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "raw.png"
            image = np.zeros((16, 16, 3), dtype=np.uint8)
            self.assertTrue(cv2.imwrite(str(source), image))
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            report = router.run(source, [(0, 0, 8, 8)])
            self.assertEqual(report["source"]["sha256"], before)
            self.assertEqual(report["source"]["status"], "read_only_raw_reference")
            self.assertEqual(len(report["plate_region_assessments"]), 1)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        with self.assertRaises(ValueError):
            router.inspect(np.zeros((8, 8), dtype=np.uint8))

    def test_optional_detector_boxes_are_clipped_hashed_and_never_store_ocr_text(self):
        class FakeModel:
            def predict(self, image):
                self.shape = image.shape
                return [SimpleNamespace(
                    detection=SimpleNamespace(bounding_box=SimpleNamespace(x1=-2, y1=2, x2=12, y2=15)),
                    ocr=SimpleNamespace(text="SENSITIVE-PLATE-TEXT"),
                )]

        model = FakeModel()
        calls = []
        def load_model(**kwargs):
            calls.append(kwargs)
            return model, {"weight_provenance_status": "hashed_loaded_files", "model_files": [
                {"role": "detector", "sha256": "a" * 64}
            ]}

        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "raw.png"
            self.assertTrue(cv2.imwrite(str(source), np.full((16, 16, 3), 120, dtype=np.uint8)))
            report = router.run(source, detect_plates=True, model_loader=load_model)
            region, = report["plate_region_assessments"]
            self.assertEqual(region["box_xyxy"], [0, 2, 12, 15])
            self.assertEqual(report["plate_box_source"], "selected_alpr_detector")
            self.assertEqual(report["plate_model_metadata"]["weight_provenance_status"], "hashed_loaded_files")
            self.assertEqual(calls, [{"cpu_threads": 2, "device": "cpu"}])
            self.assertEqual(model.shape, (16, 16, 3))
            self.assertNotIn("SENSITIVE-PLATE-TEXT", json.dumps(report))

    def test_detector_no_candidate_result_is_explicit_and_keeps_model_provenance(self):
        class EmptyModel:
            def predict(self, image): return []

        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "raw.png"
            self.assertTrue(cv2.imwrite(str(source), np.zeros((8, 8, 3), dtype=np.uint8)))
            report = router.run(source, detect_plates=True,
                                model_loader=lambda **kwargs: (EmptyModel(), {"model_id": "test-detector"}))
            self.assertEqual(report["plate_region_assessments"], [])
            self.assertEqual(report["plate_box_source"], "selected_alpr_detector_no_candidates")
            self.assertEqual(report["plate_model_metadata"], {"model_id": "test-detector"})

    def test_manual_and_automatic_boxes_cannot_be_mixed(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "raw.png"
            self.assertTrue(cv2.imwrite(str(source), np.zeros((8, 8, 3), dtype=np.uint8)))
            with self.assertRaisesRegex(ValueError, "cannot be combined"):
                router.run(source, [(0, 0, 4, 4)], detect_plates=True,
                           model_loader=lambda **kwargs: self.fail("model must not load"))


if __name__ == "__main__":
    unittest.main()
