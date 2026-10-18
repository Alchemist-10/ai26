"""Opt-in pseudonyms and presentation-only person masking for sampled views."""
import copy
import hashlib
import hmac
import os
import re
import stat
import threading
from pathlib import Path

import cv2

from plate_format import normalize_plate

_lock = threading.Lock()
_cached_path = None
_cached_key = None
_PLATE_TEXT = re.compile(r"(?<![A-Z0-9])[A-Z]{2}\s*\d{1,2}\s*[A-Z]{0,3}\s*\d{1,4}(?![A-Z0-9])", re.IGNORECASE)
_PLATE_FIELDS = {"plate", "plate_norm", "plate_raw"}


def enabled():
    return os.environ.get("AI26_PRIVACY_ENABLED", "0") == "1"


def _key():
    global _cached_path, _cached_key
    path_value = os.environ.get("AI26_PRIVACY_KEY_FILE")
    if not path_value:
        raise RuntimeError("Privacy mode requires AI26_PRIVACY_KEY_FILE")
    path = Path(path_value)
    normalized_path = str(path.resolve())
    with _lock:
        if _cached_path == normalized_path and _cached_key is not None:
            return _cached_key
        try:
            info = path.stat()
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise RuntimeError("Privacy key file must not be accessible to group or other users")
            key = path.read_bytes()
        except OSError as exc:
            raise RuntimeError("Privacy key file is unavailable") from exc
        if len(key) < 32:
            raise RuntimeError("Privacy key must contain at least 32 random bytes")
        _cached_path, _cached_key = normalized_path, key
        return key


def validate_configuration():
    if enabled():
        _key()


def plate_alias(value):
    if not enabled() or not isinstance(value, str):
        return value
    normalized = normalize_plate(value)
    if not normalized.get("format_valid"):
        return value
    canonical = str(normalized["plate_norm"])
    digest = hmac.new(_key(), canonical.encode("ascii"), hashlib.sha256).hexdigest()[:24]
    return f"PLATE-{digest}"


def redact_analytics_payload(payload):
    """Copy a JSON-like analytics result and replace plate identifiers in it."""
    if not enabled():
        return payload

    def redact_text(value):
        def replace(match):
            return plate_alias(match.group(0))
        return _PLATE_TEXT.sub(replace, value)

    def walk(value, field=None):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key in _PLATE_FIELDS and isinstance(item, str):
                    result[key] = plate_alias(item)
                else:
                    result[key] = walk(item, key)
            return result
        if isinstance(value, list):
            return [walk(item, field) for item in value]
        if isinstance(value, tuple):
            return tuple(walk(item, field) for item in value)
        if isinstance(value, str):
            return redact_text(value)
        return copy.deepcopy(value)

    return walk(payload)


def pixelate_person_boxes(frame, boxes, padding=0.12):
    """Pixelate person bounding regions in a presentation frame, never in evidence."""
    if frame is None or getattr(frame, "ndim", 0) < 2:
        return frame
    height, width = frame.shape[:2]
    for box in boxes:
        if not isinstance(box, (tuple, list)) or len(box) != 4:
            continue
        try:
            x1, y1, x2, y2 = (int(round(float(value))) for value in box)
        except (TypeError, ValueError, OverflowError):
            continue
        box_width, box_height = x2 - x1, y2 - y1
        if box_width < 2 or box_height < 2:
            continue
        pad_x, pad_y = round(box_width * padding), round(box_height * padding)
        x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
        x2, y2 = min(width, x2 + pad_x), min(height, y2 + pad_y)
        if x2 - x1 < 2 or y2 - y1 < 2:
            continue
        region = frame[y1:y2, x1:x2]
        # Reduce each detected person to a tiny mosaic before nearest-neighbor
        # expansion. This hides more detail than a mild Gaussian blur.
        mosaic_size = (max(1, (x2 - x1) // 20), max(1, (y2 - y1) // 20))
        mosaic = cv2.resize(region, mosaic_size, interpolation=cv2.INTER_AREA)
        frame[y1:y2, x1:x2] = cv2.resize(mosaic, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)
    return frame


def status():
    active = enabled()
    if active:
        validate_configuration()
    return {
        "enabled": active,
        "plate_identifiers": "keyed_pseudonyms" if active else "raw",
        "sampled_person_mask": "person_box_pixelation" if active else "disabled",
        "scope": "sampled analytics views only; evidence records retain original values and pixels",
    }
