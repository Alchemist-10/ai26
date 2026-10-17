import os

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from cameras import CAMERAS, CAMERAS_BY_ID, camera_playback_source, camera_source
from events import derive_alerts, evidence_report, get_events, get_trajectory, stats
from nlquery import answer as nl_answer
from stream import mjpeg_generator, snapshot_frame

frontend_port = os.environ.get("AI26_FRONTEND_PORT", "5174")
app = FastAPI(title="AI26 demo backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{frontend_port}", f"http://127.0.0.1:{frontend_port}"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_active_stream_id = 0


@app.get("/api/cameras")
def list_cameras():
    return [{k: v for k, v in c.items() if k != "path"} for c in CAMERAS]


@app.get("/api/stream/{camera_id}")
async def stream(request: Request, camera_id: str, start: float | None = None, anchor: float | None = None):
    """Continuous full-inference feed — only ever requested for the one focused/main camera."""
    global _active_stream_id
    _active_stream_id += 1
    my_stream_id = _active_stream_id

    if camera_id not in CAMERAS_BY_ID:
        return {"error": "unknown camera"}
    if not camera_source(camera_id).is_file():
        return Response(status_code=404)
    return StreamingResponse(
        mjpeg_generator(
            camera_id,
            start,
            anchor,
            request=request,
            stream_id=my_stream_id,
            get_active_stream_id=lambda: _active_stream_id,
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/video/{camera_id}")
def video(camera_id: str):
    """Serve source footage to camera-wall tiles without consuming inference capacity."""
    if camera_id not in CAMERAS_BY_ID:
        return {"error": "unknown camera"}
    path = camera_playback_source(camera_id)
    if not path.exists():
        return Response(status_code=404)
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/snapshot/{camera_id}")
def snapshot(camera_id: str):
    """One-shot annotated frame for still-image API consumers."""
    if camera_id not in CAMERAS_BY_ID:
        return {"error": "unknown camera"}
    jpeg = snapshot_frame(camera_id)
    if not jpeg:
        return Response(status_code=204)
    return Response(content=jpeg, media_type="image/jpeg")


@app.get("/api/events")
def events(camera: str | None = None, plate: str | None = None):
    return get_events(camera_id=camera, plate=plate)


@app.get("/api/alerts")
def alerts():
    return derive_alerts()


@app.get("/api/stats")
def get_stats():
    return stats()


@app.post("/api/nlquery")
def nlquery(body: dict):
    return nl_answer(body.get("question", ""))


@app.get("/api/trajectory/{plate}")
def trajectory(plate: str):
    return get_trajectory(plate)


@app.post("/api/evidence/{plate}")
def evidence(plate: str):
    return evidence_report(plate)
