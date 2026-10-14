import importlib.util
from pathlib import Path
import unittest

import cv2
import numpy as np


MODULE_PATH = Path(__file__).parents[1] / "evaluation" / "flow_align.py"
spec = importlib.util.spec_from_file_location("flow_align", MODULE_PATH)
flow_align = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow_align)


class FlowAlignmentTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(76)
        self.reference = rng.integers(0, 256, (128, 160, 3), dtype=np.uint8)

    def test_translation_is_aligned_and_never_claimed_as_identity_or_probability(self):
        transform = np.float32([[1, 0, 4], [0, 1, -3]])
        shifted = cv2.warpAffine(self.reference, transform, (160, 128), borderMode=cv2.BORDER_REFLECT_101)

        aligned, details = flow_align.align_to_reference(self.reference, shifted)
        before = np.mean(np.abs(self.reference.astype(np.float32) - shifted.astype(np.float32)))
        after = np.mean(np.abs(self.reference.astype(np.float32) - aligned.astype(np.float32)))

        self.assertEqual(aligned.shape, self.reference.shape)
        self.assertEqual(aligned.dtype, np.uint8)
        self.assertLess(after, before * 0.7)
        self.assertEqual(details["status"], "research_alignment")
        self.assertFalse(details["confidence_is_calibrated"])
        self.assertFalse(details["identity_inferred"])

    def test_burst_keeps_reference_and_aligns_each_other_frame(self):
        shifted = cv2.warpAffine(self.reference, np.float32([[1, 0, 2], [0, 1, 1]]), (160, 128))
        output, details = flow_align.align_burst([self.reference, shifted])
        self.assertEqual(len(output), 2)
        self.assertTrue(np.array_equal(output[0], self.reference))
        self.assertEqual(details[0]["status"], "unchanged_reference")
        self.assertEqual(details[1]["method"], "farneback_dense_optical_flow")

    def test_invalid_shapes_and_burst_bounds_are_rejected(self):
        with self.assertRaises(ValueError):
            flow_align.align_to_reference(self.reference, self.reference[:, :-1])
        with self.assertRaises(ValueError):
            flow_align.align_to_reference(self.reference, self.reference, window_size=4)
        with self.assertRaises(ValueError):
            flow_align.align_burst([self.reference])
        with self.assertRaises(ValueError):
            flow_align.align_burst([self.reference, self.reference], reference_index=2)


if __name__ == "__main__":
    unittest.main()
