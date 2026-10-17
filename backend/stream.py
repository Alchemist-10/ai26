import time

import cv2

from cameras import CAMERAS_BY_ID, camera_source
from events import add_events

PLAYBACK_STAGGER_SECONDS = 4.5


def _camera_playback_offset(camera_id: str, duration: float) -> float:
    camera_number = int(camera_id.rsplit("-", 1)[-1])
    cycle = max(duration - 0.5, 0.5)
    return (time.time() + camera_number * PLAYBACK_STAGGER_SECONDS) % cycle


def _seek_to_live_phase(cap, camera_id: str, start_at: float | None = None, anchor_at: float | None = None):
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    if total > 0:
        duration = total / fps
        cycle = max(duration - 0.5, 0.5)
        offset = (start_at + time.time() - (anchor_at or time.time())) % cycle if start_at is not None else _camera_playback_offset(camera_id, duration)
        cap.set(cv2.CAP_PROP_POS_MSEC, offset * 1000)


def _annotate(frame, kind: str, camera_id: str):
    # Load models when inference is first requested, not for metadata/API startup.
    from inference import annotate_plate_frame, annotate_vehicle_frame

    if kind == "vehicle":
        return annotate_vehicle_frame(frame, camera_id)
    frame, plate_detections = annotate_plate_frame(frame, camera_id)
    frame, vehicle_detections = annotate_vehicle_frame(frame, camera_id)
    return frame, plate_detections + vehicle_detections


import asyncio
from typing import Callable
from fastapi import Request


async def mjpeg_generator(
    camera_id: str,
    start_at: float | None = None,
    anchor_at: float | None = None,
    request: Request | None = None,
    stream_id: int | None = None,
    get_active_stream_id: Callable[[], int] | None = None,
):
    """Continuous full-inference stream for the focused camera."""
    cam = CAMERAS_BY_ID[camera_id]
    cap = cv2.VideoCapture(str(camera_source(camera_id)))
    if start_at is None:
        start_at = _camera_playback_offset(camera_id, (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1) / (cap.get(cv2.CAP_PROP_FPS) or 25))
        anchor_at = time.time()
    _seek_to_live_phase(cap, camera_id, start_at, anchor_at)

    try:
        while True:
            if stream_id is not None and get_active_stream_id and get_active_stream_id() != stream_id:
                break
            if request is not None and await request.is_disconnected():
                break

            ok, frame = cap.read()
            if not ok:
                _seek_to_live_phase(cap, camera_id)
                continue

            frame, detections = _annotate(frame, cam["kind"], camera_id)
            add_events(detections)

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            )
            await asyncio.sleep(0.01)
    finally:
        cap.release()


SNAPSHOT_MAX_DIM = 480


def snapshot_frame(camera_id: str) -> bytes:
    """One annotated frame for API consumers that need a still image."""
    cam = CAMERAS_BY_ID[camera_id]
    cap = cv2.VideoCapture(str(camera_source(camera_id)))
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        frame_idx = int(time.time() * fps) % total
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            return b""
        h, w = frame.shape[:2]
        scale = SNAPSHOT_MAX_DIM / max(h, w)
        if scale < 1:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        frame, detections = _annotate(frame, cam["kind"], camera_id)
        add_events(detections)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 78])
        return buf.tobytes() if ok else b""
    finally:
        cap.release()
