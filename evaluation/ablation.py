"""Paired raw/classical/learned/fusion evaluation on one labeled test manifest."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

try:
    from .evaluate import evaluate
    from .dataset_manifest import ManifestError, validate_manifest
except ImportError:
    try:
        from evaluate import evaluate
    except ImportError:
        spec = importlib.util.spec_from_file_location("evaluation_metrics", Path(__file__).with_name("evaluate.py"))
        if spec is None or spec.loader is None:
            raise
        evaluation_metrics = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(evaluation_metrics)
        evaluate = evaluation_metrics.evaluate
    try:
        from dataset_manifest import ManifestError, validate_manifest
    except ImportError:
        spec = importlib.util.spec_from_file_location("dataset_manifest", Path(__file__).with_name("dataset_manifest.py"))
        if spec is None or spec.loader is None:
            raise
        dataset_manifest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dataset_manifest)
        ManifestError, validate_manifest = dataset_manifest.ManifestError, dataset_manifest.validate_manifest


VARIANTS = ("raw", "classical", "learned", "fusion")
HASH = re.compile(r"^[a-f0-9]{64}$")
GROUND_TRUTH_FIELDS = ("clip_id", "camera", "session", "frame_index", "expected_plate",
                       "expected_boxes", "expected_link", "expected_rule", "expected_passages")
PREDICTION_METRICS = (
    ("detector", "precision"), ("detector", "recall"),
    ("plates", "exact_match_rate"), ("plates", "abstentions"),
    ("tracking", "id_switches"), ("tracking", "fragmentations"),
    ("links", "precision"), ("links", "recall"),
    ("rules", "precision"), ("rules", "recall"),
    ("passages", "signed_error"),
)


class AblationError(ValueError):
    """Raised when ablation inputs are not paired or traceable."""


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _record_key(record: dict) -> str:
    sample_id = record.get("sample_id")
    if not isinstance(sample_id, str) or not sample_id.strip():
        raise AblationError("each record needs a non-empty sample_id")
    return sample_id


def compare_ablation_records(records: list[dict], test_clips: dict[str, dict], manifest_sha256: str) -> dict:
    """Compare four variants using the same test frames and unchanged labels."""
    if not isinstance(records, list) or not records:
        raise AblationError("records must contain predictions for all four variants")
    grouped: dict[str, dict[str, dict]] = {variant: {} for variant in VARIANTS}
    run_metadata: dict[str, dict] = {}
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            raise AblationError(f"record {index} must be an object")
        variant = row.get("variant")
        if not isinstance(variant, str) or variant not in grouped:
            raise AblationError(f"record {index} variant must be one of {VARIANTS}")
        sample_id = _record_key(row)
        if sample_id in grouped[variant]:
            raise AblationError(f"duplicate sample_id {sample_id!r} in variant {variant}")
        if row.get("synthetic", False):
            raise AblationError("synthetic fixtures cannot be used for an ablation accuracy report")
        if row.get("manifest_sha256") != manifest_sha256:
            raise AblationError(f"record {sample_id!r} does not reference the validated manifest hash")
        clip_id = row.get("clip_id")
        clip = test_clips.get(clip_id) if isinstance(clip_id, str) else None
        if clip is None or clip.get("split") != "test":
            raise AblationError(f"record {sample_id!r} must reference a test-split clip")
        if row.get("camera") != clip.get("camera_id") or row.get("session") != clip.get("session_id"):
            raise AblationError(f"record {sample_id!r} camera/session do not match the test manifest")
        if "frame_index" not in row or type(row["frame_index"]) is not int or row["frame_index"] < 0:
            raise AblationError(f"record {sample_id!r} needs a nonnegative frame_index")

        metadata = row.get("run_metadata")
        required = ("model_id", "model_version", "weights_sha256", "preprocessing_id", "configuration_sha256")
        if not isinstance(metadata, dict) or any(not isinstance(metadata.get(key), str) or not metadata[key].strip()
                                                 for key in required):
            raise AblationError(f"record {sample_id!r} needs complete run_metadata")
        for key in ("weights_sha256", "configuration_sha256"):
            if not HASH.fullmatch(metadata[key]):
                raise AblationError(f"record {sample_id!r} run_metadata.{key} must be a SHA-256 digest")
        if variant in run_metadata and run_metadata[variant] != metadata:
            raise AblationError(f"variant {variant} mixes model/configuration provenance")
        run_metadata[variant] = metadata
        grouped[variant][sample_id] = row

    if set(run_metadata) != set(VARIANTS):
        raise AblationError(f"all four variants are required: {', '.join(VARIANTS)}")
    fingerprints = {metadata["configuration_sha256"] for metadata in run_metadata.values()}
    if len(fingerprints) != len(VARIANTS):
        raise AblationError("each variant must identify its own configuration with a distinct hash")
    sample_sets = {variant: set(grouped[variant]) for variant in VARIANTS}
    expected_samples = sample_sets["raw"]
    if not expected_samples or any(values != expected_samples for values in sample_sets.values()):
        raise AblationError("all variants must contain exactly the same non-empty sample_id set")

    for sample_id in sorted(expected_samples):
        labels = [_json({key: grouped[variant][sample_id].get(key) for key in GROUND_TRUTH_FIELDS})
                  for variant in VARIANTS]
        if len(set(labels)) != 1:
            raise AblationError(f"ground-truth labels differ across variants for sample {sample_id!r}")

    metrics = {}
    for variant in VARIANTS:
        metric_rows = []
        for row in grouped[variant].values():
            metric_rows.append({key: value for key, value in row.items()
                                if key not in ("variant", "manifest_sha256", "run_metadata", "synthetic")})
        metrics[variant] = evaluate(metric_rows)

    paired_plate_changes = {}
    for variant in VARIANTS[1:]:
        improved = regressed = unchanged = 0
        for sample_id in expected_samples:
            raw, candidate = grouped["raw"][sample_id], grouped[variant][sample_id]
            if "expected_plate" not in raw:
                continue
            raw_correct = raw.get("predicted_plate") == raw.get("expected_plate")
            candidate_correct = candidate.get("predicted_plate") == candidate.get("expected_plate")
            improved += candidate_correct and not raw_correct
            regressed += raw_correct and not candidate_correct
            unchanged += candidate_correct == raw_correct
        paired_plate_changes[variant] = {"correctness_improved": improved, "correctness_regressed": regressed,
                                         "correctness_unchanged": unchanged}

    deltas = {}
    baseline = metrics["raw"]
    for variant in VARIANTS[1:]:
        deltas[variant] = {}
        for section, metric in PREDICTION_METRICS:
            before, after = baseline[section][metric], metrics[variant][section][metric]
            deltas[variant][f"{section}.{metric}"] = (after - before) if before is not None and after is not None else None

    return {
        "schema_version": 1,
        "type": "paired_model_ablation_report",
        "synthetic": False,
        "manifest_sha256": manifest_sha256,
        "test_sample_count": len(expected_samples),
        "test_clip_count": len({grouped["raw"][sample]["clip_id"] for sample in expected_samples}),
        "variants": {variant: {"run_metadata": run_metadata[variant], "metrics": metrics[variant]}
                     for variant in VARIANTS},
        "delta_from_raw": deltas,
        "paired_plate_correctness_changes_vs_raw": paired_plate_changes,
        "accuracy_interpretation": "Metrics describe only these paired, manifest-verified labeled test samples; no confidence intervals or claims beyond this dataset are inferred.",
        "limitations": ["No ablation result is valid until the test manifest contains real, held-out labeled clips.",
                        "Variants must use the same samples and labels; model/configuration provenance is required.",
                        "The report does not select a production model or establish deployment safety."],
    }


def run(records_path: Path, manifest_path: Path) -> dict:
    try:
        manifest_report = validate_manifest(manifest_path)
    except ManifestError as error:
        raise AblationError(f"invalid dataset manifest: {error}") from error
    if manifest_report["status"] != "ready":
        raise AblationError("dataset manifest is incomplete; require real labeled train/validation/test splits")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    clips = {clip["clip_id"]: clip for clip in manifest["clips"] if clip["split"] == "test"}
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = compare_ablation_records(records, clips, digest)
    report["dataset_id"] = manifest_report["dataset_id"]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True, help="paired JSONL predictions from four variants")
    parser.add_argument("--manifest", type=Path, required=True, help="complete dataset manifest with held-out test split")
    parser.add_argument("--output", type=Path, required=True, help="new report path; never overwrites")
    args = parser.parse_args()
    try:
        report = run(args.records, args.manifest)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        fd, temp_name = tempfile.mkstemp(prefix=f".{args.output.name}.", suffix=".tmp", dir=args.output.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temp_name, args.output)
        finally:
            Path(temp_name).unlink(missing_ok=True)
        print(f"{report['test_sample_count']} paired samples across {len(VARIANTS)} variants; output={args.output}")
    except (OSError, json.JSONDecodeError, AblationError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
