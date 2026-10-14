"""Generate controlled synthetic image degradations for offline research only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import cv2
import numpy as np


CONDITIONS = ("rain", "fog", "low_light", "motion_blur", "sensor_noise")


def _image(image: np.ndarray) -> np.ndarray:
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must be a uint8 BGR image with three channels")
    if image.shape[0] < 2 or image.shape[1] < 2:
        raise ValueError("image must be at least 2 by 2 pixels")
    return image


def degrade(image: np.ndarray, condition: str, severity: float = 0.5, seed: int = 0) -> tuple[np.ndarray, dict]:
    """Return a deterministic uint8 BGR research derivative and exact parameters."""
    image = _image(image)
    if condition not in CONDITIONS:
        raise ValueError(f"condition must be one of: {', '.join(CONDITIONS)}")
    if not isinstance(severity, (int, float)) or isinstance(severity, bool) or not math.isfinite(severity) or not 0.0 < severity <= 1.0:
        raise ValueError("severity must be a finite number in (0, 1]")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("seed must be an integer from 0 to 4294967295")
    rng = np.random.default_rng(seed)
    level = float(severity)
    height, width = image.shape[:2]

    if condition == "rain":
        overlay = np.zeros_like(image)
        streak_count = max(1, int(height * width * level / 1800))
        streak_length = max(3, int(4 + 20 * level))
        for _ in range(streak_count):
            x = int(rng.integers(0, width))
            y = int(rng.integers(0, height))
            drift = int(rng.integers(-4, 5))
            end = (max(0, min(width - 1, x + drift)), min(height - 1, y + streak_length))
            cv2.line(overlay, (x, y), end, (225, 232, 238), 1, cv2.LINE_AA)
        alpha = 0.12 + 0.38 * level
        result = cv2.addWeighted(image, 1.0, overlay, alpha, 0)
        parameters = {"streak_count": streak_count, "streak_length_px": streak_length, "overlay_opacity": round(alpha, 4)}
    elif condition == "fog":
        transmittance = 1.0 - 0.7 * level
        airlight = int(round(205 + 45 * level))
        result = np.clip(image.astype(np.float32) * transmittance + airlight * (1 - transmittance), 0, 255).astype(np.uint8)
        parameters = {"transmittance": round(transmittance, 4), "airlight_bgr": [airlight] * 3}
    elif condition == "low_light":
        gamma = 1.0 + 2.5 * level
        table = np.clip(np.power(np.arange(256, dtype=np.float32) / 255.0, gamma) * 255, 0, 255).astype(np.uint8)
        result = cv2.LUT(image, table)
        parameters = {"gamma": round(gamma, 4)}
    elif condition == "motion_blur":
        size = max(3, int(round(3 + 14 * level)))
        if size % 2 == 0:
            size += 1
        angle = float(rng.uniform(-20, 20))
        kernel = np.zeros((size, size), dtype=np.float32)
        center = size // 2
        radians = np.deg2rad(angle)
        dx = int(round(np.cos(radians) * center))
        dy = int(round(np.sin(radians) * center))
        cv2.line(kernel, (center - dx, center - dy), (center + dx, center + dy), 1.0, 1, cv2.LINE_8)
        kernel /= max(float(kernel.sum()), 1.0)
        result = cv2.filter2D(image, -1, kernel, borderType=cv2.BORDER_REFLECT_101)
        parameters = {"kernel_size": size, "angle_degrees": round(angle, 4)}
    else:
        standard_deviation = 2.0 + 38.0 * level
        noise = rng.normal(0, standard_deviation, image.shape).astype(np.float32)
        result = np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        parameters = {"gaussian_standard_deviation": round(standard_deviation, 4)}

    return result, {"condition": condition, "severity": level, "seed": seed, **parameters}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def run(input_path: Path, output_path: Path, condition: str, severity: float = 0.5, seed: int = 0) -> Path:
    source = input_path.resolve(strict=True)
    output = output_path.resolve()
    if output.suffix.lower() != ".png":
        raise ValueError("output path must use the .png extension")
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    if output == source or manifest_path == source:
        raise ValueError("output and manifest must not overwrite the source image")
    if output.exists() or manifest_path.exists():
        raise FileExistsError("output image or manifest already exists; choose new output paths")
    source_hash = _sha256_file(source)
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"cannot decode image: {source}")
    transformed, parameters = degrade(image, condition, severity, seed)
    ok, encoded = cv2.imencode(".png", transformed)
    if not ok:
        raise RuntimeError("could not encode degraded derivative")
    encoded_bytes = encoded.tobytes()
    manifest = {
        "schema_version": 1,
        "type": "synthetic_degradation_manifest",
        "source": {"path": source.name, "sha256": source_hash, "status": "raw_reference_unchanged"},
        "derivative": {"path": output.name, "sha256": _sha256_bytes(encoded_bytes), "status": "synthetic_degraded_derivative"},
        "parameters": parameters,
        "condition_is_observed_weather": False,
        "accuracy_claim": False,
        "limitations": "Synthetic image corruption for controlled experiments only; it is not observed adverse-weather footage or evidence of OCR robustness.",
    }
    output_created = False
    try:
        _write_new(output, encoded_bytes)
        output_created = True
        _write_new(manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    except BaseException:
        if output_created:
            output.unlink(missing_ok=True)
        raise
    if _sha256_file(source) != source_hash:
        output.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise RuntimeError("source image changed during degradation generation")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="source image preserved as an unchanged raw reference")
    parser.add_argument("--condition", required=True, choices=CONDITIONS)
    parser.add_argument("--severity", type=float, default=0.5, help="controlled effect strength in (0, 1]")
    parser.add_argument("--seed", type=int, default=0, help="deterministic random seed")
    parser.add_argument("--output", type=Path, required=True, help="new PNG derivative path; never overwrites")
    args = parser.parse_args()
    try:
        print(run(args.image, args.output, args.condition, args.severity, args.seed))
    except (ValueError, FileExistsError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
