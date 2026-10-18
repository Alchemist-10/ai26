"""Startup-pinned vehicle model assignment for stable and camera-scoped canary runs."""
from __future__ import annotations

import math
import os
from pathlib import Path
import re

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_CHECKPOINT = Path(__file__).parent / "yolov8n.pt"
REQUIRED_VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
PERSON_CLASS = {0: "person"}


class DetectorCompatibilityError(RuntimeError):
    """A checkpoint cannot satisfy AI26's pinned detector output contract."""


def preflight_detector(model, *, device: str, include_person: bool = False) -> dict:
    """Fail closed unless a loaded checkpoint has the expected detect outputs and class IDs."""
    if getattr(model, "task", None) != "detect":
        raise DetectorCompatibilityError("Vehicle checkpoint must be an object-detection model")
    raw_names = getattr(model, "names", None)
    if isinstance(raw_names, dict):
        names = {}
        for index, name in raw_names.items():
            if isinstance(index, bool):
                raise DetectorCompatibilityError("Vehicle checkpoint has a duplicate or invalid class index")
            try:
                normalized_index = int(index)
            except (TypeError, ValueError) as error:
                raise DetectorCompatibilityError("Vehicle checkpoint has an invalid class map") from error
            if isinstance(index, float) and not index.is_integer():
                raise DetectorCompatibilityError("Vehicle checkpoint has an invalid class map")
            if isinstance(index, str) and str(normalized_index) != index.strip():
                raise DetectorCompatibilityError("Vehicle checkpoint has an invalid class map")
            if normalized_index in names:
                raise DetectorCompatibilityError("Vehicle checkpoint has a duplicate or invalid class index")
            names[normalized_index] = name
    elif isinstance(raw_names, (list, tuple)):
        names = dict(enumerate(raw_names))
    else:
        raise DetectorCompatibilityError("Vehicle checkpoint does not expose a class map")
    required = {**REQUIRED_VEHICLE_CLASSES, **(PERSON_CLASS if include_person else {})}
    for index, expected in required.items():
        actual = names.get(index)
        if not isinstance(actual, str) or actual.strip().casefold() != expected:
            raise DetectorCompatibilityError(f"Vehicle checkpoint class {index} must be named {expected!r}")
    predictor = getattr(model, "predict", None)
    if not callable(predictor):
        raise DetectorCompatibilityError("Vehicle checkpoint does not support prediction")

    # A synthetic forward pass checks the runtime output contract without introducing
    # a detection, observation, label, or accuracy claim into the application.
    import numpy as np
    try:
        outputs = predictor(np.zeros((640, 640, 3), dtype=np.uint8), device=device,
                            verbose=False, classes=sorted(required), conf=0.4)
    except Exception as error:
        raise DetectorCompatibilityError("Vehicle checkpoint failed its 640x640 detection preflight") from error
    if not isinstance(outputs, (list, tuple)) or len(outputs) != 1:
        raise DetectorCompatibilityError("Vehicle checkpoint preflight returned an unexpected result count")
    boxes = getattr(outputs[0], "boxes", None)
    classes = getattr(boxes, "cls", None)
    if classes is None:
        raise DetectorCompatibilityError("Vehicle checkpoint preflight did not return detection boxes")
    try:
        predicted = classes.tolist() if hasattr(classes, "tolist") else list(classes)
        numeric_ids = [float(value) for value in predicted]
        if any(not math.isfinite(value) or not value.is_integer() for value in numeric_ids):
            raise ValueError("non-integral class id")
        predicted_ids = {int(value) for value in numeric_ids}
    except (TypeError, ValueError, OverflowError) as error:
        raise DetectorCompatibilityError("Vehicle checkpoint preflight returned an invalid class tensor") from error
    if not predicted_ids.issubset(required):
        raise DetectorCompatibilityError("Vehicle checkpoint preflight returned an unsupported class ID")
    return {"task": "detect", "class_map_status": "compatible",
            "preflight_status": "passed", "preflight_input": "synthetic_640x640_bgr",
            "required_class_ids": sorted(required)}


def _expected_digest(value: str | None, variable: str) -> str | None:
    if value is None or value == "":
        return None
    if not SHA256_RE.fullmatch(value):
        raise RuntimeError(f"{variable} must be a lowercase SHA-256 digest")
    return value


def _checkpoint_path(value: str | None, variable: str, default: Path | None = None) -> Path:
    if value is None:
        if default is None:
            raise RuntimeError(f"{variable} is required")
        path = default
    else:
        path = Path(value)
        if not path.is_absolute():
            raise RuntimeError(f"{variable} must be an absolute path")
    try:
        path = path.resolve(strict=True)
    except OSError as error:
        raise RuntimeError(f"{variable} does not resolve to a readable model file") from error
    if not path.is_file() or not os.access(path, os.R_OK):
        raise RuntimeError(f"{variable} must point to a readable model file")
    return path


def load_configuration(environment: dict[str, str] | None = None,
                       camera_ids: set[str] | None = None) -> dict:
    """Validate paths and pin assignments once, before the processor starts."""
    env = os.environ if environment is None else environment
    if camera_ids is None:
        from cameras import CAMERAS_BY_ID
        camera_ids = set(CAMERAS_BY_ID)
    stable_path_value = env.get("AI26_VEHICLE_MODEL_PATH") or None
    stable_digest = _expected_digest(env.get("AI26_VEHICLE_MODEL_SHA256"), "AI26_VEHICLE_MODEL_SHA256")
    if stable_path_value and not stable_digest:
        raise RuntimeError("AI26_VEHICLE_MODEL_SHA256 is required with AI26_VEHICLE_MODEL_PATH")
    stable_path = _checkpoint_path(stable_path_value, "AI26_VEHICLE_MODEL_PATH", DEFAULT_CHECKPOINT)

    canary_path_value = env.get("AI26_VEHICLE_CANARY_MODEL_PATH") or None
    canary_digest_value = env.get("AI26_VEHICLE_CANARY_MODEL_SHA256") or None
    canary_camera_value = env.get("AI26_VEHICLE_CANARY_CAMERAS") or None
    canary_fields = (canary_path_value, canary_digest_value, canary_camera_value)
    if any(value is not None for value in canary_fields) and not all(value for value in canary_fields):
        raise RuntimeError("canary model path, SHA-256 and camera allowlist must be configured together")

    canary = None
    if canary_path_value:
        canary_digest = _expected_digest(canary_digest_value, "AI26_VEHICLE_CANARY_MODEL_SHA256")
        canary_path = _checkpoint_path(canary_path_value, "AI26_VEHICLE_CANARY_MODEL_PATH")
        cameras = [item.strip() for item in canary_camera_value.split(",") if item.strip()]
        if not cameras or len(set(cameras)) != len(cameras):
            raise RuntimeError("AI26_VEHICLE_CANARY_CAMERAS must list unique camera IDs")
        if camera_ids is not None and any(camera not in camera_ids for camera in cameras):
            raise RuntimeError("AI26_VEHICLE_CANARY_CAMERAS contains an unknown camera ID")
        canary = {"path": canary_path, "expected_sha256": canary_digest, "camera_ids": tuple(cameras)}

    return {"stable": {"path": stable_path, "expected_sha256": stable_digest},
            "canary": canary}


def status(configuration: dict) -> dict:
    """Return path-free operator status; hashes identify bytes, not model accuracy."""
    stable = configuration["stable"]
    canary = configuration["canary"]
    result = {"mode": "camera_allowlist_canary" if canary else "stable_only",
              "stable": {"checkpoint": stable["path"].name,
                         "expected_sha256": stable["expected_sha256"],
                         "sha256": stable.get("loaded_sha256"),
                         "loaded": stable.get("loaded", False),
                         "compatibility": stable.get("compatibility")},
              "rollback": "remove the canary environment settings and restart the API"}
    if canary:
        result["canary"] = {"checkpoint": canary["path"].name,
                            "expected_sha256": canary["expected_sha256"],
                            "sha256": canary.get("loaded_sha256"),
                            "loaded": canary.get("loaded", False),
                            "compatibility": canary.get("compatibility"),
                            "camera_ids": list(canary["camera_ids"])}
    return result


def profile_for_camera(configuration: dict, camera_id: str) -> str:
    canary = configuration["canary"]
    return "canary" if canary and camera_id in canary["camera_ids"] else "stable"


CONFIGURATION = load_configuration()
