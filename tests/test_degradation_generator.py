import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np


MODULE_PATH = Path(__file__).parents[1] / "evaluation" / "degradation_generator.py"
spec = importlib.util.spec_from_file_location("degradation_generator", MODULE_PATH)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class DegradationGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.image = np.zeros((64, 80, 3), dtype=np.uint8)
        self.image[:, :40] = (40, 70, 100)
        self.image[:, 40:] = (150, 180, 210)

    def test_all_conditions_are_deterministic_valid_derivatives(self):
        for condition in generator.CONDITIONS:
            with self.subTest(condition=condition):
                first, metadata = generator.degrade(self.image, condition, 0.65, 83)
                second, _ = generator.degrade(self.image, condition, 0.65, 83)
                self.assertEqual(first.shape, self.image.shape)
                self.assertEqual(first.dtype, np.uint8)
                self.assertTrue(np.array_equal(first, second))
                self.assertFalse(np.array_equal(first, self.image))
                self.assertEqual(metadata["condition"], condition)
                self.assertEqual(metadata["seed"], 83)

    def test_stochastic_conditions_change_with_seed(self):
        for condition in ("rain", "sensor_noise"):
            with self.subTest(condition=condition):
                first, _ = generator.degrade(self.image, condition, 0.8, 12)
                second, _ = generator.degrade(self.image, condition, 0.8, 13)
                self.assertFalse(np.array_equal(first, second))
        _, first = generator.degrade(self.image, "motion_blur", 0.8, 12)
        _, second = generator.degrade(self.image, "motion_blur", 0.8, 13)
        self.assertNotEqual(first["angle_degrees"], second["angle_degrees"])

    def test_invalid_inputs_are_rejected(self):
        for invalid in (np.zeros((4, 4), dtype=np.uint8), np.zeros((4, 4, 3), dtype=np.float32)):
            with self.subTest(shape=invalid.shape, dtype=invalid.dtype):
                with self.assertRaises(ValueError):
                    generator.degrade(invalid, "fog")
        for severity in (0, -0.1, 1.1, float("nan"), True):
            with self.subTest(severity=severity):
                with self.assertRaises(ValueError):
                    generator.degrade(self.image, "fog", severity)
        with self.assertRaises(ValueError):
            generator.degrade(self.image, "snow")
        with self.assertRaises(ValueError):
            generator.degrade(self.image, "fog", seed=-1)

    def test_run_writes_hashed_labeled_derivative_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "raw.png"
            output = root / "derived.png"
            self.assertTrue(cv2.imwrite(str(source), self.image))
            source_bytes = source.read_bytes()
            source_hash = hashlib.sha256(source_bytes).hexdigest()

            manifest_path = generator.run(source, output, "fog", 0.7, 4)
            manifest = json.loads(manifest_path.read_text())

            self.assertEqual(manifest["source"]["sha256"], source_hash)
            self.assertEqual(manifest["derivative"]["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(manifest["derivative"]["status"], "synthetic_degraded_derivative")
            self.assertFalse(manifest["condition_is_observed_weather"])
            self.assertFalse(manifest["accuracy_claim"])
            self.assertEqual(source.read_bytes(), source_bytes)

            with self.assertRaises(FileExistsError):
                generator.run(source, output, "fog", 0.7, 4)
            with self.assertRaises(ValueError):
                generator.run(source, root / "misleading.jpg", "fog")
            with self.assertRaises(ValueError):
                generator.run(source, source, "fog")


if __name__ == "__main__":
    unittest.main()
