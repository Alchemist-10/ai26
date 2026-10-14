"""Offline classical image enhancement experiments; outputs are research derivatives."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

import cv2
import numpy as np


METHODS = ("clahe", "gamma", "gray_world", "retinex", "dark_channel", "unsharp")
METHOD_PARAMETERS = {
    "clahe": {"clip_limit": 2.0, "tile_size": 8, "channel": "Lab L"},
    "gamma": {"gamma": 1.2},
    "gray_world": {"method": "gray-world channel mean balance"},
    "retinex": {"sigma": 30.0, "range_percentiles": [1, 99]},
    "dark_channel": {"radius": 7, "omega": 0.85, "minimum_transmission": 0.15},
    "unsharp": {"amount": 0.5, "sigma": 1.0},
}


def _image(image: np.ndarray) -> np.ndarray:
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must be a uint8 BGR image with three channels")
    return image


def clahe(image: np.ndarray, clip_limit: float = 2.0, tile_size: int = 8) -> np.ndarray:
    """Apply CLAHE to Lab luminance, preserving chroma."""
    _image(image)
    if not 0.1 <= clip_limit <= 8 or not 2 <= tile_size <= 32:
        raise ValueError("clip_limit must be 0.1..8 and tile_size 2..32")
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    light, a, b = cv2.split(lab)
    light = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_size, tile_size)).apply(light)
    return cv2.cvtColor(cv2.merge((light, a, b)), cv2.COLOR_LAB2BGR)


def gamma_correct(image: np.ndarray, gamma: float = 1.2) -> np.ndarray:
    _image(image)
    if not 0.2 <= gamma <= 3:
        raise ValueError("gamma must be 0.2..3")
    table = np.clip(np.power(np.arange(256, dtype=np.float32) / 255.0, 1.0 / gamma) * 255, 0, 255).astype(np.uint8)
    return cv2.LUT(image, table)


def gray_world(image: np.ndarray) -> np.ndarray:
    _image(image)
    means = image.astype(np.float32).mean(axis=(0, 1))
    target = float(means.mean())
    gains = target / np.maximum(means, 1.0)
    return np.clip(image.astype(np.float32) * gains.reshape(1, 1, 3), 0, 255).astype(np.uint8)


def retinex(image: np.ndarray, sigma: float = 30.0) -> np.ndarray:
    """Single-scale Retinex with per-channel robust range normalization."""
    _image(image)
    if not 2 <= sigma <= 150:
        raise ValueError("sigma must be 2..150")
    source = image.astype(np.float32) + 1.0
    illumination = cv2.GaussianBlur(source, (0, 0), sigmaX=sigma, sigmaY=sigma) + 1.0
    response = np.log(source) - np.log(illumination)
    out = np.empty_like(image)
    for channel in range(3):
        plane = response[:, :, channel]
        low, high = np.percentile(plane, (1, 99))
        if high <= low:
            out[:, :, channel] = image[:, :, channel]
        else:
            out[:, :, channel] = np.clip((plane - low) * (255.0 / (high - low)), 0, 255).astype(np.uint8)
    return out


def dark_channel(image: np.ndarray, radius: int = 7, omega: float = 0.85) -> np.ndarray:
    """Basic dark-channel dehazing estimate; intended only for offline experiments."""
    _image(image)
    if not 1 <= radius <= 31 or not 0.5 <= omega <= 0.98:
        raise ValueError("radius must be 1..31 and omega 0.5..0.98")
    size = 2 * radius + 1
    normalized = image.astype(np.float32) / 255.0
    dark = cv2.erode(np.min(normalized, axis=2), np.ones((size, size), np.uint8))
    count = max(1, dark.size // 1000)
    candidates = np.argpartition(dark.ravel(), -count)[-count:]
    atmospheric = normalized.reshape(-1, 3)[candidates].mean(axis=0)
    atmospheric = np.maximum(atmospheric, 0.05)
    normalized_dark = np.min(normalized / atmospheric.reshape(1, 1, 3), axis=2)
    transmission = np.clip(1 - omega * cv2.erode(normalized_dark, np.ones((size, size), np.uint8)), 0.15, 1.0)
    recovered = (normalized - atmospheric.reshape(1, 1, 3)) / transmission[:, :, None] + atmospheric.reshape(1, 1, 3)
    return np.clip(recovered * 255, 0, 255).astype(np.uint8)


def unsharp(image: np.ndarray, amount: float = 0.5, sigma: float = 1.0) -> np.ndarray:
    _image(image)
    if not 0 <= amount <= 1 or not 0.3 <= sigma <= 5:
        raise ValueError("amount must be 0..1 and sigma 0.3..5")
    blur = cv2.GaussianBlur(image, (0, 0), sigmaX=sigma, sigmaY=sigma)
    return cv2.addWeighted(image, 1 + amount, blur, -amount, 0)


TRANSFORMS: dict[str, Callable[[np.ndarray], np.ndarray]] = {
    "clahe": clahe,
    "gamma": gamma_correct,
    "gray_world": gray_world,
    "retinex": retinex,
    "dark_channel": dark_channel,
    "unsharp": unsharp,
}


def _sha256(path: Path) -> str:
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
        os.link(temp_name, path)  # atomic no-clobber publish
    finally:
        Path(temp_name).unlink(missing_ok=True)


def run(input_path: Path, output_dir: Path, methods: list[str]) -> Path:
    source = input_path.resolve(strict=True)
    destination = output_dir.resolve()
    if destination == source.parent or source.is_relative_to(destination):
        raise ValueError("output directory must be separate from the source image")
    if not methods or len(set(methods)) != len(methods) or any(m not in TRANSFORMS for m in methods):
        raise ValueError(f"choose unique methods from: {', '.join(METHODS)}")
    planned = [destination / f"{source.stem}.{method}.png" for method in methods]
    manifest_path = destination / f"{source.stem}.enhancement-manifest.json"
    if any(path.exists() for path in [*planned, manifest_path]):
        raise FileExistsError("one or more output files already exist; choose a new output directory")
    original_hash = _sha256(source)
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"cannot decode image: {source}")
    derivative_records = []
    for method in methods:
        output = TRANSFORMS[method](image)
        ok, encoded = cv2.imencode(".png", output)
        if not ok:
            raise RuntimeError(f"could not encode {method} derivative")
        path = destination / f"{source.stem}.{method}.png"
        _write_new(path, encoded.tobytes())
        derivative_records.append({"method": method, "parameters": METHOD_PARAMETERS[method], "path": path.name, "sha256": hashlib.sha256(encoded.tobytes()).hexdigest(), "status": "research_derivative"})
    manifest = {
        "schema_version": 1,
        "source": {"path": source.name, "sha256": original_hash, "status": "raw_reference_unchanged"},
        "derivatives": derivative_records,
        "quality_metrics": {"type": "descriptive_only_not_accuracy", "source": _metrics(image)},
        "accuracy_claim": False,
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    _write_new(manifest_path, payload)
    if _sha256(source) != original_hash:
        raise RuntimeError("source image changed during processing")
    return manifest_path


def _metrics(image: np.ndarray) -> dict[str, float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return {"mean_luminance": round(float(gray.mean()), 4), "luminance_stddev": round(float(gray.std()), 4), "laplacian_variance": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 4)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="input image; preserved as the raw reference")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--method", action="append", choices=METHODS, help="repeat to select multiple methods; default: all")
    args = parser.parse_args()
    try:
        print(run(args.image, args.output_dir, args.method or list(METHODS)))
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
