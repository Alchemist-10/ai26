"""Offline optical-flow alignment experiment for same-view image bursts.

This utility does not fuse OCR, infer identity, or estimate calibrated confidence.
"""
from __future__ import annotations

import cv2
import numpy as np


def _validate(image: np.ndarray, name: str) -> np.ndarray:
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"{name} must be a uint8 BGR image with three channels")
    if image.shape[0] < 16 or image.shape[1] < 16:
        raise ValueError(f"{name} must be at least 16 by 16 pixels")
    if image.shape[0] * image.shape[1] > 3_145_728:
        raise ValueError(f"{name} exceeds the 3,145,728-pixel offline processing bound")
    return image


def align_to_reference(
    reference: np.ndarray,
    frame: np.ndarray,
    *,
    consistency_threshold_px: float = 1.5,
    levels: int = 4,
    window_size: int = 21,
    iterations: int = 3,
) -> tuple[np.ndarray, dict]:
    """Warp ``frame`` into ``reference`` coordinates using dense Farneback flow.

    The returned diagnostics are geometric consistency measurements, not a
    probability that pixels or plates are correctly aligned. Inputs must be
    same-sized frames from one fixed camera; this is an offline research helper.
    """
    reference = _validate(reference, "reference")
    frame = _validate(frame, "frame")
    if frame.shape != reference.shape:
        raise ValueError("reference and frame must have identical dimensions")
    if (not isinstance(consistency_threshold_px, (int, float)) or isinstance(consistency_threshold_px, bool)
            or not np.isfinite(consistency_threshold_px) or consistency_threshold_px <= 0):
        raise ValueError("consistency_threshold_px must be finite and positive")
    if type(levels) is not int or not 1 <= levels <= 8:
        raise ValueError("levels must be an integer from 1 to 8")
    if type(window_size) is not int or not 5 <= window_size <= 101 or window_size % 2 == 0:
        raise ValueError("window_size must be an odd integer from 5 to 101")
    if type(iterations) is not int or not 1 <= iterations <= 20:
        raise ValueError("iterations must be an integer from 1 to 20")

    ref_gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    forward = cv2.calcOpticalFlowFarneback(
        ref_gray, frame_gray, None, 0.5, levels, window_size, iterations, 5, 1.2, 0
    )
    backward = cv2.calcOpticalFlowFarneback(
        frame_gray, ref_gray, None, 0.5, levels, window_size, iterations, 5, 1.2, 0
    )

    height, width = ref_gray.shape
    grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    map_x = grid_x + forward[..., 0]
    map_y = grid_y + forward[..., 1]
    aligned = cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
    reverse_at_source = cv2.remap(backward, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    error = np.linalg.norm(forward + reverse_at_source, axis=2)
    in_bounds = (map_x >= 0) & (map_x <= width - 1) & (map_y >= 0) & (map_y <= height - 1)
    consistent = in_bounds & np.isfinite(error) & (error <= consistency_threshold_px)
    magnitude = np.linalg.norm(forward, axis=2)
    diagnostics = {
        "method": "farneback_dense_optical_flow",
        "status": "research_alignment",
        "reference_shape": [height, width],
        "mean_flow_px": round(float(np.mean(magnitude)), 4),
        "p95_flow_px": round(float(np.percentile(magnitude, 95)), 4),
        "forward_backward_consistent_fraction": round(float(np.mean(consistent)), 6),
        "consistency_threshold_px": float(consistency_threshold_px),
        "confidence_is_calibrated": False,
        "identity_inferred": False,
    }
    return aligned, diagnostics


def align_burst(frames: list[np.ndarray], *, reference_index: int = 0, **kwargs) -> tuple[list[np.ndarray], list[dict]]:
    """Align a bounded in-memory burst to one reference; does not blend frames."""
    if not isinstance(frames, list) or not 2 <= len(frames) <= 32:
        raise ValueError("frames must be a list containing 2 to 32 images")
    if type(reference_index) is not int or not 0 <= reference_index < len(frames):
        raise ValueError("reference_index is out of range")
    reference = _validate(frames[reference_index], "reference")
    aligned, diagnostics = [], []
    for index, frame in enumerate(frames):
        if index == reference_index:
            aligned.append(reference.copy())
            diagnostics.append({"method": "reference", "status": "unchanged_reference",
                                "confidence_is_calibrated": False, "identity_inferred": False})
            continue
        image, detail = align_to_reference(reference, frame, **kwargs)
        aligned.append(image)
        diagnostics.append(detail)
    return aligned, diagnostics
