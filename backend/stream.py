"""Read-only consumers of shared inference frames. No capture/model/event side effects."""
import time
import asyncio
from fastapi import Request
from processing import processor


async def mjpeg_generator(camera_id, start_at=None, anchor_at=None, request: Request | None = None):
    previous=None
    # start/anchor remain accepted for old clients; shared processing cannot be seeked by a viewer.
    idle_deadline=time.monotonic()+30
    while not processor.stop_event.is_set():
        if request is not None and await request.is_disconnected():
            return
        latest=processor.jpeg(camera_id)
        if latest and latest[0]!=previous:
            previous,jpeg=latest
            idle_deadline=time.monotonic()+30
            yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+jpeg+b'\r\n'
        elif time.monotonic()>idle_deadline:
            return
        await asyncio.sleep(.1)


def snapshot_frame(camera_id):
    latest=processor.jpeg(camera_id)
    return latest[1] if latest else b''
