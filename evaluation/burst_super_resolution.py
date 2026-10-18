"""Offline translation-only multi-frame shift-and-add reconstruction.

Outputs are reconstructed research derivatives, never raw evidence. The method
does not model motion parallax, rolling shutter, occlusion, or plate OCR quality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import cv2
import numpy as np

MAX_FRAMES = 8
MAX_INPUT_PIXELS = 786_432
MAX_SHIFT_PIXELS = 8.0
SCALE = 2


def _validate(image: np.ndarray, name: str) -> np.ndarray:
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"{name} must be a uint8 BGR image with three channels")
    if min(image.shape[:2]) < 32 or image.shape[0] * image.shape[1] > MAX_INPUT_PIXELS:
        raise ValueError(f"{name} must be at least 32 by 32 and at most {MAX_INPUT_PIXELS} pixels")
    return image


def reconstruct_burst(frames: list[np.ndarray], *, min_response: float = 0.05) -> tuple[np.ndarray, dict]:
    """Fuse a short fixed-camera burst using phase-correlation shifts and 2x splatting."""
    if not isinstance(frames, list) or not 2 <= len(frames) <= MAX_FRAMES:
        raise ValueError(f"frames must contain 2 to {MAX_FRAMES} images")
    if (not isinstance(min_response, (int, float)) or isinstance(min_response, bool)
            or not np.isfinite(min_response) or not 0 < min_response <= 1):
        raise ValueError("min_response must be in (0, 1]")
    reference = _validate(frames[0], "reference")
    for index, frame in enumerate(frames[1:], 1):
        _validate(frame, f"frame {index}")
        if frame.shape != reference.shape:
            raise ValueError("all burst frames must have identical dimensions")

    gray_ref = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = reference.shape[:2]
    shifts = [(0.0, 0.0)]
    responses = [1.0]
    for index, frame in enumerate(frames[1:], 1):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        (dx, dy), response = cv2.phaseCorrelate(gray_ref, gray)
        if not np.isfinite([dx, dy, response]).all() or response < min_response:
            raise ValueError(f"frame {index} could not be registered with sufficient response")
        if abs(dx) > MAX_SHIFT_PIXELS or abs(dy) > MAX_SHIFT_PIXELS:
            raise ValueError(f"frame {index} shift exceeds the {MAX_SHIFT_PIXELS:g}-pixel bound")
        shifts.append((float(dx), float(dy)))
        responses.append(float(response))

    # Distinct subpixel phases are required; otherwise this only enlarges pixels.
    phases = [(dx % 1.0, dy % 1.0) for dx, dy in shifts]
    phase_spread = max((max(min(abs(a[axis]-b[axis]), 1-abs(a[axis]-b[axis]))
                             for axis in (0, 1)) for a in phases for b in phases), default=0)
    if phase_spread < 0.15:
        raise ValueError("burst has insufficient subpixel shift diversity for multi-frame reconstruction")

    out_h, out_w = h * SCALE, w * SCALE
    accumulation = np.zeros((out_h, out_w, 3), dtype=np.float32)
    weights = np.zeros((out_h, out_w, 1), dtype=np.float32)
    for frame, (dx, dy) in zip(frames, shifts):
        # phaseCorrelate reports frame displacement relative to reference. Move
        # each frame back by that offset while preserving its fractional phase.
        transform = np.float32([[SCALE, 0, -dx * SCALE], [0, SCALE, -dy * SCALE]])
        warped = cv2.warpAffine(frame, transform, (out_w, out_h), flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        coverage = cv2.warpAffine(np.ones((h, w), np.float32), transform, (out_w, out_h),
                                  flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        accumulation += warped.astype(np.float32) * coverage[:, :, None]
        weights += coverage[:, :, None]
    result = np.clip(accumulation / np.maximum(weights, 1e-6), 0, 255).astype(np.uint8)
    diagnostics = {
        "schema_version": 1,
        "status": "reconstructed",
        "method": "translation_phase_correlation_2x_shift_and_add",
        "input_frame_count": len(frames),
        "input_shape": [h, w],
        "output_shape": [out_h, out_w],
        "scale": SCALE,
        "frame_shifts_px": [[round(x, 4), round(y, 4)] for x, y in shifts],
        "registration_responses": [round(value, 6) for value in responses],
        "subpixel_phase_spread": round(float(phase_spread), 6),
        "confidence_is_calibrated": False,
        "identity_inferred": False,
        "raw_evidence": False,
        "limitations": ["translation-only alignment", "no occlusion or parallax model", "no OCR benefit established"],
    }
    return result, diagnostics


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _publish_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def run(input_paths: list[Path], output_path: Path, manifest_path: Path | None = None) -> Path:
    if not 2 <= len(input_paths) <= MAX_FRAMES:
        raise ValueError(f"choose 2 to {MAX_FRAMES} input images")
    sources = [path.resolve(strict=True) for path in input_paths]
    output_path = output_path.resolve()
    manifest_path = (manifest_path or output_path.with_suffix(".manifest.json")).resolve()
    if output_path.suffix.lower() != ".png" or manifest_path.suffix.lower() != ".json":
        raise ValueError("output must use .png and manifest must use .json")
    if len(set(sources)) != len(sources) or any(path == output_path or path == manifest_path for path in sources):
        raise ValueError("inputs must be distinct and outputs must not replace source frames")
    if output_path == manifest_path or output_path in sources or manifest_path in sources:
        raise ValueError("output and manifest paths must be separate")
    if output_path.exists() or manifest_path.exists():
        raise FileExistsError("an output already exists; choose new output paths")
    input_hashes = [_sha256(path) for path in sources]
    frames = []
    for path in sources:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("one or more burst images could not be decoded")
        frames.append(image)
    image, details = reconstruct_burst(frames)
    if [_sha256(path) for path in sources] != input_hashes:
        raise RuntimeError("a source frame changed during reconstruction; no output was published")
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("reconstructed image could not be encoded")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _publish_new(output_path, encoded.tobytes())
    details.update({
        "inputs": [{"filename": path.name, "sha256": digest} for path, digest in zip(sources, input_hashes)],
        "output": {"filename": output_path.name, "sha256": hashlib.sha256(encoded).hexdigest()},
    })
    try:
        _publish_new(manifest_path, (json.dumps(details, indent=2, sort_keys=True) + "\n").encode())
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True, help="burst image; repeat 2–8 times in capture order")
    parser.add_argument("--output", type=Path, required=True, help="new reconstructed PNG path")
    parser.add_argument("--manifest", type=Path, help="new provenance JSON path (defaults beside output)")
    args = parser.parse_args()
    print(run(args.input, args.output, args.manifest))


if __name__ == "__main__":
    main()
