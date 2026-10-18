import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evaluation"))
import promotion_gate


POLICY = {
    "schema_version": 1,
    "minimum_test_frames": 3,
    "minimum_labeled_boxes": 10,
    "minimum_labeled_plates": 3,
    "minimum_detection_precision": 0.9,
    "minimum_detection_recall": 0.9,
    "minimum_plate_exact_match_rate": 0.5,
    "maximum_false_positives_per_100_objects": 10.0,
    "maximum_false_reads_per_100_plates": 25.0,
    "maximum_detection_precision_drop": 0.02,
    "maximum_detection_recall_drop": 0.02,
    "maximum_plate_exact_match_drop": 0.1,
    "maximum_false_positive_rate_increase": 0.02,
    "maximum_false_read_rate_increase": 0.1,
}


class ModelPromotionGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "manifest.json"
        clips = []
        for split in ("train", "validation", "test"):
            name = f"{split}.mp4"
            data = f"fixture clip {split}".encode()
            (self.root / name).write_bytes(data)
            clips.append({
                "clip_id": split,
                "split": split,
                "camera_id": f"CAM-{len(clips) + 1:02d}",
                "location_id": f"junction-{split}",
                "session_id": f"session-{split}",
                "vehicles": [{"vehicle_id": f"vehicle-{split}", "plate_label": "readable",
                              "plate_text": "KL07AB1234", "labeled_frames": 1}],
                "coordinate_status": "unverified",
                "coordinate_evidence": "not surveyed",
                "coordinates": None,
                "capture_clock_status": "unknown",
                "capture_clock_metadata": {"method": "unknown", "timezone": "Asia/Kolkata",
                                           "reason": "fixture"},
                "clock_sync_status": "unknown",
                "conditions": {"weather": "clear", "lighting": "day", "plate_visibility": "readable"},
                "labels_complete": True,
                "negative_frames_labeled": True,
                "path": name,
                "sha256": hashlib.sha256(data).hexdigest(),
            })
        self.manifest.write_text(json.dumps({
            "schema_version": 1,
            "dataset_id": "test-fixture",
            "split_dimensions": ["vehicle_id", "camera_id", "location_id", "session_id"],
            "clips": clips,
            "missing_inputs": [],
        }), encoding="utf-8")
        self.manifest_sha = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.stable_sha = "1" * 64
        self.candidate_sha = "2" * 64
        self.stable_report = self.root / "stable.json"
        self.candidate_report = self.root / "candidate.json"
        self.stable_records = self.root / "stable.jsonl"
        self.candidate_records = self.root / "candidate.jsonl"
        self.stable_records.write_text("stable prediction records\n", encoding="utf-8")
        self.candidate_records.write_text("candidate prediction records\n", encoding="utf-8")
        self.write_report(self.stable_report, self.stable_sha, tp=10, fp=1, fn=1,
                          exact=2, false_reads=0, abstentions=1)
        self.write_report(self.candidate_report, self.candidate_sha, tp=10, fp=0, fn=0,
                          exact=2, false_reads=0, abstentions=1)

    def write_report(self, path, model_sha, *, tp, fp, fn, exact, false_reads, abstentions,
                     synthetic=False, manifest_sha=None, records_path=None):
        records_path = records_path or (self.candidate_records if model_sha == self.candidate_sha else self.stable_records)
        path.write_text(json.dumps({
            "synthetic": synthetic,
            "sample_count": 3,
            "detector": {"tp": tp, "fp": fp, "fn": fn},
            "plates": {"labeled_samples": 3, "exact_matches": exact,
                       "false_reads": false_reads, "abstentions": abstentions},
            "provenance": {"schema_version": 1, "manifest_sha256": manifest_sha or self.manifest_sha,
                           "model_sha256": model_sha,
                           "records_sha256": hashlib.sha256(records_path.read_bytes()).hexdigest(),
                           "sample_ids_sha256": hashlib.sha256(b"sample-1\nsample-2\nsample-3").hexdigest(),
                           "test_split_only": True, "record_count": 3},
        }), encoding="utf-8")

    def run_gate(self, policy=None):
        return promotion_gate.evaluate_gate(
            manifest_path=self.manifest,
            stable_report_path=self.stable_report,
            candidate_report_path=self.candidate_report,
            stable_records_path=self.stable_records,
            candidate_records_path=self.candidate_records,
            policy=POLICY if policy is None else policy,
            stable_model_sha256=self.stable_sha,
            candidate_model_sha256=self.candidate_sha,
        )

    def test_paired_real_reports_pass_without_performing_promotion(self):
        report = self.run_gate()
        self.assertTrue(report["eligible"])
        self.assertFalse(report["promotion_performed"])
        self.assertEqual(report["candidate"]["detection_precision"], 1)

    def test_absolute_accuracy_floor_and_noninferiority_can_reject_candidate(self):
        self.write_report(self.candidate_report, self.candidate_sha, tp=8, fp=3, fn=2,
                          exact=1, false_reads=1, abstentions=1)
        report = self.run_gate()
        self.assertFalse(report["eligible"])
        self.assertTrue(any(not check["passed"] for check in report["checks"]))

    def test_synthetic_reports_are_never_eligible(self):
        self.write_report(self.candidate_report, self.candidate_sha, tp=10, fp=0, fn=0,
                          exact=2, false_reads=0, abstentions=1, synthetic=True)
        with self.assertRaisesRegex(promotion_gate.GateError, "synthetic"):
            self.run_gate()

    def test_hash_mismatch_and_same_model_are_rejected(self):
        self.write_report(self.candidate_report, self.candidate_sha, tp=10, fp=0, fn=0,
                          exact=2, false_reads=0, abstentions=1, manifest_sha="0" * 64)
        with self.assertRaisesRegex(promotion_gate.GateError, "supplied manifest"):
            self.run_gate()
        with self.assertRaisesRegex(promotion_gate.GateError, "must differ"):
            promotion_gate.evaluate_gate(
                manifest_path=self.manifest, stable_report_path=self.stable_report,
                candidate_report_path=self.stable_report, stable_records_path=self.stable_records,
                candidate_records_path=self.stable_records, policy=POLICY,
                stable_model_sha256=self.stable_sha, candidate_model_sha256=self.stable_sha,
            )

    def test_equal_counts_do_not_allow_different_test_samples(self):
        report = json.loads(self.candidate_report.read_text())
        report["provenance"]["sample_ids_sha256"] = "3" * 64
        self.candidate_report.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(promotion_gate.GateError, "exact same test sample IDs"):
            self.run_gate()

    def test_changed_prediction_records_invalidate_report(self):
        self.candidate_records.write_text("changed after evaluation\n", encoding="utf-8")
        with self.assertRaisesRegex(promotion_gate.GateError, "supplied prediction records"):
            self.run_gate()

    def test_operator_policy_must_be_complete_and_require_positive_plate_rate(self):
        with self.assertRaisesRegex(promotion_gate.GateError, "missing fields"):
            self.run_gate({"schema_version": 1})
        policy = dict(POLICY, minimum_plate_exact_match_rate=0)
        with self.assertRaisesRegex(promotion_gate.GateError, "positive exact-read rate"):
            self.run_gate(policy)

    def test_unready_manifest_is_rejected(self):
        document = json.loads(self.manifest.read_text())
        document["missing_inputs"] = [{"camera_id": "CAM-07", "reason": "footage absent"}]
        self.manifest.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(promotion_gate.GateError, "manifest is incomplete"):
            self.run_gate()

    def test_evaluator_binds_real_report_to_manifest_model_and_exact_samples(self):
        model_sha = "a" * 64
        records = self.root / "predictions.jsonl"
        records.write_text("\n".join(json.dumps({
            "sample_id": f"test-{index}",
            "clip_id": "test",
            "camera": "CAM-03",
            "session": "session-test",
            "frame_index": index,
            "model_sha256": model_sha,
            "expected_plate": "KL07AB1234",
            "predicted_plate": "KL07AB1234",
            "expected_boxes": [{"label": "car", "bbox": [0, 0, 20, 20]}],
            "predicted_boxes": [{"label": "car", "bbox": [0, 0, 20, 20]}],
        }) for index in range(2)) + "\n", encoding="utf-8")
        output = self.root / "evaluation.json"
        script = Path(__file__).resolve().parents[1] / "evaluation" / "evaluate.py"
        command = [sys.executable, str(script), "--records", str(records), "--manifest", str(self.manifest),
                   "--model-sha256", model_sha, "--output", str(output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["provenance"]["model_sha256"], model_sha)
        self.assertEqual(report["provenance"]["manifest_sha256"], self.manifest_sha)
        self.assertEqual(report["provenance"]["records_sha256"], hashlib.sha256(records.read_bytes()).hexdigest())
        self.assertEqual(report["provenance"]["record_count"], 2)

        rows = records.read_text(encoding="utf-8").splitlines()
        row = json.loads(rows[0]); row["model_sha256"] = "b" * 64
        rows[0] = json.dumps(row); records.write_text("\n".join(rows) + "\n", encoding="utf-8")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("model_sha256 does not match", result.stderr)


if __name__ == "__main__":
    unittest.main()
