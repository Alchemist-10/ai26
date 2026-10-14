"""Startup-pinned vehicle model assignment for stable and camera-scoped canary runs."""
from __future__ import annotations

import os
from pathlib import Path
import re

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_CHECKPOINT = Path(__file__).parent / "yolov8n.pt"


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
                         "loaded": stable.get("loaded", False)},
              "rollback": "remove the canary environment settings and restart the API"}
    if canary:
        result["canary"] = {"checkpoint": canary["path"].name,
                            "expected_sha256": canary["expected_sha256"],
                            "sha256": canary.get("loaded_sha256"),
                            "loaded": canary.get("loaded", False),
                            "camera_ids": list(canary["camera_ids"])}
    return result


def profile_for_camera(configuration: dict, camera_id: str) -> str:
    canary = configuration["canary"]
    return "canary" if canary and camera_id in canary["camera_ids"] else "stable"


CONFIGURATION = load_configuration()
