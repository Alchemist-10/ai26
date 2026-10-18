"""Review-set selection/provenance and no-clobber behavior on synthetic media."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

SPEC = importlib.util.spec_from_file_location("prepare_frame_review", Path(__file__).resolve().parents[1] / "evaluation/prepare_frame_review.py")
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class FrameReview(unittest.TestCase):
    def test_temporal_selection_is_spread_unique_and_bounded(self):
        self.assertEqual(review.sample_indices(100, 5), [10, 30, 50, 70, 90])
        self.assertEqual(review.sample_indices(5, 5), [0, 1, 2, 3, 4])
        for value in (0, -1, True, 21):
            with self.assertRaises(ValueError): review.sample_indices(100, value)

    def test_bundle_hashes_exact_sources_and_frames_without_human_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.avi"
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 5, (96, 64))
            self.assertTrue(writer.isOpened())
            for index in range(20): writer.write(np.full((64, 96, 3), index * 10, dtype=np.uint8))
            writer.release()
            output = root / "review"
            with contextlib.redirect_stdout(io.StringIO()):
                manifest = review.prepare([{"camera_id": "CAM-01", "path": source, "role": "original"}], output)
            self.assertEqual([s["frame_index"] for s in manifest["samples"]], [2, 6, 10, 14, 18])
            self.assertEqual(manifest["source_clips"][0]["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(manifest["source_clips"][0]["sequentially_counted_frames"], 20)
            labels = json.loads((output / "labels-template.json").read_text())
            for sample in manifest["samples"]:
                self.assertEqual(review.digest(output / sample["image"]), sample["image_sha256"])
                row = labels["annotations"][sample["sample_id"]]
                self.assertEqual(row["status"], "pending")
                self.assertIsNone(row["vehicle_count"])
                self.assertEqual(row["vehicles"], [])
            self.assertNotIn("/* REVIEW_PAYLOAD */ null", (output / "index.html").read_text())
            preserved = (output / "labels-template.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "already exists"):
                review.prepare([], output)
            self.assertEqual((output / "labels-template.json").read_bytes(), preserved)

    def test_failed_extraction_does_not_publish_partial_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "invalid.mp4"
            source.write_bytes(b"not media")
            with self.assertRaises(ValueError):
                review.prepare([{"camera_id": "CAM-01", "path": source}], root / "review")
            self.assertFalse((root / "review").exists())


if __name__ == "__main__": unittest.main()
