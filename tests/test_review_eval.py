import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from evaluate_review import evaluate_review_manifests


class ReviewEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "observations.sqlite3"
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "CREATE TABLE observations (camera TEXT, kind TEXT, plate TEXT, data TEXT)"
            )

    def manifest(self, label="KL07AB1234", readability="readable"):
        crop = self.root / "crop.jpg"
        crop.write_bytes(b"synthetic crop bytes")
        digest = hashlib.sha256(crop.read_bytes()).hexdigest()
        sample = {
            "sample_id": "CAM-07-TEST",
            "camera_id": "CAM-07",
            "crop_path": crop.name,
            "crop_sha256": digest,
            "source_sha256": "a" * 64,
            "session_id": "session-test",
            "frame_id": 12,
            "crop_bbox": [1, 2, 20, 12],
            "ground_truth_status": "reviewed",
            "plate_readability": readability,
            "ground_truth_plate": label if readability == "readable" else None,
        }
        path = self.root / "review.json"
        path.write_text(json.dumps({"samples": [sample]}))
        return path, sample

    def add_read(self, sample, plate_raw, session_id=None, **extra):
        data = {
            "camera_id": sample["camera_id"],
            "session_id": session_id or sample["session_id"],
            "frame_id": sample["frame_id"],
            "source_sha256": sample["source_sha256"],
            "bbox": sample["crop_bbox"],
            "plate_raw": plate_raw,
            **extra,
            "artifacts": [{
                "role": "plate-crop",
                "sha256": sample["crop_sha256"],
                "camera_id": sample["camera_id"],
                "session_id": sample["session_id"],
                "frame_id": sample["frame_id"],
                "source_sha256": sample["source_sha256"],
                "crop_bbox": sample["crop_bbox"],
            }],
        }
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "INSERT INTO observations VALUES (?, 'plate', NULL, ?)",
                (sample["camera_id"], json.dumps(data)),
            )

    def test_exact_crop_match_emits_aggregate_only(self):
        path, sample = self.manifest()
        self.add_read(sample, "KL 07 AB 1234")
        report = evaluate_review_manifests([path], self.database)
        self.assertEqual(report["reviewed_crop_summary"]["exact_match"], 1)
        serialized = json.dumps(report)
        self.assertNotIn("KL07AB1234", serialized)
        self.assertNotIn("KL 07 AB 1234", serialized)
        self.assertFalse(report["accuracy_claim_allowed"])

    def test_same_frame_without_exact_session_crop_reference_is_not_compared(self):
        path, sample = self.manifest()
        self.add_read(sample, "KL07AB1234", session_id="different-session")
        report = evaluate_review_manifests([path], self.database)
        self.assertEqual(report["reviewed_crop_summary"]["missing_output"], 1)

    def test_disagreement_between_repeated_exact_crop_reads_is_separate(self):
        path, sample = self.manifest()
        self.add_read(sample, "KL07AB1234")
        self.add_read(sample, "KL07AB1235")
        report = evaluate_review_manifests([path], self.database)
        self.assertEqual(report["reviewed_crop_summary"]["inconsistent_output"], 1)
        self.assertNotIn("mismatch", report["reviewed_crop_summary"])

    def test_unreadable_sample_is_excluded_from_exact_comparison(self):
        path, sample = self.manifest(readability="unreadable")
        self.add_read(sample, "WRONG00000")
        report = evaluate_review_manifests([path], self.database)
        self.assertEqual(report["reviewed_crop_summary"]["unreadable"], 1)
        self.assertNotIn("readable", report["reviewed_crop_summary"])

    def test_changed_crop_bytes_make_label_invalid(self):
        path, sample = self.manifest()
        (self.root / sample["crop_path"]).write_bytes(b"changed crop bytes")
        report = evaluate_review_manifests([path], self.database)
        self.assertEqual(report["reviewed_crop_summary"]["invalid_sample"], 1)

    def test_wrong_read_is_counted_as_rejected_only_with_explicit_status(self):
        path, sample = self.manifest()
        self.add_read(sample, "WRONG00000", format_valid=False, identity_status="invalid")
        report = evaluate_review_manifests([path], self.database)
        self.assertEqual(report["reviewed_crop_summary"]["mismatch_rejected_by_pipeline"], 1)
        self.assertNotIn("mismatch_not_proven_rejected", report["reviewed_crop_summary"])

    def test_wrong_read_without_rejection_evidence_is_not_assumed_rejected(self):
        path, sample = self.manifest()
        self.add_read(sample, "WRONG00000", format_valid=True, identity_status="supported")
        report = evaluate_review_manifests([path], self.database)
        self.assertEqual(report["reviewed_crop_summary"]["mismatch_not_proven_rejected"], 1)
        self.assertNotIn("mismatch_rejected_by_pipeline", report["reviewed_crop_summary"])


if __name__ == "__main__":
    unittest.main()
