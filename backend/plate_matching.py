"""Review-only plate similarity and labeled-pair evaluation helpers.

Scores are heuristics, not probabilities. Nothing here accepts or links identity.
"""
from __future__ import annotations

import math
import re
from collections.abc import Iterable
from statistics import NormalDist

from plate_format import normalize_plate

_MAX_EVALUATION_PAIRS = 100_000
_MAX_THRESHOLDS = 100
_MAX_RAW_PLATE_CHARS = 64


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, 1):
        current = [row]
        for column, right_char in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[column] + 1,
                               previous[column - 1] + (left_char != right_char)))
        previous = current
    return previous[-1]


def _confidence(value: float | None, field: str) -> float | None:
    if value is None:
        return None
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(value) or not 0 <= value <= 1):
        raise ValueError(f"{field} must be a finite number in [0, 1]")
    return float(value)


def _wilson_interval(successes: int, trials: int, confidence_level: float) -> dict | None:
    """Return a two-sided Wilson score interval for a binomial proportion."""
    if trials == 0:
        return None
    z = NormalDist().inv_cdf((1 + confidence_level) / 2)
    proportion = successes / trials
    z2 = z * z
    denominator = 1 + z2 / trials
    center = (proportion + z2 / (2 * trials)) / denominator
    margin = z * math.sqrt((proportion * (1 - proportion) + z2 / (4 * trials)) / trials) / denominator
    return {"lower": max(0.0, center - margin), "upper": min(1.0, center + margin)}


def compare_plates(
    left: str,
    right: str,
    *,
    left_ocr_confidence: float | None = None,
    right_ocr_confidence: float | None = None,
    candidate_threshold: float = 0.9,
) -> dict:
    """Score a plate pair for human review; never promote it to an identity link."""
    if not isinstance(left, str) or not isinstance(right, str):
        raise ValueError("plate strings are required")
    if len(left) > _MAX_RAW_PLATE_CHARS or len(right) > _MAX_RAW_PLATE_CHARS:
        raise ValueError(f"plate strings are limited to {_MAX_RAW_PLATE_CHARS} characters")
    if (not isinstance(candidate_threshold, (int, float)) or isinstance(candidate_threshold, bool)
            or not math.isfinite(candidate_threshold) or not 0 <= candidate_threshold <= 1):
        raise ValueError("candidate_threshold must be a finite number in [0, 1]")
    left_conf = _confidence(left_ocr_confidence, "left_ocr_confidence")
    right_conf = _confidence(right_ocr_confidence, "right_ocr_confidence")
    if (left_conf is None) != (right_conf is None):
        raise ValueError("supply both OCR confidences or neither")
    left_norm = normalize_plate(left)
    right_norm = normalize_plate(right)
    if not left_norm["format_valid"] or not right_norm["format_valid"]:
        return {"status": "not_comparable", "left_repairs": left_norm["repairs"],
                "right_repairs": right_norm["repairs"], "identity_linked": False,
                "score_is_probability": False}

    left_value, right_value = str(left_norm["plate_norm"]), str(right_norm["plate_norm"])
    distance = _edit_distance(left_value, right_value)
    similarity = 1.0 - distance / max(len(left_value), len(right_value))
    score = similarity
    if left_conf is not None and right_conf is not None:
        score *= math.sqrt(left_conf * right_conf)
    raw_characters_equal = re.sub(r"[^A-Z0-9]", "", left.upper()) == re.sub(r"[^A-Z0-9]", "", right.upper())
    normalization_equivalent = distance == 0
    candidate = score >= float(candidate_threshold)
    status = ("same_observed_characters" if raw_characters_equal else
              "same_after_ocr_repair" if normalization_equivalent else
              "review_candidate" if candidate else "below_threshold")
    return {
        "status": status,
        "left_plate_norm": left_value,
        "right_plate_norm": right_value,
        "edit_distance": distance,
        "similarity_score": similarity,
        "review_score": score,
        "candidate_threshold": float(candidate_threshold),
        "raw_characters_equal": raw_characters_equal,
        "normalization_equivalent": normalization_equivalent,
        "left_repairs": left_norm["repairs"],
        "right_repairs": right_norm["repairs"],
        "score_is_probability": False,
        "identity_linked": False,
        "requires_human_review": (not raw_characters_equal and
                                  (normalization_equivalent or candidate)),
    }


def evaluate_labeled_pairs(
    records: Iterable[dict], thresholds: Iterable[float], *, confidence_level: float = 0.95
) -> dict:
    """Measure review-candidate rates on uniquely identified labeled read pairs.

    Vehicle and session identifiers are disjoint across pair rows, and read IDs
    cannot be reused. IDs and labels are caller supplied and cannot prove their
    own truth; camera/location grouping still belongs to dataset construction.
    """
    if (not isinstance(confidence_level, (int, float)) or isinstance(confidence_level, bool)
            or not math.isfinite(confidence_level) or not 0 < confidence_level < 1):
        raise ValueError("confidence_level must be a finite number in (0, 1)")
    confidence_level = float(confidence_level)
    rows = []
    for row in records:
        if len(rows) >= _MAX_EVALUATION_PAIRS:
            raise ValueError(f"evaluation is limited to {_MAX_EVALUATION_PAIRS} pairs")
        rows.append(row)
    if not rows:
        raise ValueError("at least one labeled pair is required")
    threshold_values = []
    for threshold in thresholds:
        if len(threshold_values) >= _MAX_THRESHOLDS:
            raise ValueError(f"evaluation is limited to {_MAX_THRESHOLDS} thresholds")
        if (not isinstance(threshold, (int, float)) or isinstance(threshold, bool)
                or not math.isfinite(threshold) or not 0 <= threshold <= 1):
            raise ValueError("thresholds must be finite numbers in [0, 1]")
        threshold_values.append(float(threshold))
    if not threshold_values:
        raise ValueError("at least one threshold is required")
    if len(set(threshold_values)) != len(threshold_values):
        raise ValueError("thresholds must be unique")
    labels = []
    scores = []
    pair_ids = set()
    read_ids = set()
    vehicle_ids = set()
    session_ids = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or type(row.get("same_vehicle")) is not bool:
            raise ValueError(f"record {index} needs a boolean same_vehicle label")
        pair_id = row.get("pair_id")
        left_read_id = row.get("left_read_id")
        right_read_id = row.get("right_read_id")
        left_vehicle_id = row.get("left_vehicle_id")
        right_vehicle_id = row.get("right_vehicle_id")
        left_session_id = row.get("left_session_id")
        right_session_id = row.get("right_session_id")
        if any(not isinstance(value, str) or not value.strip()
               for value in (pair_id, left_read_id, right_read_id, left_vehicle_id,
                             right_vehicle_id, left_session_id, right_session_id)):
            raise ValueError(f"record {index} needs non-empty pair_id, read, vehicle and session IDs")
        if pair_id in pair_ids:
            raise ValueError(f"record {index} reuses pair_id {pair_id!r}")
        if left_read_id == right_read_id or left_read_id in read_ids or right_read_id in read_ids:
            raise ValueError(f"record {index} reuses a read ID; each read may appear only once")
        row_vehicle_ids = {left_vehicle_id, right_vehicle_id}
        row_session_ids = {left_session_id, right_session_id}
        if vehicle_ids.intersection(row_vehicle_ids):
            raise ValueError(f"record {index} reuses a vehicle across pair rows")
        if session_ids.intersection(row_session_ids):
            raise ValueError(f"record {index} reuses a session across pair rows")
        if (left_vehicle_id == right_vehicle_id) != row["same_vehicle"]:
            raise ValueError(f"record {index} label disagrees with vehicle IDs")
        pair_ids.add(pair_id)
        read_ids.update((left_read_id, right_read_id))
        vehicle_ids.update(row_vehicle_ids)
        session_ids.update(row_session_ids)
        comparison = compare_plates(
            row.get("left_plate"), row.get("right_plate"),
            left_ocr_confidence=row.get("left_ocr_confidence"),
            right_ocr_confidence=row.get("right_ocr_confidence"),
            candidate_threshold=0.0,
        )
        if comparison["status"] == "not_comparable":
            raise ValueError(f"record {index} contains an invalid plate string")
        labels.append(row["same_vehicle"])
        scores.append(comparison["review_score"])
    if not any(labels) or all(labels):
        raise ValueError("labeled pairs must contain both positive and negative examples")

    output = []
    for threshold in threshold_values:
        selected = [score >= threshold for score in scores]
        tp = sum(predicted and label for predicted, label in zip(selected, labels))
        fp = sum(predicted and not label for predicted, label in zip(selected, labels))
        positives, negatives = sum(labels), len(labels) - sum(labels)
        output.append({
            "threshold": float(threshold),
            "pair_count": len(labels),
            "positive_pair_count": positives,
            "negative_pair_count": negatives,
            "candidate_count": sum(selected),
            "true_candidate_count": tp,
            "false_candidate_count": fp,
            "false_candidate_fraction_among_candidates": fp / sum(selected) if any(selected) else None,
            "false_positive_candidate_rate_on_negative_pairs": fp / negatives,
            "recall_on_positive_pairs": tp / positives,
            "false_candidate_fraction_among_candidates_wilson_interval": _wilson_interval(
                fp, sum(selected), confidence_level),
            "false_positive_candidate_rate_on_negative_pairs_wilson_interval": _wilson_interval(
                fp, negatives, confidence_level),
            "recall_on_positive_pairs_wilson_interval": _wilson_interval(
                tp, positives, confidence_level),
            "measurement_scope": "labeled_pairs_only_not_live_accuracy",
            "scores_are_probabilities": False,
        })
    return {"schema_version": 2, "type": "review_only_plate_similarity_evaluation",
            "identity_linking_enabled": False,
            "pair_read_ids_unique": True,
            "pair_vehicle_and_session_ids_disjoint": True,
            "independence_note": "Vehicle and session IDs are disjoint across pair rows; camera/location grouping, ID truth, labels and residual correlation remain dataset responsibilities.",
            "uncertainty": {
                "method": "two-sided_wilson_score_interval",
                "confidence_level": confidence_level,
                "assumption": "Binomial intervals require independent labeled pairs; they do not correct for split leakage or correlated frames.",
            },
            "threshold_results": output}
