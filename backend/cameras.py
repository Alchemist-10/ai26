import os
from pathlib import Path

FOOTAGE_ROOT = Path(os.environ.get("AI26_FOOTAGE_ROOT", str(Path(__file__).parent / "data" / "footage")))
PLAYBACK_ROOT = Path(__file__).parent / "static" / "playback"

# Location comes only from what the footage itself proves: the plate-corridor clips have
# a real junction name burned into the on-screen overlay by the NVR/PTZ unit — that's a
# verified location. The grey-Tata clips only burn in a camera model string ("VIGI C330"),
# no place name, and ffprobe confirms no GPS/EXIF tags on any of these files — so those six
# are honestly unconfirmed, clustered near one real anchor point instead of invented names.
UNCONFIRMED_ANCHOR = (9.9736, 76.2870)  # Kochi city centroid, not a claimed exact site

CAMERAS = [
    {
        "id": "CAM-01",
        "kind": "vehicle",
        "location": "Unconfirmed",
        "location_confirmed": False,
        "lat": UNCONFIRMED_ANCHOR[0] + 0.006,
        "lon": UNCONFIRMED_ANCHOR[1] - 0.004,
        "path": str(FOOTAGE_ROOT / "grey-tata-videos" / "VIGI NVR1016H(UN)(000)_6C-A8_20260914174903-20260914174939_0_1789562584529.mp4"),
    },
    {
        "id": "CAM-02",
        "kind": "vehicle",
        "location": "Unconfirmed",
        "location_confirmed": False,
        "lat": UNCONFIRMED_ANCHOR[0] + 0.003,
        "lon": UNCONFIRMED_ANCHOR[1] + 0.005,
        "path": str(FOOTAGE_ROOT / "grey-tata-videos" / "VIGI NVR1016H(UN)(001)_6C-A8_20260914174918-20260914174954_0_1789562260286.mp4"),
    },
    {
        "id": "CAM-03",
        "kind": "vehicle",
        "location": "Unconfirmed",
        "location_confirmed": False,
        "lat": UNCONFIRMED_ANCHOR[0] - 0.002,
        "lon": UNCONFIRMED_ANCHOR[1] + 0.007,
        "path": str(FOOTAGE_ROOT / "grey-tata-videos" / "VIGI NVR1016H(UN)(002)_6C-A8_20260914174922-20260914174958_0_1789562583905.mp4"),
    },
    {
        "id": "CAM-04",
        "kind": "vehicle",
        "location": "Unconfirmed",
        "location_confirmed": False,
        "lat": UNCONFIRMED_ANCHOR[0] - 0.005,
        "lon": UNCONFIRMED_ANCHOR[1] - 0.002,
        "path": str(FOOTAGE_ROOT / "grey-tata-videos" / "VIGI NVR1016H(UN)(004)_6C-A8_20260914174904-20260914174940_0_1789562820911.mp4"),
    },
    {
        "id": "CAM-05",
        "kind": "vehicle",
        "location": "Unconfirmed",
        "location_confirmed": False,
        "lat": UNCONFIRMED_ANCHOR[0] + 0.007,
        "lon": UNCONFIRMED_ANCHOR[1] + 0.001,
        "path": str(FOOTAGE_ROOT / "grey-tata-videos" / "VIGI NVR1016H(UN)(005)_6C-A8_20260914174858-20260914174934_0_1789562992516.mp4"),
    },
    {
        "id": "CAM-06",
        "kind": "vehicle",
        "location": "Unconfirmed",
        "location_confirmed": False,
        "lat": UNCONFIRMED_ANCHOR[0] - 0.004,
        "lon": UNCONFIRMED_ANCHOR[1] - 0.006,
        "path": str(FOOTAGE_ROOT / "grey-tata-videos" / "VIGI NVR1016H(UN)(008)_6C-A8_20260914174845-20260914174957_0_1789573469522.mp4"),
    },
    # plate-recognition corridor — location read directly off the burned-in PTZ overlay text
    {
        "id": "CAM-07",
        "kind": "plate",
        "location": "Subhash Chandra Bose Jn",
        "location_confirmed": True,
        "lat": 9.9680,
        "lon": 76.2810,
        "path": str(FOOTAGE_ROOT / "numberplate-vids" / "clip 4.mp4"),
    },
    {
        "id": "CAM-08",
        "kind": "plate",
        "location": "Kathrikkadavu Junction",
        "location_confirmed": True,
        "lat": 9.9846,
        "lon": 76.2932,
        "path": str(FOOTAGE_ROOT / "numberplate-vids" / "clip_2_00_25-00_50.mp4"),
    },
    {
        "id": "CAM-09",
        "kind": "plate",
        "location": "Petta Junction",
        "location_confirmed": True,
        "lat": 9.9430,
        "lon": 76.3487,
        "path": str(FOOTAGE_ROOT / "numberplate-vids" / "clip_2_00_30-01_00.mp4"),
    },
]

CAMERAS_BY_ID = {c["id"]: c for c in CAMERAS}

# Bindings are immutable for this process. Import publication takes effect only
# on restart, so an open decoder and browser playback cannot switch independently.
from source_catalog import load_catalog
MANAGED_SOURCES = load_catalog(CAMERAS_BY_ID)


def camera_source(camera_id: str) -> Path:
    """Use original footage when available, otherwise a repo-local proxy."""
    camera = CAMERAS_BY_ID[camera_id]
    if camera_id in MANAGED_SOURCES:
        return MANAGED_SOURCES[camera_id]['original']
    source = Path(camera["path"])
    if source.exists():
        return source
    proxy = PLAYBACK_ROOT / f"{camera_id}.mp4"
    return proxy if proxy.exists() else source


def camera_playback_source(camera_id: str) -> Path:
    """Use the browser-safe proxy for playback, even when original footage exists."""
    camera = CAMERAS_BY_ID[camera_id]
    if camera_id in MANAGED_SOURCES:
        return MANAGED_SOURCES[camera_id]['playback']
    proxy = PLAYBACK_ROOT / f"{camera_id}.mp4"
    return proxy if proxy.exists() else Path(camera["path"])
