import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
REPORT = ROOT / "docs/validation/alpr-visible-vehicle-frame-check-2026-10-16.json"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AlprVisibleVehicleReportTests(unittest.TestCase):
    def test_report_source_and_model_hashes_match_checked_in_assets(self):
        report = json.loads(REPORT.read_text())
        bundle = json.loads((ROOT / "evaluation/model-bundle.current.json").read_text())
        by_role = {component["role"]: component for component in bundle["components"]}
        for sample in report["samples"]:
            self.assertEqual(sha256(ROOT / sample["clip_path"]), sample["clip_sha256"])
            self.assertEqual(sample["plate_detector_candidates"], 0)
            self.assertEqual(sample["plate_ocr_calls"], 0)
            self.assertIn("vehicle_model_observation", sample)
        self.assertEqual(report["conditions"]["vehicle_detector_sha256"],
                         by_role["vehicle_detector_weights"]["sha256"])
        report_models = {item["role"]: item["sha256"] for item in report["model_files"]}
        for report_role, bundle_role in (("plate_detector_weights", "plate_detector_weights"),
                                         ("ocr_weights", "plate_ocr_weights"),
                                         ("ocr_configuration", "plate_ocr_configuration")):
            self.assertEqual(report_models[report_role], by_role[bundle_role]["sha256"])

    def test_report_explicitly_disclaims_accuracy_and_identity_linking(self):
        report = json.loads(REPORT.read_text())
        self.assertFalse(report["aggregate"]["accuracy_measured"])
        self.assertFalse(report["aggregate"]["false_negatives_measured"])
        self.assertFalse(report["aggregate"]["identity_linked_across_cameras"])
        self.assertEqual(report["aggregate"]["plate_ocr_calls"], 0)
        self.assertTrue(any("same vehicle" in limitation for limitation in report["limitations"]))

    def test_proxy_scan_hashes_all_six_clips_and_records_no_accuracy_claim(self):
        report_path = ROOT / "docs/validation/alpr-proxy-largest-vehicle-scan-2026-10-16.json"
        report = json.loads(report_path.read_text())
        bundle = json.loads((ROOT / "evaluation/model-bundle.current.json").read_text())
        self.assertEqual(report["sampling"]["sampled_frames"], 252)
        self.assertEqual(report["sampling"]["selected_frames"], 6)
        self.assertEqual({sample["camera"] for sample in report["samples"]},
                         {f"CAM-{index:02}" for index in range(1, 7)})
        for sample in report["samples"]:
            self.assertEqual(sha256(ROOT / sample["clip_path"]), sample["clip_sha256"])
            self.assertEqual(sample["plate_detection_count"], 0)
            self.assertEqual(sample["ocr_result_count"], 0)
        self.assertEqual(report["models"]["vehicle_detector_sha256"],
                         bundle["components"][0]["sha256"])
        # This is an immutable run snapshot; current code advances independently.
        source_snapshot = report["models"]["pipeline_source_sha256"]
        self.assertTrue(source_snapshot)
        self.assertTrue(all(len(value) == 64 and all(char in "0123456789abcdef" for char in value)
                            for value in source_snapshot.values()))
        self.assertFalse(report["aggregate"]["accuracy_measured"])
        self.assertFalse(report["aggregate"]["false_negatives_measured"])


if __name__ == "__main__":
    unittest.main()
