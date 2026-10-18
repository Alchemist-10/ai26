"""Compare last-read OCR with conservative per-track consensus on labeled sequences.

This runner accepts only synthetic fixtures. It checks sequence aggregation and
identity isolation; it does not measure a detector or OCR model.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fusion import PlateConsensus


MAX_RECORDS = 100_000
MAX_LINE_BYTES = 64 * 1024
MAX_INPUT_BYTES = 64 * 1024 * 1024


def evaluate(records: list[dict]) -> dict:
    if not isinstance(records, list) or not records or len(records) > MAX_RECORDS:
        raise ValueError(f"records must contain 1 to {MAX_RECORDS} labeled observations")
    seen_samples = set()
    last_frame = {}
    expected_by_track = {}
    reads_by_track = defaultdict(list)
    latest_by_track = {}
    consensuses = {}

    for row_number, row in enumerate(records, 1):
        if not isinstance(row, dict):
            raise ValueError(f"record {row_number} must be an object")
        sample_id = row.get("sample_id")
        camera = row.get("camera")
        session = row.get("session")
        track_id = row.get("track_id")
        frame_index = row.get("frame_index")
        expected = row.get("expected_plate")
        prediction = row.get("predicted_plate")
        association = row.get("association_status", "matched")
        confidence = row.get("confidence", 1.0)
        if not isinstance(sample_id, str) or not sample_id.strip() or sample_id in seen_samples:
            raise ValueError(f"record {row_number} needs a unique nonempty sample_id")
        seen_samples.add(sample_id)
        if row.get("synthetic") is not True:
            raise ValueError(f"record {row_number} must be explicitly marked synthetic")
        if any(not isinstance(value, str) or not value.strip() for value in (camera, session)):
            raise ValueError(f"record {row_number} needs nonempty camera and session labels")
        if isinstance(track_id, bool) or not isinstance(track_id, (str, int)) or not str(track_id).strip():
            raise ValueError(f"record {row_number} needs a nonempty string or integer track_id")
        if type(frame_index) is not int or frame_index < 0:
            raise ValueError(f"record {row_number} needs a nonnegative integer frame_index")
        if not isinstance(expected, str) or not expected.strip():
            raise ValueError(f"record {row_number} needs a nonempty expected_plate label")
        if prediction is not None and (not isinstance(prediction, str) or not prediction.strip()):
            raise ValueError(f"record {row_number} predicted_plate must be nonempty text or null")
        if association not in ("matched", "ambiguous"):
            raise ValueError(f"record {row_number} has an unsupported association_status")
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError(f"record {row_number} confidence must be finite and between 0 and 1")

        key = (camera, session, str(track_id))
        if key in last_frame and frame_index <= last_frame[key]:
            raise ValueError(f"record {row_number} frame_index is not increasing for its track")
        last_frame[key] = frame_index
        if key in expected_by_track and expected_by_track[key] != expected:
            raise ValueError(f"track {key} has conflicting expected_plate labels")
        expected_by_track[key] = expected
        latest_by_track[key] = prediction
        if prediction is not None:
            reads_by_track[key].append(prediction)
        consensus = consensuses.setdefault((camera, session), PlateConsensus())
        if association == "ambiguous":
            latest_result = consensus.read(camera, key[2], prediction or "", association, confidence)
        elif prediction is None:
            # A missing OCR result is not a character vote. Preserve a previous
            # consensus result, if any, while the last-read baseline remains null.
            latest_result = latest_by_track.get((key, "consensus"),
                                                {"identity_status": "unread", "fused_plate": None})
        else:
            latest_result = consensus.read(camera, key[2], prediction, association, confidence)
        latest_by_track[(key, "consensus")] = latest_result

    single_correct = single_incorrect = single_unread = 0
    fused_correct = fused_incorrect = fused_abstained = 0
    candidate_correct = candidate_incorrect = candidate_abstained = 0
    fusion_output_outside_track_reads = 0
    for key, expected in expected_by_track.items():
        single = latest_by_track[key]
        final = latest_by_track[(key, "consensus")]
        single_correct += single == expected
        single_incorrect += single is not None and single != expected
        single_unread += single is None
        fused = final.get("fused_plate")
        fused_correct += fused == expected
        fused_incorrect += fused is not None and fused != expected
        fused_abstained += fused is None
        candidate = final.get("character_consensus_candidate")
        candidate_correct += candidate == expected
        candidate_incorrect += candidate is not None and candidate != expected
        candidate_abstained += candidate is None
        if fused is not None and (final.get("identity_status") != "supported" or fused not in reads_by_track[key]):
            fusion_output_outside_track_reads += 1

    track_count = len(expected_by_track)
    supported = fused_correct + fused_incorrect
    candidate_coverage = candidate_correct + candidate_incorrect
    return {
        "schema_version": 2,
        "type": "synthetic_plate_fusion_comparison",
        "scope": "last OCR read versus per-camera/session/track consensus; synthetic sequence evaluation only",
        "sequence_count": track_count,
        "observation_count": len(records),
        "single_frame_last_read": {
            "exact": single_correct,
            "incorrect": single_incorrect,
            "unread": single_unread,
            "exact_rate": round(single_correct / track_count, 6),
        },
        "per_track_consensus": {
            "exact": fused_correct,
            "incorrect": fused_incorrect,
            "abstained": fused_abstained,
            "coverage_rate": round(supported / track_count, 6),
            "exact_rate_all_sequences": round(fused_correct / track_count, 6),
            "exact_rate_supported_only": round(fused_correct / supported, 6) if supported else None,
        },
        "review_only_character_candidate": {
            "exact": candidate_correct,
            "incorrect": candidate_incorrect,
            "abstained": candidate_abstained,
            "coverage_rate": round(candidate_coverage / track_count, 6),
            "exact_rate_all_sequences": round(candidate_correct / track_count, 6),
            "exact_rate_proposed_only": round(candidate_correct / candidate_coverage, 6) if candidate_coverage else None,
            "identity_status_overridden": False,
            "confidence_semantics": "heuristic_weight_share_not_calibrated_probability",
        },
        "identity_isolation": {
            "fused_outputs_outside_own_track_reads": fusion_output_outside_track_reads,
            "identity_linking_performed": False,
            "passed": fusion_output_outside_track_reads == 0,
        },
        "accuracy_claim": False,
        "limitations": "Synthetic labels validate aggregation behavior only; they do not measure detector/OCR accuracy, confidence calibration, or field identity risk.",
    }


def load_records(path: Path) -> list[dict]:
    rows = []
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"records file exceeds {MAX_INPUT_BYTES} bytes")
    total_bytes = 0
    with path.open("rb") as stream:
        for line_number, raw in enumerate(stream, 1):
            total_bytes += len(raw)
            if total_bytes > MAX_INPUT_BYTES:
                raise ValueError(f"records file exceeds {MAX_INPUT_BYTES} bytes")
            if len(raw) > MAX_LINE_BYTES:
                raise ValueError(f"record line {line_number} exceeds {MAX_LINE_BYTES} bytes")
            if not raw.strip():
                continue
            try:
                rows.append(json.loads(raw))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"record line {line_number} is not valid JSON") from exc
            if len(rows) > MAX_RECORDS:
                raise ValueError(f"records exceed {MAX_RECORDS} observations")
    return rows


def write_no_clobber(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True, help="synthetic labeled read-sequence JSONL")
    parser.add_argument("--output", type=Path, required=True, help="new report path; existing reports are never replaced")
    args = parser.parse_args()
    try:
        records = load_records(args.records)
        report = evaluate(records)
        report["input"] = {"sha256": hashlib.sha256(args.records.read_bytes()).hexdigest(),
                            "status": "synthetic_fixture"}
        write_no_clobber(args.output, report)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Compared {report['sequence_count']} sequences; identity isolation passed={report['identity_isolation']['passed']}; output={args.output}")


if __name__ == "__main__":
    main()
