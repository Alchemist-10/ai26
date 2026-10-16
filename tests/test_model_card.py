import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "evaluation" / "validate_model_card.py"
spec = importlib.util.spec_from_file_location("validate_model_card", MODULE_PATH)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ModelCardValidationTests(unittest.TestCase):
    def test_current_card_and_all_pinned_local_evidence_match(self):
        errors = validator.validate_model_card(ROOT / "evaluation/model-card.current.json", ROOT)
        self.assertEqual(errors, [])

    def test_report_digest_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "report.json").write_text('{"sample_count": 2}\n')
            card = {
                "schema_version": 1,
                "model_id": "test-model",
                "model_version": "test-version",
                "intended_use": "test only",
                "task": "test",
                "architecture": "test",
                "weights": {"sha256": "a" * 64},
                "pipeline": {"configuration_sha256": "b" * 64, "preprocessing_sha256": "c" * 64},
                "data": {"known_coverage_gaps": ["labels unavailable"]},
                "evaluation": {
                    "report_path": "report.json", "report_sha256": "d" * 64,
                    "sample_count": 2, "limitations": ["fixture only"],
                },
                "release_decision": {"status": "unreviewed"},
            }
            card_path = root / "card.json"
            card_path.write_text(json.dumps(card))
            errors = validator.validate_model_card(card_path, root)
            self.assertTrue(any("does not match report.json" in error for error in errors), errors)

    def test_repository_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            outside = Path(directory) / "outside.json"
            outside.write_text("{}\n")
            card = {
                "schema_version": 1, "model_id": "test", "model_version": "1",
                "intended_use": "test", "task": "test", "architecture": "test",
                "weights": {"sha256": "a" * 64},
                "pipeline": {"configuration_sha256": "b" * 64, "preprocessing_sha256": "c" * 64},
                "data": {"known_coverage_gaps": ["unknown"]},
                "evaluation": {
                    "report_path": "../outside.json", "report_sha256": "d" * 64,
                    "sample_count": 1, "limitations": ["test"],
                },
                "release_decision": {"status": "unreviewed"},
            }
            card_path = root / "card.json"
            card_path.write_text(json.dumps(card))
            errors = validator.validate_model_card(card_path, root)
            self.assertTrue(any("inside the repository" in error for error in errors), errors)

    def test_bundle_pipeline_source_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.py").write_text("current source\n")
            bundle = {
                "components": [{"sha256": "a" * 64}],
                "pipeline_sources": {"source.py": "b" * 64},
            }
            bundle_path = root / "bundle.json"
            bundle_path.write_text(json.dumps(bundle))
            import hashlib
            bundle_hash = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
            report_path = root / "report.json"
            report_path.write_text("{}\n")
            report_hash = hashlib.sha256(report_path.read_bytes()).hexdigest()
            card = {
                "schema_version": 1, "model_id": "test", "model_version": "1",
                "intended_use": "test", "task": "test", "architecture": "test",
                "weights": {"sha256": bundle_hash},
                "pipeline": {"configuration_sha256": bundle_hash, "preprocessing_sha256": "c" * 64},
                "data": {"known_coverage_gaps": ["unknown"]},
                "evaluation": {
                    "report_path": "report.json", "report_sha256": report_hash,
                    "sample_count": 1, "limitations": ["test"],
                },
                "provenance_bundle": {"path": "bundle.json", "sha256": bundle_hash},
                "release_decision": {"status": "unreviewed"},
            }
            card_path = root / "card.json"
            card_path.write_text(json.dumps(card))
            errors = validator.validate_model_card(card_path, root)
            self.assertTrue(any("pipeline_sources" in error and "does not match" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
