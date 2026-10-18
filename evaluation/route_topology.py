"""Learn review-only camera-pair time windows from session-split labeled transitions."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 500_000
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
MIN_POSITIVES_PER_EDGE = 5


class RouteDataError(ValueError):
    """Malformed, insufficient, or leaky labeled transition data."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise RouteDataError(f"{field} must be a non-empty identifier of at most 64 safe characters")
    return value


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_records(path: Path) -> tuple[list[dict], str]:
    path = Path(path)
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise RouteDataError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    records, seen_ids, seen_session_edges, session_split = [], set(), set(), {}
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if len(records) >= MAX_RECORDS:
                raise RouteDataError(f"input exceeds {MAX_RECORDS} records")
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise RouteDataError(f"line {line_number} is not valid JSON") from error
            if not isinstance(value, dict):
                raise RouteDataError(f"line {line_number} must be an object")
            record_id = _text(value.get("record_id"), "record_id")
            session = _text(value.get("session_id"), "session_id")
            source_camera = _text(value.get("from_camera"), "from_camera")
            target_camera = _text(value.get("to_camera"), "to_camera")
            if source_camera == target_camera:
                raise RouteDataError(f"line {line_number} must describe a directed transition between different cameras")
            split = value.get("split")
            if split not in ("train", "test"):
                raise RouteDataError(f"line {line_number}.split must be train or test")
            if type(value.get("traversed")) is not bool:
                raise RouteDataError(f"line {line_number}.traversed must be a boolean label")
            elapsed = value.get("elapsed_seconds")
            if (type(elapsed) not in (int, float) or not math.isfinite(elapsed)
                    or not 0 < elapsed <= 7 * 86400):
                raise RouteDataError(f"line {line_number}.elapsed_seconds must be finite and in (0, 604800]")
            if type(value.get("coordinates_validated")) is not bool or type(value.get("clocks_synchronized")) is not bool:
                raise RouteDataError(f"line {line_number} must state coordinate and clock validation explicitly")
            if record_id in seen_ids:
                raise RouteDataError(f"duplicate record_id: {record_id}")
            session_edge = (session, source_camera, target_camera)
            if session_edge in seen_session_edges:
                raise RouteDataError(f"session {session!r} has repeated samples for the same directed camera pair")
            previous_split = session_split.setdefault(session, split)
            if previous_split != split:
                raise RouteDataError(f"session leakage: session {session!r} appears in both splits")
            seen_ids.add(record_id)
            seen_session_edges.add(session_edge)
            records.append({
                "record_id": record_id, "session_id": session,
                "from_camera": source_camera, "to_camera": target_camera,
                "elapsed_seconds": float(elapsed), "traversed": value["traversed"],
                "split": split, "coordinates_validated": value["coordinates_validated"],
                "clocks_synchronized": value["clocks_synchronized"],
            })
    if not records:
        raise RouteDataError("input contains no transition records")
    return records, _hash(path)


def fit_and_evaluate(records: list[dict], data_sha256: str, *, lower_quantile: float = 0.05,
                     upper_quantile: float = 0.95) -> dict:
    """Fit empirical edge windows on training positives and score session-held-out test rows."""
    if not isinstance(records, list) or not records or len(records) > MAX_RECORDS:
        raise RouteDataError(f"records must be a non-empty list of at most {MAX_RECORDS} rows")
    if not re.fullmatch(r"[0-9a-f]{64}", data_sha256):
        raise RouteDataError("data_sha256 must be a lowercase SHA-256 digest")
    if (type(lower_quantile) not in (int, float) or type(upper_quantile) not in (int, float)
            or not 0 <= lower_quantile < upper_quantile <= 1):
        raise RouteDataError("quantiles must satisfy 0 <= lower < upper <= 1")
    seen_ids, session_split, session_edges = set(), {}, set()
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            raise RouteDataError(f"record {index} must be an object")
        record_id = _text(record.get("record_id"), "record_id")
        session = _text(record.get("session_id"), "session_id")
        source = _text(record.get("from_camera"), "from_camera")
        target = _text(record.get("to_camera"), "to_camera")
        split = record.get("split")
        elapsed = record.get("elapsed_seconds")
        if source == target:
            raise RouteDataError(f"record {index} must describe different cameras")
        if split not in ("train", "test"):
            raise RouteDataError(f"record {index}.split must be train or test")
        if type(record.get("traversed")) is not bool:
            raise RouteDataError(f"record {index}.traversed must be boolean")
        if (type(elapsed) not in (int, float) or not math.isfinite(elapsed)
                or not 0 < elapsed <= 7 * 86400):
            raise RouteDataError(f"record {index}.elapsed_seconds must be finite and in (0, 604800]")
        if (type(record.get("coordinates_validated")) is not bool
                or type(record.get("clocks_synchronized")) is not bool):
            raise RouteDataError(f"record {index} must state coordinate and clock validation explicitly")
        if record_id in seen_ids:
            raise RouteDataError(f"duplicate record_id: {record_id}")
        edge_key = (session, source, target)
        if edge_key in session_edges:
            raise RouteDataError(f"session {session!r} has repeated samples for the same directed camera pair")
        previous_split = session_split.setdefault(session, split)
        if previous_split != split:
            raise RouteDataError(f"session leakage: session {session!r} appears in both splits")
        seen_ids.add(record_id)
        session_edges.add(edge_key)

    train = [record for record in records if record["split"] == "train"]
    test = [record for record in records if record["split"] == "test"]
    if not train or not test:
        raise RouteDataError("both train and test splits are required")
    if {r["session_id"] for r in train} & {r["session_id"] for r in test}:
        raise RouteDataError("train and test sessions must be disjoint")
    if not any(r["traversed"] for r in train):
        raise RouteDataError("training split requires labeled positive traversals")
    if not any(r["traversed"] for r in test) or not any(not r["traversed"] for r in test):
        raise RouteDataError("test split requires both positive and negative transitions")
    if any(not r["coordinates_validated"] or not r["clocks_synchronized"] for r in records):
        raise RouteDataError("coordinate and clock calibration must be independently validated before fitting travel-time windows")

    positives = defaultdict(list)
    negative_counts = defaultdict(int)
    for row in train:
        edge = (row["from_camera"], row["to_camera"])
        if row["traversed"]:
            positives[edge].append(row["elapsed_seconds"])
        else:
            negative_counts[edge] += 1
    edges = {}
    for edge, samples in positives.items():
        if len(samples) < MIN_POSITIVES_PER_EDGE:
            continue
        values = sorted(samples)
        edges[edge] = {
            "from_camera": edge[0], "to_camera": edge[1],
            "min_travel_seconds": float(round(_quantile(values, lower_quantile), 3)),
            "max_travel_seconds": float(round(_quantile(values, upper_quantile), 3)),
            "training_positive_samples": len(samples),
            "training_negative_samples": negative_counts[edge],
        }
    if not edges:
        raise RouteDataError(f"no directed edge has {MIN_POSITIVES_PER_EDGE} positive training sessions")

    matrix = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "unmodeled_positive": 0, "unmodeled_negative": 0}
    for row in test:
        edge = edges.get((row["from_camera"], row["to_camera"]))
        accepted = bool(edge and edge["min_travel_seconds"] <= row["elapsed_seconds"] <= edge["max_travel_seconds"])
        if edge is None:
            matrix["unmodeled_positive" if row["traversed"] else "unmodeled_negative"] += 1
        if row["traversed"]:
            matrix["tp" if accepted else "fn"] += 1
        else:
            matrix["fp" if accepted else "tn"] += 1
    positive_test = matrix["tp"] + matrix["fn"]
    negative_test = matrix["fp"] + matrix["tn"]
    precision_denominator = matrix["tp"] + matrix["fp"]
    return {
        "schema_version": 1,
        "status": "offline_review_candidate",
        "method": "session_split_empirical_travel_time_quantiles",
        "data_sha256": data_sha256,
        "train_records": len(train), "test_records": len(test),
        "train_sessions": len({row["session_id"] for row in train}),
        "test_sessions": len({row["session_id"] for row in test}),
        "split_dimensions": ["session_id"],
        "quantiles": {"lower": float(lower_quantile), "upper": float(upper_quantile)},
        "minimum_positive_training_sessions_per_edge": MIN_POSITIVES_PER_EDGE,
        "directed_edges": sorted(edges.values(), key=lambda row: (row["from_camera"], row["to_camera"])),
        "held_out_metrics": {
            **matrix,
            "positive_test_denominator": positive_test,
            "negative_test_denominator": negative_test,
            "accepted_candidate_precision": matrix["tp"] / precision_denominator if precision_denominator else None,
            "positive_traversal_recall": matrix["tp"] / positive_test if positive_test else None,
            "false_accept_rate_on_negatives": matrix["fp"] / negative_test if negative_test else None,
        },
        "confidence_is_calibrated": False,
        "calibration_assertions_independently_verified": False,
        "identity_linking_enabled": False,
        "production_constraints_written": False,
        "limitations": ["requires independently validated coordinates and synchronized clocks",
                        "operator review and independent external validation remain required",
                        "labeled session split does not prove broader route coverage"],
    }


def _quantile(values: list[float], q: float) -> float:
    # Linear interpolation matching the common empirical quantile convention.
    position = (len(values) - 1) * q
    lower = math.floor(position); upper = math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def run(input_path: Path, output_path: Path, *, lower_quantile: float = 0.05,
        upper_quantile: float = 0.95) -> Path:
    input_path = Path(input_path).resolve(strict=True)
    output_path = Path(output_path).resolve()
    if input_path == output_path:
        raise ValueError("output must not replace the transition dataset")
    if output_path.suffix.lower() != ".json":
        raise ValueError("output must use .json")
    if output_path.exists():
        raise FileExistsError("output already exists; choose a new path")
    records, digest = load_records(input_path)
    result = fit_and_evaluate(records, digest, lower_quantile=lower_quantile, upper_quantile=upper_quantile)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    fd, temporary_name = tempfile.mkstemp(prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        output_path.hardlink_to(temporary)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path, help="JSONL labeled candidate transitions with session-disjoint train/test split")
    parser.add_argument("--output", type=Path, required=True, help="new JSON review-candidate report")
    parser.add_argument("--lower-quantile", type=float, default=0.05)
    parser.add_argument("--upper-quantile", type=float, default=0.95)
    args = parser.parse_args()
    print(run(args.records, args.output, lower_quantile=args.lower_quantile,
              upper_quantile=args.upper_quantile))


if __name__ == "__main__":
    main()
