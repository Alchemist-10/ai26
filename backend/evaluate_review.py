"""Compare private human-reviewed crop labels with persisted OCR, without printing plates."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any


def _canonical(value: str | None) -> str:
    """Compare literal plate characters while ignoring spacing and punctuation."""
    return re.sub(r"[^A-Z0-9]", "", value.upper()) if isinstance(value, str) else ""


def _crop_is_valid(manifest_path: Path, sample: dict[str, Any]) -> bool:
    crop_path = sample.get("crop_path")
    digest = sample.get("crop_sha256")
    if not isinstance(crop_path, str) or not isinstance(digest, str):
        return False
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        return False
    candidate = (manifest_path.parent / crop_path).resolve()
    try:
        candidate.relative_to(manifest_path.parent.resolve())
    except ValueError:
        return False
    try:
        content = candidate.read_bytes()
    except OSError:
        return False
    return hashlib.sha256(content).hexdigest() == digest


def _matching_raw_reads(
    connection: sqlite3.Connection, sample: dict[str, Any]
) -> list[dict[str, Any]]:
    required = (
        "camera_id",
        "session_id",
        "frame_id",
        "crop_bbox",
        "crop_sha256",
        "source_sha256",
    )
    if any(key not in sample for key in required):
        return []

    matches: list[dict[str, Any]] = []
    rows = connection.execute(
        "SELECT plate, data FROM observations WHERE camera=? AND kind='plate'",
        (sample["camera_id"],),
    )
    for plate, raw_data in rows:
        try:
            read = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError):
            continue
        if (
            read.get("camera_id") != sample["camera_id"]
            or read.get("session_id") != sample["session_id"]
            or read.get("frame_id") != sample["frame_id"]
            or read.get("source_sha256") != sample["source_sha256"]
            or read.get("bbox") != sample["crop_bbox"]
        ):
            continue
        has_crop = any(
            isinstance(ref, dict)
            and ref.get("role") == "plate-crop"
            and ref.get("sha256") == sample["crop_sha256"]
            and ref.get("camera_id") == sample["camera_id"]
            and ref.get("session_id") == sample["session_id"]
            and ref.get("frame_id") == sample["frame_id"]
            and ref.get("source_sha256") == sample["source_sha256"]
            and ref.get("crop_bbox") == sample["crop_bbox"]
            for ref in read.get("artifacts", [])
        )
        if has_crop:
            raw_plate = read.get("plate_raw")
            if not isinstance(raw_plate, str):
                raw_plate = plate if isinstance(plate, str) else ""
            value = _canonical(raw_plate)
            if value:
                matches.append(
                    {
                        "plate": value,
                        "format_valid": read.get("format_valid"),
                        "identity_status": read.get("identity_status"),
                    }
                )
    return matches


def evaluate_review_manifests(
    manifest_paths: list[Path], database_path: Path
) -> dict[str, Any]:
    """Return a sanitized summary for reviewed samples in one or more local manifests."""
    counters: Counter[str] = Counter()
    by_camera: dict[str, Counter[str]] = defaultdict(Counter)
    connection = sqlite3.connect(f"file:{database_path.resolve()}?mode=ro", uri=True)
    try:
        for manifest_path in manifest_paths:
            manifest = json.loads(manifest_path.read_text())
            samples = manifest.get("samples")
            if not isinstance(samples, list):
                raise ValueError("review manifest must contain a samples list")
            for sample in samples:
                if not isinstance(sample, dict):
                    counters["invalid_sample"] += 1
                    continue
                camera = sample.get("camera_id")
                status = sample.get("ground_truth_status")
                readability = sample.get("plate_readability")
                if status != "reviewed" or readability == "unreviewed":
                    counters["pending_review"] += 1
                    continue
                if readability in {"unreadable", "uncertain"}:
                    counters[readability] += 1
                    continue
                if readability != "readable":
                    counters["invalid_sample"] += 1
                    continue
                label = _canonical(sample.get("ground_truth_plate"))
                if not label or not _crop_is_valid(manifest_path, sample):
                    counters["invalid_sample"] += 1
                    if isinstance(camera, str):
                        by_camera[camera]["invalid_sample"] += 1
                    continue

                predictions = _matching_raw_reads(connection, sample)
                unique_predictions = {prediction["plate"] for prediction in predictions}
                if not unique_predictions:
                    result = "missing_output"
                elif len(unique_predictions) > 1:
                    result = "inconsistent_output"
                elif next(iter(unique_predictions)) == label:
                    result = "exact_match"
                else:
                    result = "mismatch"
                counters["readable"] += 1
                counters[result] += 1
                if result == "mismatch":
                    was_rejected = all(
                        prediction["format_valid"] is False
                        or prediction["identity_status"]
                        in {"invalid", "low_confidence", "tracking_ambiguous"}
                        for prediction in predictions
                    )
                    disposition = (
                        "mismatch_rejected_by_pipeline"
                        if was_rejected
                        else "mismatch_not_proven_rejected"
                    )
                    counters[disposition] += 1
                if isinstance(camera, str):
                    by_camera[camera]["readable"] += 1
                    by_camera[camera][result] += 1
                    if result == "mismatch":
                        by_camera[camera][disposition] += 1
    finally:
        connection.close()

    return {
        "schema_version": 1,
        "reviewed_crop_summary": dict(sorted(counters.items())),
        "by_camera": {
            camera: dict(sorted(counts.items()))
            for camera, counts in sorted(by_camera.items())
        },
        "plate_values_or_images_in_report": False,
        "accuracy_claim_allowed": False,
        "limitations": [
            "This summary covers only the selected reviewed crops; it is not a representative accuracy estimate.",
            "Unreadable, uncertain, pending, and invalid samples are not exact-string comparisons.",
            "Missing outputs and inconsistent repeated outputs are reported separately from mismatches.",
            "A mismatch is counted as rejected only when every matched stored read explicitly has an invalid, low-confidence, or ambiguous status, or format_valid=false.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare local reviewed crops with persisted OCR; prints aggregate counts only."
    )
    parser.add_argument("--database", type=Path, default=Path("backend/data/ai26.sqlite3"))
    parser.add_argument("manifests", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        summary = evaluate_review_manifests(args.manifests, args.database)
    except (OSError, sqlite3.Error, json.JSONDecodeError, ValueError) as error:
        print(f"review evaluation failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
