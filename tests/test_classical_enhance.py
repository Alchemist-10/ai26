import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

import cv2
import numpy as np


MODULE_PATH = Path(__file__).parents[1] / "evaluation" / "classical_enhance.py"
spec = importlib.util.spec_from_file_location("classical_enhance", MODULE_PATH)
enhance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enhance)


class ClassicalEnhanceTests(unittest.TestCase):
    def test_transforms_return_valid_bgr_uint8_images(self):
        image = np.zeros((48, 64, 3), dtype=np.uint8)
        image[:, :32] = (25, 60, 100)
        image[:, 32:] = (120, 170, 220)
        for transform in enhance.TRANSFORMS.values():
            result = transform(image)
            self.assertEqual(result.shape, image.shape)
            self.assertEqual(result.dtype, np.uint8)

    def test_grayscale_contrast_transform_matches_pinned_parameters(self):
        image = np.full((8, 12, 3), (30, 60, 90), dtype=np.uint8)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        expected = cv2.cvtColor(cv2.convertScaleAbs(gray, alpha=1.5, beta=-25), cv2.COLOR_GRAY2BGR)
        result = enhance.grayscale_contrast(image)
        self.assertTrue(np.array_equal(result, expected))
        self.assertFalse(np.array_equal(result, image))


    def test_cli_creates_labeled_derivatives_and_preserves_source(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            tmp_path = Path(temp)
            source = tmp_path / "raw.png"
            image = np.full((32, 40, 3), (30, 50, 70), dtype=np.uint8)
            image[8:24, 10:30] = (180, 200, 220)
            self.assertTrue(cv2.imwrite(str(source), image))
            before = hashlib.sha256(source.read_bytes()).hexdigest()

            manifest_path = enhance.run(source, tmp_path / "derived", ["clahe", "gamma", "grayscale_contrast", "unsharp"])

            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["source"]["sha256"], before)
            self.assertEqual(manifest["source"]["status"], "raw_reference_unchanged")
            self.assertFalse(manifest["accuracy_claim"])
            self.assertEqual(manifest["quality_metrics"]["type"], "descriptive_only_not_accuracy")
            self.assertEqual([item["method"] for item in manifest["derivatives"]], ["clahe", "gamma", "grayscale_contrast", "unsharp"])
            for item in manifest["derivatives"]:
                output = manifest_path.parent / item["path"]
                self.assertEqual(item["status"], "research_derivative")
                self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), item["sha256"])
                decoded = cv2.imread(str(output))
                self.assertEqual(decoded.shape, image.shape)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)


    def test_existing_output_is_never_overwritten(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            tmp_path = Path(temp)
            source = tmp_path / "raw.png"
            cv2.imwrite(str(source), np.zeros((8, 8, 3), dtype=np.uint8))
            output = tmp_path / "derived"
            output.mkdir()
            derivative = output / "raw.gamma.png"
            derivative.write_bytes(b"keep-me")
            with self.assertRaises(FileExistsError):
                enhance.run(source, output, ["gamma"])
            self.assertEqual(derivative.read_bytes(), b"keep-me")


    def test_invalid_inputs_and_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            enhance.gamma_correct(np.zeros((4, 4), dtype=np.uint8))
        with self.assertRaises(ValueError):
            enhance.gamma_correct(np.zeros((4, 4, 3), dtype=np.uint8), gamma=9)
        with self.assertRaises(ValueError):
            enhance.grayscale_contrast(np.zeros((4, 4), dtype=np.uint8))
        with self.assertRaises(ValueError):
            enhance.grayscale_contrast(np.zeros((4, 4, 3), dtype=np.uint8), alpha=9)
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            tmp_path = Path(temp)
            source = tmp_path / "raw.png"
            cv2.imwrite(str(source), np.zeros((4, 4, 3), dtype=np.uint8))
            with self.assertRaises(ValueError):
                enhance.run(source, tmp_path, ["gamma"])


if __name__ == "__main__":
    unittest.main()
