"""Fail-closed offline acceptance gate for digest-pinned model canaries.

The gate does not install or promote weights. It checks operator-supplied policy
against paired evaluation reports that use one verified, held-out manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

try:
    from .dataset_manifest import ManifestError, validate_manifest
except ImportError:
    from dataset_manifest import ManifestError, validate_manifest


SHA256 = re.compile(r"^[0-9a-f]{64}$")
POLICY_FIELDS = {
    "schema_version",
    "minimum_test_frames",
    "minimum_labeled_boxes",
    "minimum_labeled_plates",
    "minimum_detection_precision",
    "minimum_detection_recall",
    "minimum_plate_exact_match_rate",
    "maximum_false_positives_per_100_objects",
    "maximum_false_reads_per_100_plates",
    "maximum_detection_precision_drop",
    "maximum_detection_recall_drop",
    "maximum_plate_exact_match_drop",
    "maximum_false_positive_rate_increase",
    "maximum_false_read_rate_increase",
}


class GateError(ValueError):
    """Raised when an evaluation package cannot safely be gated."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GateError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise GateError(f"{label} must be a JSON object")
    return value


def validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    if set(policy) != POLICY_FIELDS:
        missing = sorted(POLICY_FIELDS - set(policy))
        extra = sorted(set(policy) - POLICY_FIELDS)
        detail = []
        if missing:
            detail.append(f"missing fields: {', '.join(missing)}")
        if extra:
            detail.append(f"unknown fields: {', '.join(extra)}")
        raise GateError("policy fields do not match schema version 1 (" + "; ".join(detail) + ")")
    if type(policy["schema_version"]) is not int or policy["schema_version"] != 1:
        raise GateError("policy schema_version must be 1")
    for name in ("minimum_test_frames", "minimum_labeled_boxes", "minimum_labeled_plates"):
        if type(policy[name]) is not int or policy[name] < 1:
            raise GateError(f"{name} must be a positive integer")
    for name in (
        "minimum_detection_precision", "minimum_detection_recall",
        "minimum_plate_exact_match_rate", "maximum_detection_precision_drop",
        "maximum_detection_recall_drop", "maximum_plate_exact_match_drop",
        "maximum_false_positive_rate_increase", "maximum_false_read_rate_increase",
    ):
        value = policy[name]
        if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
            raise GateError(f"{name} must be a finite fraction from 0 through 1")
    if policy["minimum_plate_exact_match_rate"] <= 0:
        raise GateError("minimum_plate_exact_match_rate must require a positive exact-read rate")
    if policy["minimum_detection_precision"] <= 0 or policy["minimum_detection_recall"] <= 0:
        raise GateError("minimum detection precision and recall must both be positive")
    for name in ("maximum_false_positives_per_100_objects", "maximum_false_reads_per_100_plates"):
        value = policy[name]
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise GateError(f"{name} must be a finite nonnegative rate")
    return policy


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise GateError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _rate(numerator: int, denominator: int, label: str) -> float:
    if type(numerator) is not int or numerator < 0 or type(denominator) is not int or denominator < 0:
        raise GateError(f"{label} counts must be nonnegative integers")
    if denominator == 0:
        raise GateError(f"{label} has no labeled denominator")
    return numerator / denominator


def _metrics(report: dict[str, Any], label: str, minimum_frames: int,
             minimum_boxes: int, minimum_plates: int) -> dict[str, float | int]:
    if report.get("synthetic") is not False:
        raise GateError(f"{label} report is synthetic or does not declare real data")
    sample_count = report.get("sample_count")
    if type(sample_count) is not int or sample_count < minimum_frames:
        raise GateError(f"{label} report does not meet the minimum test-frame count")
    detector, plates = report.get("detector"), report.get("plates")
    if not isinstance(detector, dict) or not isinstance(plates, dict):
        raise GateError(f"{label} report is missing detector or plate metrics")
    tp, fp, fn = (detector.get(key) for key in ("tp", "fp", "fn"))
    if any(type(value) is not int or value < 0 for value in (tp, fp, fn)):
        raise GateError(f"{label} detector counts are invalid")
    labeled_boxes = tp + fn
    if labeled_boxes < minimum_boxes:
        raise GateError(f"{label} report does not meet the minimum labeled-box count")
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = _rate(tp, tp + fn, f"{label} detection recall")
    plate_count = plates.get("labeled_samples")
    exact = plates.get("exact_matches")
    false_reads = plates.get("false_reads")
    abstentions = plates.get("abstentions")
    if any(type(value) is not int or value < 0 for value in (plate_count, exact, false_reads, abstentions)):
        raise GateError(f"{label} plate counts are invalid")
    if plate_count < minimum_plates or exact + false_reads + abstentions != plate_count:
        raise GateError(f"{label} report does not meet plate-label requirements")
    exact_rate = _rate(exact, plate_count, f"{label} exact plate rate")
    false_read_rate = _rate(false_reads, plate_count, f"{label} false-read rate")
    false_positive_rate = fp / labeled_boxes
    return {
        "test_frames": sample_count,
        "labeled_boxes": labeled_boxes,
        "labeled_plates": plate_count,
        "detection_precision": precision,
        "detection_recall": recall,
        "false_positives_per_100_objects": 100 * false_positive_rate,
        "plate_exact_match_rate": exact_rate,
        "false_reads_per_100_plates": 100 * false_read_rate,
        "false_positive_rate": false_positive_rate,
        "false_read_rate": false_read_rate,
    }


def _verify_report(path: Path, label: str, manifest_sha: str, model_sha: str,
                   records_path: Path,
                   minimum_frames: int, minimum_boxes: int,
                   minimum_plates: int) -> tuple[dict[str, Any], dict[str, float | int]]:
    report = _read_json(path, f"{label} evaluation report")
    provenance = report.get("provenance")
    if (not isinstance(provenance, dict) or type(provenance.get("schema_version")) is not int
            or provenance.get("schema_version") != 1):
        raise GateError(f"{label} report has no supported provenance block")
    if provenance.get("manifest_sha256") != manifest_sha:
        raise GateError(f"{label} report was not evaluated against the supplied manifest")
    if provenance.get("test_split_only") is not True:
        raise GateError(f"{label} report does not prove test-split-only evaluation")
    if provenance.get("record_count") != report.get("sample_count"):
        raise GateError(f"{label} report record count does not match its sample count")
    _digest(provenance.get("sample_ids_sha256"), f"{label} report sample_ids_sha256")
    if _digest(provenance.get("model_sha256"), f"{label} report model_sha256") != model_sha:
        raise GateError(f"{label} report model hash does not match the requested model")
    try:
        records_sha = hashlib.sha256(records_path.read_bytes()).hexdigest()
    except OSError as error:
        raise GateError(f"cannot read {label} prediction records: {error}") from error
    if _digest(provenance.get("records_sha256"), f"{label} report records_sha256") != records_sha:
        raise GateError(f"{label} report does not match the supplied prediction records")
    return report, _metrics(report, label, minimum_frames, minimum_boxes, minimum_plates)


def evaluate_gate(*, manifest_path: Path, stable_report_path: Path,
                  candidate_report_path: Path, stable_records_path: Path,
                  candidate_records_path: Path, policy: dict[str, Any],
                  stable_model_sha256: str, candidate_model_sha256: str) -> dict[str, Any]:
    policy = validate_policy(policy)
    stable_sha = _digest(stable_model_sha256, "stable model SHA-256")
    candidate_sha = _digest(candidate_model_sha256, "candidate model SHA-256")
    if stable_sha == candidate_sha:
        raise GateError("stable and candidate model hashes must differ")
    try:
        manifest_report = validate_manifest(manifest_path)
    except ManifestError as error:
        raise GateError(f"dataset manifest is invalid: {error}") from error
    if manifest_report["status"] != "ready":
        raise GateError("dataset manifest is incomplete; all disjoint labeled splits and clip hashes are required")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    common = (policy["minimum_test_frames"], policy["minimum_labeled_boxes"],
              policy["minimum_labeled_plates"])
    stable_report, stable = _verify_report(stable_report_path, "stable", manifest_sha, stable_sha,
                                           stable_records_path, *common)
    candidate_report, candidate = _verify_report(candidate_report_path, "candidate", manifest_sha, candidate_sha,
                                                 candidate_records_path, *common)
    if stable_report.get("sample_count") != candidate_report.get("sample_count"):
        raise GateError("stable and candidate reports must contain the same number of test samples")
    if (stable_report["provenance"]["sample_ids_sha256"]
            != candidate_report["provenance"]["sample_ids_sha256"]):
        raise GateError("stable and candidate reports must use the exact same test sample IDs")
    checks = [
        ("minimum_detection_precision", candidate["detection_precision"] >= policy["minimum_detection_precision"]),
        ("minimum_detection_recall", candidate["detection_recall"] >= policy["minimum_detection_recall"]),
        ("minimum_plate_exact_match_rate", candidate["plate_exact_match_rate"] >= policy["minimum_plate_exact_match_rate"]),
        ("maximum_false_positives_per_100_objects", candidate["false_positives_per_100_objects"] <= policy["maximum_false_positives_per_100_objects"]),
        ("maximum_false_reads_per_100_plates", candidate["false_reads_per_100_plates"] <= policy["maximum_false_reads_per_100_plates"]),
        ("maximum_detection_precision_drop", stable["detection_precision"] - candidate["detection_precision"] <= policy["maximum_detection_precision_drop"]),
        ("maximum_detection_recall_drop", stable["detection_recall"] - candidate["detection_recall"] <= policy["maximum_detection_recall_drop"]),
        ("maximum_plate_exact_match_drop", stable["plate_exact_match_rate"] - candidate["plate_exact_match_rate"] <= policy["maximum_plate_exact_match_drop"]),
        ("maximum_false_positive_rate_increase", candidate["false_positive_rate"] - stable["false_positive_rate"] <= policy["maximum_false_positive_rate_increase"]),
        ("maximum_false_read_rate_increase", candidate["false_read_rate"] - stable["false_read_rate"] <= policy["maximum_false_read_rate_increase"]),
    ]
    return {
        "schema_version": 1,
        "eligible": all(passed for _, passed in checks),
        "promotion_performed": False,
        "manifest_sha256": manifest_sha,
        "stable_model_sha256": stable_sha,
        "candidate_model_sha256": candidate_sha,
        "policy": policy,
        "stable": stable,
        "candidate": candidate,
        "checks": [{"name": name, "passed": passed} for name, passed in checks],
        "limitations": [
            "The gate verifies report declarations and dataset hashes, not the quality of human labels or the provenance of prediction generation.",
            "Thresholds are operator-supplied and must be approved for the deployment context.",
            "Eligibility does not install weights, change the stable model, or prove field performance beyond this held-out dataset.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--stable-report", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path, required=True)
    parser.add_argument("--stable-records", type=Path, required=True)
    parser.add_argument("--candidate-records", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--stable-model-sha256", required=True)
    parser.add_argument("--candidate-model-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = evaluate_gate(
            manifest_path=args.manifest,
            stable_report_path=args.stable_report,
            candidate_report_path=args.candidate_report,
            stable_records_path=args.stable_records,
            candidate_records_path=args.candidate_records,
            policy=_read_json(args.policy, "promotion policy"),
            stable_model_sha256=args.stable_model_sha256,
            candidate_model_sha256=args.candidate_model_sha256,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except GateError as error:
        print(json.dumps({"eligible": False, "error": str(error)}, indent=2), file=sys.stderr)
        return 1
    print(f"candidate eligible={str(report['eligible']).lower()}; promotion performed=false; output={args.output}")
    return 0 if report["eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
