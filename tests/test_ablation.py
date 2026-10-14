import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "evaluation" / "ablation.py"
spec = importlib.util.spec_from_file_location("ablation", MODULE_PATH)
ablation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ablation)


def records():
    result = []
    config_hashes = {name: f"{index:x}" * 64 for index, name in enumerate(ablation.VARIANTS, 1)}
    predictions = {
        "raw": [None, "KL07AB1234"],
        "classical": ["KL07AB1234", "KL07AC1234"],
        "learned": ["KL07AB1234", "KL07AB1234"],
        "fusion": ["KL07AB1234", "KL07AB1234"],
    }
    for variant in ablation.VARIANTS:
        for index, sample_id in enumerate(("s1", "s2"), 1):
            result.append({
                "variant": variant,
                "sample_id": sample_id,
                "clip_id": "clip-test",
                "camera": "CAM-01",
                "session": "session-1",
                "frame_index": index,
                "expected_plate": "KL07AB1234",
                "predicted_plate": predictions[variant][index - 1],
                "expected_boxes": [],
                "predicted_boxes": [],
                "expected_passages": 1,
                "predicted_passages": 1,
                "manifest_sha256": "f" * 64,
                "run_metadata": {
                    "model_id": variant,
                    "model_version": "test",
                    "weights_sha256": "a" * 64,
                    "preprocessing_id": variant,
                    "configuration_sha256": config_hashes[variant],
                },
            })
    return result


class AblationTests(unittest.TestCase):
    def setUp(self):
        self.test_clips = {"clip-test": {"split": "test", "camera_id": "CAM-01", "session_id": "session-1"}}

    def test_paired_variants_report_metrics_deltas_and_plate_regressions(self):
        report = ablation.compare_ablation_records(records(), self.test_clips, "f" * 64)
        self.assertEqual(report["test_sample_count"], 2)
        self.assertEqual(set(report["variants"]), set(ablation.VARIANTS))
        self.assertEqual(report["variants"]["raw"]["metrics"]["plates"]["exact_matches"], 1)
        self.assertEqual(report["variants"]["fusion"]["metrics"]["plates"]["exact_matches"], 2)
        self.assertEqual(report["paired_plate_correctness_changes_vs_raw"]["fusion"], {
            "correctness_improved": 1, "correctness_regressed": 0, "correctness_unchanged": 1,
        })
        self.assertEqual(report["delta_from_raw"]["fusion"]["plates.exact_match_rate"], 0.5)
        self.assertFalse(report["synthetic"])

    def test_variants_must_use_exactly_same_samples_and_labels(self):
        data = records()
        data.pop()
        with self.assertRaisesRegex(ablation.AblationError, "same non-empty sample_id set"):
            ablation.compare_ablation_records(data, self.test_clips, "f" * 64)

        data = records()
        next(row for row in data if row["variant"] == "learned" and row["sample_id"] == "s1")["expected_plate"] = "KL07AC1234"
        with self.assertRaisesRegex(ablation.AblationError, "ground-truth labels differ"):
            ablation.compare_ablation_records(data, self.test_clips, "f" * 64)

    def test_provenance_and_test_split_are_required(self):
        data = records()
        data[0]["manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(ablation.AblationError, "validated manifest hash"):
            ablation.compare_ablation_records(data, self.test_clips, "f" * 64)

        data = records()
        with self.assertRaisesRegex(ablation.AblationError, "test-split clip"):
            ablation.compare_ablation_records(data, {"clip-test": {"split": "validation"}}, "f" * 64)

        data = records()
        data[0]["run_metadata"]["weights_sha256"] = "missing"
        with self.assertRaisesRegex(ablation.AblationError, "SHA-256 digest"):
            ablation.compare_ablation_records(data, self.test_clips, "f" * 64)

    def test_synthetic_rows_and_duplicate_ids_are_rejected(self):
        data = records()
        data[0]["synthetic"] = True
        with self.assertRaisesRegex(ablation.AblationError, "synthetic fixtures"):
            ablation.compare_ablation_records(data, self.test_clips, "f" * 64)

        data = records()
        data.append(data[0].copy())
        with self.assertRaisesRegex(ablation.AblationError, "duplicate sample_id"):
            ablation.compare_ablation_records(data, self.test_clips, "f" * 64)


if __name__ == "__main__":
    unittest.main()
