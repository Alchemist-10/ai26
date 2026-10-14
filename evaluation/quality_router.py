"""Read-only rule-based image condition hints and offline enhancement suggestions."""
from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
import json
from pathlib import Path

import cv2
import numpy as np


def inspect(image: np.ndarray) -> dict:
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
    haze_like = features["luminance_stddev"] < 45 and features["mean_saturation"] < 65
    if haze_like:
        flags.append("haze_or_fog_like_low_contrast")
        suggestions.append("dark_channel")
    return {
        "schema_version": 1,
        "type": "heuristic_image_condition_report",
        "features": features,
        "flags": flags,
        "weather_assessment": "possible_haze_or_fog_like_appearance" if haze_like else "undetermined",
        "weather_is_verified": False,
        "enhancement_candidates": list(dict.fromkeys(suggestions)),
        "raw_reference_retained": True,
        "accuracy_claim": False,
        "limitations": "Fixed image-statistic thresholds are not a trained quality or weather classifier; conditions and OCR performance require labeled validation.",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(path: Path) -> dict:
    path = path.resolve(strict=True)
    digest = _sha256(path)
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"cannot decode image: {path}")
    report = inspect(image)
    report["source"] = {"path": path.name, "sha256": digest, "status": "read_only_raw_reference"}
    if _sha256(path) != digest:
        raise RuntimeError("source image changed during inspection")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="new JSON report path; existing file is never replaced")
    args = parser.parse_args()
    try:
        report = run(args.image)
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
