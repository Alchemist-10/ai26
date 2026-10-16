import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "evaluation" / "plate_fusion_eval.py"
spec = importlib.util.spec_from_file_location("plate_fusion_eval", MODULE_PATH)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def row(sample_id, camera, track, frame, expected, prediction, *, session="session-a", association="matched"):
    return {"sample_id": sample_id, "synthetic": True, "camera": camera, "session": session,
            "track_id": track, "frame_index": frame, "expected_plate": expected,
            "predicted_plate": prediction, "association_status": association, "confidence": .9}


class PlateFusionEvaluationTests(unittest.TestCase):
    def test_last_read_comparison_reports_conflict_abstention_and_track_isolation(self):
        records = [
            row("a1", "CAM-07", 1, 1, "KL07AB1234", "KL07AB1234"),
            row("b1", "CAM-07", 2, 1, "TN22ZZ0007", "TN22ZZ0007"),
            row("a2", "CAM-07", 1, 2, "KL07AB1234", "KL07AB1234"),
            row("b2", "CAM-07", 2, 2, "TN22ZZ0007", "TN22ZZ0007"),
            row("a3", "CAM-07", 1, 3, "KL07AB1234", "KL07AB1234"),
            row("b3", "CAM-07", 2, 3, "TN22ZZ0007", "TN22ZZ0007"),
            row("a4", "CAM-07", 1, 4, "KL07AB1234", "KL07AB1284"),
        ]
        report = evaluation.evaluate(records)
        self.assertEqual(report["sequence_count"], 2)
        self.assertEqual(report["single_frame_last_read"],
                         {"exact": 1, "incorrect": 1, "unread": 0, "exact_rate": .5})
        self.assertEqual(report["per_track_consensus"]["exact"], 1)
        self.assertEqual(report["per_track_consensus"]["incorrect"], 0)
        self.assertEqual(report["per_track_consensus"]["abstained"], 1)
        self.assertEqual(report["per_track_consensus"]["coverage_rate"], .5)
        self.assertTrue(report["identity_isolation"]["passed"])
        self.assertEqual(report["identity_isolation"]["fused_outputs_outside_own_track_reads"], 0)
        self.assertFalse(report["accuracy_claim"])

    def test_ambiguous_association_resets_consensus_and_unread_is_not_a_vote(self):
        records = [
            row("s1", "CAM-01", 1, 1, "KL07AB1234", "KL07AB1234"),
            row("s2", "CAM-01", 1, 2, "KL07AB1234", "KL07AB1234"),
            row("s3", "CAM-01", 1, 3, "KL07AB1234", None, association="ambiguous"),
            row("s4", "CAM-01", 1, 4, "KL07AB1234", None),
        ]
        report = evaluation.evaluate(records)
        self.assertEqual(report["single_frame_last_read"]["unread"], 1)
        self.assertEqual(report["per_track_consensus"]["abstained"], 1)
        self.assertEqual(report["per_track_consensus"]["exact"], 0)

    def test_rejects_mixed_labels_duplicate_ids_unsorted_frames_and_non_synthetic_rows(self):
        valid = row("x1", "CAM-01", 1, 1, "KL07AB1234", "KL07AB1234")
        for records in (
            [valid, {**row("x2", "CAM-01", 1, 2, "TN22ZZ0007", "TN22ZZ0007")}],
            [valid, {**valid}],
            [valid, row("x2", "CAM-01", 1, 1, "KL07AB1234", "KL07AB1234")],
            [{**valid, "synthetic": False}],
        ):
            with self.subTest(records=records), self.assertRaises(ValueError):
                evaluation.evaluate(records)


if __name__ == "__main__":
    unittest.main()
