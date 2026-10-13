"""Validate dataset provenance, annotation coverage and split independence."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


SPLITS = {"train", "validation", "test"}
DIMENSIONS = {"vehicle_id", "camera_id", "location_id", "session_id"}
PLATE_LABELS = {"readable", "unreadable", "unknown"}
COORDINATE_STATES = {"validated", "unverified", "missing"}
CLOCK_STATES = {"original", "replay", "unknown"}
SYNC_STATES = {"synchronized", "unsynchronized", "unknown"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    """Raised when a dataset manifest is malformed or internally inconsistent."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty string")
    return value.strip()


def _array(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ManifestError(f"{field} must be an array")
    return value


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _aware_timestamp(value: Any, field: str) -> datetime:
    raw = _text(value, field)
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ManifestError(f"{field} must be an ISO-8601 timestamp") from error
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ManifestError(f"{field} must include a timezone")
    return stamp


def validate_manifest(path: Path) -> dict[str, Any]:
    """Validate structure and actual clip bytes; never infer labels or metadata."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestError(f"cannot read JSON manifest: {error}") from error
    if not isinstance(document, dict):
        raise ManifestError("manifest root must be an object")
    if document.get("schema_version") != 1:
        raise ManifestError("schema_version must be 1")
    dataset_id = _text(document.get("dataset_id"), "dataset_id")
    dimensions = _array(document.get("split_dimensions"), "split_dimensions")
    if (not dimensions or any(not isinstance(d, str) or d not in DIMENSIONS for d in dimensions)
            or len(set(dimensions)) != len(dimensions)):
        raise ManifestError(f"split_dimensions must contain unique values from {sorted(DIMENSIONS)}")

    root = path.resolve().parent
    clips = _array(document.get("clips"), "clips")
    missing_inputs = _array(document.get("missing_inputs"), "missing_inputs")
    clip_ids: set[str] = set()
    seen_by_dimension: dict[str, dict[str, str]] = {dimension: {} for dimension in dimensions}
    label_count = 0
    verified_hashes = 0
    file_errors: list[dict[str, str]] = []
    for index, clip in enumerate(clips):
        prefix = f"clips[{index}]"
        if not isinstance(clip, dict):
            raise ManifestError(f"{prefix} must be an object")
        clip_id = _text(clip.get("clip_id"), f"{prefix}.clip_id")
        if clip_id in clip_ids:
            raise ManifestError(f"duplicate clip_id: {clip_id}")
        clip_ids.add(clip_id)
        split = _text(clip.get("split"), f"{prefix}.split")
        if split not in SPLITS:
            raise ManifestError(f"{prefix}.split must be one of {sorted(SPLITS)}")

        vehicles = _array(clip.get("vehicles"), f"{prefix}.vehicles")
        if any(not isinstance(vehicle, dict) for vehicle in vehicles):
            raise ManifestError(f"{prefix}.vehicles entries must be objects")

        for dimension in dimensions:
            values: list[str]
            if dimension == "vehicle_id":
                values = [_text(entry.get("vehicle_id"), f"{prefix}.vehicles[].vehicle_id") for entry in vehicles]
            else:
                values = [_text(clip.get(dimension), f"{prefix}.{dimension}")]
            if len(values) != len(set(values)):
                raise ManifestError(f"{prefix} repeats a {dimension}")
            for value in values:
                previous = seen_by_dimension[dimension].get(value)
                if previous is not None and previous != split:
                    raise ManifestError(
                        f"split leakage: {dimension} {value!r} appears in {previous!r} and {split!r}"
                    )
                seen_by_dimension[dimension][value] = split

        coordinate_status = clip.get("coordinate_status")
        if coordinate_status not in COORDINATE_STATES:
            raise ManifestError(f"{prefix}.coordinate_status must be one of {sorted(COORDINATE_STATES)}")
        coordinate_evidence = _text(clip.get("coordinate_evidence"), f"{prefix}.coordinate_evidence")
        coordinates = clip.get("coordinates")
        if coordinate_status == "validated":
            if not isinstance(coordinates, dict):
                raise ManifestError(f"{prefix}.coordinates are required when coordinates are validated")
            latitude, longitude = coordinates.get("latitude"), coordinates.get("longitude")
            if (type(latitude) not in (int, float) or type(longitude) not in (int, float)
                    or not math.isfinite(latitude) or not math.isfinite(longitude)
                    or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
                raise ManifestError(f"{prefix}.coordinates must contain valid numeric latitude/longitude")
        elif coordinates is not None:
            raise ManifestError(f"{prefix}.coordinates must be null unless coordinate_status is validated")
        clock_status = clip.get("capture_clock_status")
        if clock_status not in CLOCK_STATES:
            raise ManifestError(f"{prefix}.capture_clock_status must be one of {sorted(CLOCK_STATES)}")
        clock_metadata = clip.get("capture_clock_metadata")
        if not isinstance(clock_metadata, dict):
            raise ManifestError(f"{prefix}.capture_clock_metadata must be an object")
        _text(clock_metadata.get("method"), f"{prefix}.capture_clock_metadata.method")
        _text(clock_metadata.get("timezone"), f"{prefix}.capture_clock_metadata.timezone")
        if clock_status == "original":
            _aware_timestamp(clock_metadata.get("start_time"), f"{prefix}.capture_clock_metadata.start_time")
        elif clock_status == "replay":
            _aware_timestamp(clock_metadata.get("replay_epoch"), f"{prefix}.capture_clock_metadata.replay_epoch")
            offset = clock_metadata.get("source_offset_seconds")
            if type(offset) not in (int, float) or not math.isfinite(offset):
                raise ManifestError(f"{prefix}.capture_clock_metadata.source_offset_seconds must be finite")
        else:
            _text(clock_metadata.get("reason"), f"{prefix}.capture_clock_metadata.reason")
        if clip.get("clock_sync_status") not in SYNC_STATES:
            raise ManifestError(f"{prefix}.clock_sync_status must be one of {sorted(SYNC_STATES)}")
        conditions = clip.get("conditions")
        if not isinstance(conditions, dict):
            raise ManifestError(f"{prefix}.conditions must be an object")
        for field in ("weather", "lighting", "plate_visibility"):
            _text(conditions.get(field), f"{prefix}.conditions.{field}")
        if type(clip.get("labels_complete")) is not bool:
            raise ManifestError(f"{prefix}.labels_complete must be a boolean")
        if type(clip.get("negative_frames_labeled")) is not bool:
            raise ManifestError(f"{prefix}.negative_frames_labeled must be a boolean")

        for vehicle_index, vehicle in enumerate(vehicles):
            vehicle_prefix = f"{prefix}.vehicles[{vehicle_index}]"
            if not isinstance(vehicle, dict):
                raise ManifestError(f"{vehicle_prefix} must be an object")
            _text(vehicle.get("vehicle_id"), f"{vehicle_prefix}.vehicle_id")
            if vehicle.get("plate_label") not in PLATE_LABELS:
                raise ManifestError(f"{vehicle_prefix}.plate_label must be one of {sorted(PLATE_LABELS)}")
            frames = vehicle.get("labeled_frames")
            if type(frames) is not int or frames <= 0:
                raise ManifestError(f"{vehicle_prefix}.labeled_frames must be a positive integer")
            plate_text = vehicle.get("plate_text")
            if vehicle["plate_label"] == "readable":
                _text(plate_text, f"{vehicle_prefix}.plate_text")
            elif plate_text is not None:
                raise ManifestError(f"{vehicle_prefix}.plate_text must be null unless plate_label is readable")
            label_count += 1

        relative_path = _text(clip.get("path"), f"{prefix}.path")
        candidate = (root / relative_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise ManifestError(f"{prefix}.path must stay inside the manifest directory") from error
        expected_hash = clip.get("sha256")
        if not isinstance(expected_hash, str) or not SHA256.fullmatch(expected_hash):
            raise ManifestError(f"{prefix}.sha256 must be 64 lowercase hexadecimal characters")
        if not candidate.is_file():
            file_errors.append({"clip_id": clip_id, "error": "file missing"})
        else:
            actual_hash = _hash_file(candidate)
            if actual_hash != expected_hash:
                file_errors.append({"clip_id": clip_id, "error": "sha256 mismatch"})
            else:
                verified_hashes += 1

    missing_camera_ids: set[str] = set()
    for index, item in enumerate(missing_inputs):
        if not isinstance(item, dict):
            raise ManifestError(f"missing_inputs[{index}] must be an object")
        camera_id = _text(item.get("camera_id"), f"missing_inputs[{index}].camera_id")
        _text(item.get("reason"), f"missing_inputs[{index}].reason")
        missing_camera_ids.add(camera_id)

    splits_present = sorted({clip["split"] for clip in clips})
    errors = file_errors
    ready = (
        bool(clips)
        and not missing_inputs
        and not errors
        and splits_present == ["test", "train", "validation"]
        and label_count > 0
        and all(clip["labels_complete"] and clip["negative_frames_labeled"] for clip in clips)
    )
    return {
        "dataset_id": dataset_id,
        "schema_version": 1,
        "status": "ready" if ready else "incomplete",
        "split_dimensions": dimensions,
        "clip_count": len(clips),
        "verified_clip_hashes": verified_hashes,
        "labelled_vehicle_count": label_count,
        "splits_present": splits_present,
        "missing_inputs": sorted(missing_camera_ids),
        "file_errors": errors,
        "cross_camera_inputs_declared_ready": len({clip["camera_id"] for clip in clips}) >= 2 and all(
            clip["coordinate_status"] == "validated"
            and clip["capture_clock_status"] == "original"
            and clip["clock_sync_status"] == "synchronized"
            for clip in clips
        ),
        "accuracy_claim_allowed": False,
        "note": "Manifest integrity and split separation do not establish label quality or model accuracy.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON manifest; clip paths are relative to its directory")
    parser.add_argument("--require-ready", action="store_true", help="exit 2 unless all splits and labels are present")
    args = parser.parse_args()
    try:
        report = validate_manifest(args.manifest)
    except ManifestError as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 2 if args.require_ready and report["status"] != "ready" else 0


if __name__ == "__main__":
    raise SystemExit(main())
