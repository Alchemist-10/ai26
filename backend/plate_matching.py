"""Review-only plate similarity and labeled-pair evaluation helpers.

Scores are heuristics, not probabilities. Nothing here accepts or links identity.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from statistics import NormalDist

from plate_format import normalize_plate


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
    exact = distance == 0
    candidate = score >= float(candidate_threshold)
    return {
        "status": "exact_text" if exact else "review_candidate" if candidate else "below_threshold",
        "left_plate_norm": left_value,
        "right_plate_norm": right_value,
        "edit_distance": distance,
        "similarity_score": similarity,
        "review_score": score,
        "candidate_threshold": float(candidate_threshold),
        "left_repairs": left_norm["repairs"],
        "right_repairs": right_norm["repairs"],
        "score_is_probability": False,
        "identity_linked": False,
        "requires_human_review": not exact and candidate,
    }


def evaluate_labeled_pairs(
    records: Iterable[dict], thresholds: Iterable[float], *, confidence_level: float = 0.95
) -> dict:
    """Measure candidate false-link rates on explicitly labeled independent pairs."""
    if (not isinstance(confidence_level, (int, float)) or isinstance(confidence_level, bool)
            or not math.isfinite(confidence_level) or not 0 < confidence_level < 1):
        raise ValueError("confidence_level must be a finite number in (0, 1)")
    confidence_level = float(confidence_level)
    rows = list(records)
    if not rows:
        raise ValueError("at least one labeled pair is required")
    labels = []
    scores = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or type(row.get("same_vehicle")) is not bool:
            raise ValueError(f"record {index} needs a boolean same_vehicle label")
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
    for threshold in thresholds:
        if (not isinstance(threshold, (int, float)) or isinstance(threshold, bool)
                or not math.isfinite(threshold) or not 0 <= threshold <= 1):
            raise ValueError("thresholds must be finite numbers in [0, 1]")
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
    return {"schema_version": 1, "type": "review_only_plate_similarity_evaluation",
            "identity_linking_enabled": False,
            "uncertainty": {
                "method": "two-sided_wilson_score_interval",
                "confidence_level": confidence_level,
                "assumption": "Binomial intervals require independent labeled pairs; they do not correct for split leakage or correlated frames.",
            },
            "threshold_results": output}
