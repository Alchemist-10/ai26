"""Run a bounded, sanitized preprocessing probe on one privately reviewed crop."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

VARIANT_NAMES = (
    "cubic_upscale_4x",
    "cubic_upscale_6x",
    "lanczos_upscale_4x",
    "grayscale",
    "clahe",
    "grayscale_contrast_alpha_1_5_beta_minus_25",
    "clahe_gaussian_blur_sigma_1_2",
    "clahe_unsharp",
    "clahe_binary_threshold_100",
    "clahe_binary_threshold_130",
    "clahe_binary_threshold_160",
    "clahe_binary_threshold_190",
    "clahe_adaptive_threshold_block_11",
    "clahe_adaptive_threshold_block_17",
    "clahe_adaptive_threshold_block_25",
    "white_border_padding",
    "black_border_padding",
)


def _canonical(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _summarize_variant_predictions(model, candidates, label: str) -> dict:
    """Count potentially usable variants without retaining or printing OCR text."""
    from plate_format import normalize_plate

    passing = []
    exact = []
    exact_passing = []
    inexact_passing = []
    for index, candidate in enumerate(candidates):
        result = model.ocr.predict(candidate)
        prediction = getattr(result, "text", "") or ""
        confidence = getattr(result, "confidence", 0.0)
        if isinstance(confidence, (list, tuple)):
            confidence = sum(confidence) / len(confidence) if confidence else 0.0
        normalized = normalize_plate(prediction)
        is_exact = _canonical(prediction) == label
        if is_exact:
            exact.append(index)
        if (normalized["format_valid"] and isinstance(confidence, (int, float))
                and not isinstance(confidence, bool) and confidence >= 0.35):
            passing.append(index)
            (exact_passing if is_exact else inexact_passing).append(index)
    return {
        "exact_match_variant_indices": exact,
        "variants_passing_format_and_confidence_gates": len(passing),
        "exact_gate_passing_variant_indices": exact_passing,
        "inexact_gate_passing_variant_indices": inexact_passing,
        "ocr_text_recorded": False,
    }


def _variants(image):
    import cv2

    base = cv2.resize(image, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)

    def color(value):
        return cv2.cvtColor(value, cv2.COLOR_GRAY2BGR)

    candidates = [
        base,
        cv2.resize(image, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC),
        cv2.resize(image, None, fx=4, fy=4, interpolation=cv2.INTER_LANCZOS4),
        color(gray),
        color(clahe),
        color(cv2.convertScaleAbs(gray, alpha=1.5, beta=-25)),
        color(cv2.GaussianBlur(clahe, (0, 0), 1.2)),
        color(cv2.addWeighted(clahe, 1.7, cv2.GaussianBlur(clahe, (0, 0), 1.5), -0.7, 0)),
    ]
    for threshold in (100, 130, 160, 190):
        _, binary = cv2.threshold(clahe, threshold, 255, cv2.THRESH_BINARY)
        candidates.append(color(binary))
    for block in (11, 17, 25):
        binary = cv2.adaptiveThreshold(
            clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 3
        )
        candidates.append(color(binary))
    candidates.extend(
        [
            cv2.copyMakeBorder(base, 40, 40, 60, 60, cv2.BORDER_CONSTANT, value=(255, 255, 255)),
            cv2.copyMakeBorder(base, 80, 80, 120, 120, cv2.BORDER_CONSTANT, value=(0, 0, 0)),
        ]
    )
    if len(candidates) != len(VARIANT_NAMES):
        raise RuntimeError("preprocessing variant map is inconsistent")
    return candidates


def _source_frame_probe(manifest_path: Path, sample: dict, model, label: str) -> dict:
    import cv2
    import numpy as np

    camera_id = sample.get("camera_id")
    source_digest = sample.get("source_sha256")
    frame_index = sample.get("frame_id")
    data_root = next(
        (
            ancestor
            for ancestor in manifest_path.parents
            if (ancestor / "sources" / str(camera_id) / "active.json").is_file()
        ),
        None,
    )
    if data_root is None:
        raise ValueError("could not locate active source catalog for reviewed sample")
    active_path = data_root / "sources" / str(camera_id) / "active.json"
    if not isinstance(source_digest, str) or not re.fullmatch(r"[a-f0-9]{64}", source_digest):
        raise ValueError("reviewed sample source digest is invalid")
    if not isinstance(frame_index, int) or isinstance(frame_index, bool) or frame_index < 0:
        raise ValueError("reviewed sample frame index is invalid")
    active = json.loads(active_path.read_text())
    original = active.get("original", {})
    release = active.get("release")
    if original.get("sha256") != source_digest or not isinstance(release, str):
        raise ValueError("reviewed sample does not match the active source release")
    source_path = (active_path.parent / "releases" / release / original.get("file", "")).resolve()
    try:
        source_path.relative_to((active_path.parent / "releases" / release).resolve())
    except ValueError as error:
        raise ValueError("active source path escaped release folder") from error
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if source_hash != source_digest:
        raise ValueError("active source digest does not match reviewed sample")
    capture = cv2.VideoCapture(str(source_path))
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok or frame is None:
        raise ValueError("reviewed source frame could not be decoded")

    height, width = frame.shape[:2]
    reviewed_box = sample.get("crop_bbox")
    if (
        not isinstance(reviewed_box, list)
        or len(reviewed_box) != 4
        or any(not isinstance(value, int) or isinstance(value, bool) for value in reviewed_box)
    ):
        raise ValueError("reviewed source box is invalid")
    x1, y1, x2, y2 = reviewed_box
    if x1 < 0 or y1 < 0 or x2 > width or y2 > height or x2 <= x1 or y2 <= y1:
        raise ValueError("reviewed source box is outside the decoded frame")

    detections = model.predict(frame)
    overlapping = 0
    full_frame_matches = 0
    contrast_crop_matches = 0
    contrast_crop_gate_passes = 0
    from plate_format import normalize_plate

    for result in detections:
        bounds = result.detection.bounding_box
        box = [int(bounds.x1), int(bounds.y1), int(bounds.x2), int(bounds.y2)]
        ix1, iy1 = max(box[0], x1), max(box[1], y1)
        ix2, iy2 = min(box[2], x2), min(box[3], y2)
        intersection = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        box_area = max(0, box[2] - box[0]) * max(0, box[3] - box[1])
        reviewed_area = (x2 - x1) * (y2 - y1)
        union = box_area + reviewed_area - intersection
        if union and intersection / union >= 0.25:
            overlapping += 1
        if result.ocr and _canonical(result.ocr.text or "") == label:
            full_frame_matches += 1
        if union and intersection / union >= 0.25:
            plate_crop = frame[box[1]:box[3], box[0]:box[2]]
            if plate_crop.size:
                contrast_candidate = _variants(plate_crop)[5]
                contrast_result = model.ocr.predict(contrast_candidate)
                contrast_text = getattr(contrast_result, "text", "") or ""
                if _canonical(contrast_text) == label:
                    contrast_crop_matches += 1
                    confidence = getattr(contrast_result, "confidence", 0.0)
                    if isinstance(confidence, (list, tuple)):
                        confidence = sum(confidence) / len(confidence) if confidence else 0.0
                    normalized = normalize_plate(contrast_text)
                    if normalized["format_valid"] and isinstance(confidence, (int, float)) and confidence >= 0.35:
                        contrast_crop_gate_passes += 1

    pad_x, pad_y = round((x2 - x1) * 0.25), round((y2 - y1) * 0.25)
    xa, ya = max(0, x1 - pad_x), max(0, y1 - pad_y)
    xb, yb = min(width, x2 + pad_x), min(height, y2 + pad_y)
    region = frame[ya:yb, xa:xb]
    enlarged = cv2.resize(region, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    region_result = model.ocr.predict(enlarged)
    region_match = _canonical(getattr(region_result, "text", "") or "") == label
    return {
        "source_sha256": source_digest,
        "frame_index": frame_index,
        "frame_dimensions": [width, height],
        "detected_plate_count": len(detections),
        "detections_overlapping_reviewed_box_iou_025": overlapping,
        "full_frame_exact_matches": full_frame_matches,
        "detected_crop_contrast_exact_matches": contrast_crop_matches,
        "detected_crop_contrast_matches_passing_format_and_confidence_gates": contrast_crop_gate_passes,
        "expanded_review_box_ocr_exact_match": region_match,
        "ocr_text_recorded": False,
        "image_recorded": False,
    }


def probe(manifest_path: Path, sample_id: str, *, cpu_threads: int = 2) -> dict:
    import cv2
    import numpy as np

    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text())
    samples = manifest.get("samples")
    if not isinstance(samples, list):
        raise ValueError("review manifest has no samples list")
    sample = next(
        (item for item in samples if isinstance(item, dict) and item.get("sample_id") == sample_id),
        None,
    )
    if sample is None or sample.get("ground_truth_status") != "reviewed":
        raise ValueError("sample is missing or not reviewed")
    if sample.get("plate_readability") != "readable":
        raise ValueError("sample is not marked readable")
    digest = sample.get("crop_sha256")
    relative_path = sample.get("crop_path")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("sample crop digest is invalid")
    if not isinstance(relative_path, str):
        raise ValueError("sample crop path is invalid")
    crop_path = (manifest_path.parent / relative_path).resolve()
    try:
        crop_path.relative_to(manifest_path.parent)
    except ValueError as error:
        raise ValueError("sample crop path escaped manifest folder") from error
    content = crop_path.read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError("sample crop digest does not match")
    label = sample.get("ground_truth_plate")
    if not isinstance(label, str) or not _canonical(label):
        raise ValueError("reviewed sample has no usable private label")
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("reviewed crop could not be decoded")

    from model_provenance import load_plate_model

    model, metadata = load_plate_model(cpu_threads=cpu_threads, device="cpu")
    candidates = _variants(image)
    variant_gate_summary = _summarize_variant_predictions(model, candidates, _canonical(label))
    exact_match_indices = variant_gate_summary["exact_match_variant_indices"]
    source_frame = _source_frame_probe(manifest_path, sample, model, _canonical(label))
    return {
        "sample_id": sample_id,
        "crop_sha256": digest,
        "ocr_model": metadata.get("ocr_model"),
        "device": "CPUExecutionProvider",
        "variants_tested": len(candidates),
        "exact_match_variants": len(exact_match_indices),
        "exact_match_variant_indices": exact_match_indices,
        "exact_match_variant_names": [VARIANT_NAMES[index] for index in exact_match_indices],
        "any_exact_match": bool(exact_match_indices),
        "variant_gate_summary": variant_gate_summary,
        "source_frame_probe": source_frame,
        "ocr_text_recorded": False,
        "image_recorded": False,
        "scope": "One reviewed crop and a fixed preprocessing set; not an accuracy estimate or production change.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--cpu-threads", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.cpu_threads <= 8:
        parser.error("--cpu-threads must be 1–8")
    try:
        result = probe(args.manifest, args.sample_id, cpu_threads=args.cpu_threads)
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as error:
        print(f"offline OCR probe failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
