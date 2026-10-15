"""Generate controlled synthetic image degradations for offline research only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from collections.abc import Iterable, Iterator

import cv2
import numpy as np


CONDITIONS = ("rain", "fog", "low_light", "motion_blur", "sensor_noise")
MAX_VIDEO_FRAMES = 12_000
MAX_VIDEO_DIMENSION = 4096
MAX_DERIVATIVE_BYTES = 2 * 1024 * 1024 * 1024


def _image(image: np.ndarray) -> np.ndarray:
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must be a uint8 BGR image with three channels")
    if image.shape[0] < 2 or image.shape[1] < 2:
        raise ValueError("image must be at least 2 by 2 pixels")
    return image


def _validate_options(condition: str, severity: float, seed: int) -> float:
    if condition not in CONDITIONS:
        raise ValueError(f"condition must be one of: {', '.join(CONDITIONS)}")
    if not isinstance(severity, (int, float)) or isinstance(severity, bool) or not math.isfinite(severity) or not 0.0 < severity <= 1.0:
        raise ValueError("severity must be a finite number in (0, 1]")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("seed must be an integer from 0 to 4294967295")
    return float(severity)


def _rain_overlay(height: int, width: int, level: float, rng: np.random.Generator) -> tuple[np.ndarray, int, int, float]:
    overlay = np.zeros((height, width, 3), dtype=np.uint8)
    streak_count = max(1, int(height * width * level / 1800))
    streak_length = max(3, int(4 + 20 * level))
    for _ in range(streak_count):
        x = int(rng.integers(0, width))
        y = int(rng.integers(0, height))
        drift = int(rng.integers(-4, 5))
        end = (max(0, min(width - 1, x + drift)), min(height - 1, y + streak_length))
        cv2.line(overlay, (x, y), end, (225, 232, 238), 1, cv2.LINE_AA)
    alpha = 0.12 + 0.38 * level
    return overlay, streak_count, streak_length, alpha


def degrade(image: np.ndarray, condition: str, severity: float = 0.5, seed: int = 0) -> tuple[np.ndarray, dict]:
    """Return a deterministic uint8 BGR research derivative and exact parameters."""
    image = _image(image)
    level = _validate_options(condition, severity, seed)
    rng = np.random.default_rng(seed)
    height, width = image.shape[:2]

    if condition == "rain":
        overlay, streak_count, streak_length, alpha = _rain_overlay(height, width, level, rng)
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


def degrade_sequence(frames: Iterable[np.ndarray], condition: str, severity: float = 0.5,
                     seed: int = 0, *, max_frames: int = MAX_VIDEO_FRAMES) -> Iterator[tuple[np.ndarray, dict]]:
    """Yield deterministic, temporally coherent research frames with bounded memory."""
    level = _validate_options(condition, severity, seed)
    if type(max_frames) is not int or not 1 <= max_frames <= MAX_VIDEO_FRAMES:
        raise ValueError(f"max_frames must be an integer from 1 to {MAX_VIDEO_FRAMES}")

    def generate():
        shape = None
        overlay = None
        rain_count = rain_length = 0
        alpha = 0.0
        fixed_noise = None
        standard_deviation = 2.0 + 38.0 * level
        for index, frame in enumerate(frames):
            if index >= max_frames:
                raise ValueError(f"sequence exceeds the {max_frames}-frame bound")
            frame = _image(frame)
            if shape is None:
                shape = frame.shape
                if condition == "rain":
                    overlay, rain_count, rain_length, alpha = _rain_overlay(
                        frame.shape[0], frame.shape[1], level, np.random.default_rng(seed))
                elif condition == "sensor_noise":
                    fixed_noise = np.random.default_rng(seed).normal(
                        0, standard_deviation * 0.25, frame.shape).astype(np.float32)
            elif frame.shape != shape:
                raise ValueError("all frames in a sequence must have the same dimensions")

            if condition == "rain":
                speed = max(1, int(round(2 + 8 * level)))
                drift = int(seed % 5) - 2
                transform = np.float32([[1, 0, drift * index], [0, 1, speed * index]])
                moving_overlay = cv2.warpAffine(overlay, transform, (shape[1], shape[0]),
                                                flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_WRAP)
                result = cv2.addWeighted(frame, 1.0, moving_overlay, alpha, 0)
                parameters = {"rain_field": "seeded_periodic_translation", "fall_speed_px_per_frame": speed,
                              "wind_drift_px_per_frame": drift, "streak_count": rain_count,
                              "streak_length_px": rain_length, "overlay_opacity": round(alpha, 4)}
            elif condition == "sensor_noise":
                frame_rng = np.random.default_rng(np.random.SeedSequence([seed, index]))
                temporal = frame_rng.normal(0, standard_deviation * math.sqrt(1 - 0.25 ** 2),
                                            frame.shape).astype(np.float32)
                result = np.clip(frame.astype(np.float32) + fixed_noise + temporal, 0, 255).astype(np.uint8)
                parameters = {"fixed_pattern_noise_fraction": 0.25,
                              "gaussian_standard_deviation": round(standard_deviation, 4),
                              "temporal_seed": [seed, index]}
            else:
                result, parameters = degrade(frame, condition, level, seed)
            yield result, {"condition": condition, "severity": level, "seed": seed,
                           "frame_index": index, "temporal_mode": "sequence_consistent", **parameters}

    return generate()


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


def run_video(input_path: Path, output_path: Path, condition: str,
              severity: float = 0.5, seed: int = 0) -> Path:
    """Write a bounded MP4 research derivative; the source video is never modified."""
    level = _validate_options(condition, severity, seed)
    source = input_path.resolve(strict=True)
    output = output_path.resolve()
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    if output.suffix.lower() != ".mp4":
        raise ValueError("video output path must use the .mp4 extension")
    if output == source or manifest_path == source:
        raise ValueError("output and manifest must not overwrite the source video")
    if output.exists() or manifest_path.exists():
        raise FileExistsError("output video or manifest already exists; choose new output paths")
    if source.stat().st_size > MAX_DERIVATIVE_BYTES:
        raise ValueError("source video exceeds the 2 GiB research bound")

    source_hash = _sha256_file(source)
    capture = cv2.VideoCapture(str(source), cv2.CAP_FFMPEG)
    if not capture.isOpened():
        capture.release()
        raise ValueError(f"cannot open source video: {source}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    reported_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if (not math.isfinite(fps) or not 1 <= fps <= 120 or not math.isfinite(reported_count)
            or not 1 <= reported_count <= MAX_VIDEO_FRAMES or not 2 <= width <= MAX_VIDEO_DIMENSION
            or not 2 <= height <= MAX_VIDEO_DIMENSION):
        capture.release()
        raise ValueError("source video metadata is invalid or exceeds the frame, FPS or dimension bound")

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.stem}.", suffix=".tmp.mp4", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    writer = None
    source_count = 0
    derivative_count = 0
    output_created = False
    try:
        writer = cv2.VideoWriter(str(temporary), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError("MP4 video writer is unavailable on this host")

        def decoded_frames():
            nonlocal source_count
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame.shape[:2] != (height, width):
                    raise ValueError("source video changed frame dimensions during decode")
                source_count += 1
                yield frame

        for frame, _metadata in degrade_sequence(decoded_frames(), condition, level, seed):
            writer.write(frame)
            derivative_count += 1
            if derivative_count % 128 == 0 and temporary.stat().st_size > MAX_DERIVATIVE_BYTES:
                raise ValueError("synthetic video exceeds the 2 GiB output bound")
        if not derivative_count or source_count != int(round(reported_count)):
            raise RuntimeError(f"decoded {source_count} frames but source metadata reported {reported_count:g}")
    except BaseException:
        if writer is not None:
            writer.release()
            writer = None
        capture.release()
        temporary.unlink(missing_ok=True)
        raise
    finally:
        if writer is not None:
            writer.release()
        capture.release()

    try:
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        derivative_size = temporary.stat().st_size
        if not derivative_size or derivative_size > MAX_DERIVATIVE_BYTES:
            raise ValueError("synthetic video is empty or exceeds the 2 GiB output bound")
        derivative_hash = _sha256_file(temporary)
        manifest = {
            "schema_version": 1,
            "type": "synthetic_degraded_video_manifest",
            "source": {"path": source.name, "sha256": source_hash, "status": "raw_reference_unchanged"},
            "derivative": {"path": output.name, "sha256": derivative_hash, "size_bytes": derivative_size,
                           "status": "synthetic_degraded_derivative"},
            "video": {"codec": "mp4v", "fps": fps, "width": width, "height": height,
                      "frame_count": derivative_count, "audio_preserved": False},
            "parameters": {"condition": condition, "severity": level, "seed": seed,
                           "temporal_mode": "sequence_consistent", "noise_and_rain_change_by_frame": condition in {"rain", "sensor_noise"}},
            "condition_is_observed_weather": False,
            "accuracy_claim": False,
            "limitations": "Synthetic video corruption for controlled experiments only; temporal effects are simplified and are not observed weather or evidence of OCR robustness.",
        }
        if _sha256_file(source) != source_hash:
            raise RuntimeError("source video changed during degradation generation")
        os.link(temporary, output)
        output_created = True
        _write_new(manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
        if _sha256_file(source) != source_hash:
            raise RuntimeError("source video changed during degradation generation")
    except BaseException:
        if output_created:
            output.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="source image preserved as an unchanged raw reference")
    parser.add_argument("--condition", required=True, choices=CONDITIONS)
    parser.add_argument("--severity", type=float, default=0.5, help="controlled effect strength in (0, 1]")
    parser.add_argument("--seed", type=int, default=0, help="deterministic random seed")
    parser.add_argument("--video", action="store_true", help="process a video sequence and write an MP4; audio is dropped")
    parser.add_argument("--output", type=Path, required=True, help="new PNG or MP4 derivative path; never overwrites")
    args = parser.parse_args()
    try:
        runner = run_video if args.video else run
        print(runner(args.image, args.output, args.condition, args.severity, args.seed))
    except (ValueError, FileExistsError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
