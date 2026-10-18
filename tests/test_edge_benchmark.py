import importlib.util
from pathlib import Path
import unittest

import numpy as np


MODULE_PATH = Path(__file__).parents[1] / "evaluation" / "edge_benchmark.py"
spec = importlib.util.spec_from_file_location("edge_benchmark", MODULE_PATH)
edge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edge)


class EdgeBenchmarkHelpers(unittest.TestCase):
    def test_letterbox_is_rgb_normalized_bchw_and_preserves_aspect_ratio(self):
        image = np.zeros((40, 80, 3), dtype=np.uint8)
        image[:, :, 2] = 255  # red BGR input
        result = edge.letterbox_bgr(image, size=64)
        self.assertEqual(result.shape, (1, 3, 64, 64))
        self.assertEqual(result.dtype, np.float32)
        self.assertTrue(np.isfinite(result).all())
        self.assertEqual(float(result[0, 0, 32, 32]), 1.0)  # RGB red channel
        self.assertAlmostEqual(float(result[0, 0, 0, 0]), 114 / 255)

    def test_output_drift_reports_exact_agreement_and_shape_mismatch(self):
        reference = np.zeros((1, 5), dtype=np.float32)
        exact = edge._drift(reference, reference.copy())
        self.assertTrue(exact["same_shape"])
        self.assertEqual(exact["mean_absolute_difference"], 0)
        mismatch = edge._drift(reference, np.zeros((1, 6), dtype=np.float32))
        self.assertFalse(mismatch["same_shape"])

    def test_detection_agreement_requires_same_class_and_overlapping_box(self):
        ref = [{"class_id": 2, "xyxy": [0, 0, 10, 10]}]
        same = edge._match_detection_lists(ref, [{"class_id": 2, "xyxy": [1, 1, 11, 11]}])
        wrong_class = edge._match_detection_lists(ref, [{"class_id": 3, "xyxy": [0, 0, 10, 10]}])
        self.assertEqual(same["matched_count"], 1)
        self.assertEqual(wrong_class["matched_count"], 0)

    def test_no_replace_writer_preserves_existing_report(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.json"
            edge._write_no_replace(path, b"first")
            with self.assertRaises(FileExistsError):
                edge._write_no_replace(path, b"second")
            self.assertEqual(path.read_bytes(), b"first")


if __name__ == "__main__":
    unittest.main()
