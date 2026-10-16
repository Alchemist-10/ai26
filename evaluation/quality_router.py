"""Read-only rule-based image condition hints and offline enhancement suggestions."""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
import json
from pathlib import Path

import cv2
import numpy as np


def _image_metrics(image: np.ndarray, *, include_weather: bool) -> dict:
    """Return descriptive, uncalibrated image hints for one BGR region."""
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must be a uint8 BGR image with three channels")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    channel_means = image.astype(np.float32).mean(axis=(0, 1))
    features = {
        "mean_luminance": round(float(gray.mean()), 3),
        "luminance_stddev": round(float(gray.std()), 3),
        "laplacian_variance": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 3),
        "mean_saturation": round(float(hsv[:, :, 1].mean()), 3),
        "clipped_dark_fraction": round(float((gray <= 5).mean()), 5),
        "clipped_bright_fraction": round(float((gray >= 250).mean()), 5),
        "bgr_channel_means": [round(float(x), 3) for x in channel_means],
    }
    flags = []
    suggestions = ["raw"]  # raw is always retained as the comparison/reference branch
    if features["mean_luminance"] < 70:
        flags.append("low_light_possible")
        suggestions.extend(("gamma", "clahe"))
    if features["mean_luminance"] > 205 or features["clipped_bright_fraction"] > 0.1:
        flags.append("overexposure_possible")
    if features["luminance_stddev"] < 35:
        flags.append("low_contrast_possible")
        suggestions.append("clahe")
    if features["laplacian_variance"] < 80:
        flags.append("low_sharpness_possible")
        suggestions.append("unsharp")
    nonzero = channel_means[channel_means > 1]
    if nonzero.size == 3 and float(nonzero.max() / nonzero.min()) > 1.5:
        flags.append("color_cast_possible")
        suggestions.append("gray_world")
    haze_like = include_weather and features["luminance_stddev"] < 45 and features["mean_saturation"] < 65
    if haze_like:
        flags.append("haze_or_fog_like_low_contrast")
        suggestions.append("dark_channel")
    return {"features": features, "flags": flags, "enhancement_candidates": list(dict.fromkeys(suggestions)),
            "haze_like": haze_like}


def _validate_plate_boxes(plate_boxes, width: int, height: int) -> list[tuple[int, int, int, int]]:
    if plate_boxes is None:
        return []
    if not isinstance(plate_boxes, (list, tuple)) or len(plate_boxes) > 100:
        raise ValueError("plate_boxes must be a list of at most 100 xyxy boxes")
    result = []
    for index, box in enumerate(plate_boxes):
        if not isinstance(box, (list, tuple)) or len(box) != 4 or any(type(value) is not int for value in box):
            raise ValueError(f"plate box {index} must contain four integer xyxy coordinates")
        x1, y1, x2, y2 = box
        if x1 < 0 or y1 < 0 or x2 > width or y2 > height or x2 <= x1 or y2 <= y1:
            raise ValueError(f"plate box {index} must be a nonempty region inside the image bounds")
        result.append((x1, y1, x2, y2))
    return result


def inspect(image: np.ndarray, plate_boxes=None, *, plate_box_source="operator_supplied",
            plate_model_metadata=None) -> dict:
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must be a uint8 BGR image with three channels")
    height, width = image.shape[:2]
    whole = _image_metrics(image, include_weather=True)
    regions = []
    for index, (x1, y1, x2, y2) in enumerate(_validate_plate_boxes(plate_boxes, width, height)):
        crop = image[y1:y2, x1:x2]
        assessment = _image_metrics(crop, include_weather=False)
        regions.append({
            "region_index": index,
            "box_xyxy": [x1, y1, x2, y2],
            "width": x2 - x1,
            "height": y2 - y1,
            "features": assessment["features"],
            "flags": assessment["flags"],
            "suggested_ocr_preprocessing": assessment["enhancement_candidates"],
            "routing_status": "review_only_no_live_route",
            "weather_is_assessed": False,
            "accuracy_claim": False,
        })
    return {
        "schema_version": 1,
        "type": "heuristic_image_condition_report",
        "image_dimensions": {"width": width, "height": height},
        "features": whole["features"],
        "flags": whole["flags"],
        "weather_assessment": "possible_haze_or_fog_like_appearance" if whole["haze_like"] else "undetermined",
        "weather_is_verified": False,
        "enhancement_candidates": whole["enhancement_candidates"],
        "plate_region_assessments": regions,
        "plate_box_source": plate_box_source,
        "plate_model_metadata": plate_model_metadata if plate_box_source.startswith("selected_alpr_detector") else None,
        "raw_reference_retained": True,
        "accuracy_claim": False,
        "limitations": "Fixed image-statistic thresholds are not a trained quality or weather classifier; detector-supplied or operator-supplied plate boxes may be wrong, recommendations are review-only, and conditions/OCR performance require labeled validation.",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_plate_box(value: str) -> tuple[int, int, int, int]:
    try:
        fields = value.split(",")
        if len(fields) != 4 or any(not field.strip() for field in fields):
            raise ValueError
        return tuple(int(field.strip()) for field in fields)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("plate boxes use integer x1,y1,x2,y2 coordinates") from exc


def _detect_plate_boxes(image: np.ndarray, model_loader=None) -> tuple[list[tuple[int, int, int, int]], dict]:
    """Use the selected digest-snapshotted detector and deliberately discard OCR text."""
    if model_loader is None:
        backend = str(Path(__file__).resolve().parents[1] / "backend")
        if backend not in sys.path:
            sys.path.insert(0, backend)
        from model_provenance import load_plate_model
        model_loader = load_plate_model
    model, metadata = model_loader(cpu_threads=2, device="cpu")
    results = model.predict(image)
    height, width = image.shape[:2]
    boxes = []
    for result in results:
        detection = getattr(result, "detection", None)
        box = getattr(detection, "bounding_box", None)
        coordinates = [getattr(box, name, None) for name in ("x1", "y1", "x2", "y2")]
        if any(type(value) not in (int, float) or not np.isfinite(value) for value in coordinates):
            continue
        x1, y1, x2, y2 = (int(round(value)) for value in coordinates)
        x1, y1, x2, y2 = max(0, x1), max(0, y1), min(width, x2), min(height, y2)
        if x2 > x1 and y2 > y1:
            boxes.append((x1, y1, x2, y2))
    return boxes, metadata


def run(path: Path, plate_boxes=None, *, detect_plates=False, model_loader=None) -> dict:
    path = path.resolve(strict=True)
    digest = _sha256(path)
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"cannot decode image: {path}")
    model_metadata = None
    box_source = "operator_supplied" if plate_boxes else "none"
    if detect_plates:
        if plate_boxes:
            raise ValueError("automatic detection and operator-supplied boxes cannot be combined")
        plate_boxes, model_metadata = _detect_plate_boxes(image, model_loader=model_loader)
        box_source = "selected_alpr_detector" if plate_boxes else "selected_alpr_detector_no_candidates"
    report = inspect(image, plate_boxes=plate_boxes, plate_box_source=box_source,
                     plate_model_metadata=model_metadata)
    report["source"] = {"path": path.name, "sha256": digest, "status": "read_only_raw_reference"}
    if _sha256(path) != digest:
        raise RuntimeError("source image changed during inspection")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--plate-box", action="append", type=parse_plate_box, default=[], metavar="X1,Y1,X2,Y2",
                        help="optional operator-supplied plate crop; may be repeated")
    parser.add_argument("--detect-plates", action="store_true",
                        help="explicitly run the selected hash-snapshotted ALPR detector for review-only boxes; may download models")
    parser.add_argument("--output", type=Path, required=True, help="new JSON report path; existing file is never replaced")
    args = parser.parse_args()
    try:
        report = run(args.image, plate_boxes=args.plate_box, detect_plates=args.detect_plates)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        fd, temp_name = tempfile.mkstemp(dir=args.output.parent, prefix=f".{args.output.name}.")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temp_name, args.output)
        finally:
            Path(temp_name).unlink(missing_ok=True)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
