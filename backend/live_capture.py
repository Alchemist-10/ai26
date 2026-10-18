"""Bounded RTSP capture readers. Credentials stay in a protected host-side file."""
import json
import logging
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import cv2

log = logging.getLogger(__name__)
MAX_CONFIG_BYTES = 64 * 1024
OPEN_TIMEOUT_MS = 5000
READ_TIMEOUT_MS = 3000
MAX_FRAME_AGE_SECONDS = 5


def load_live_sources(path=None, camera_ids=None):
    """Read camera_id -> RTSP URL config; never include URLs in errors or output."""
    path = path if path is not None else os.environ.get('AI26_LIVE_SOURCES_FILE', '').strip()
    if not path:
        return {}
    config_path = Path(path)
    try:
        info = config_path.stat()
        if not config_path.is_file() or info.st_size > MAX_CONFIG_BYTES:
            raise ValueError
        if os.name == 'posix' and info.st_mode & 0o077:
            raise ValueError
        data = json.loads(config_path.read_text(encoding='utf-8'))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError('Live source configuration is unavailable, invalid, or not private (require mode 0600).') from exc
    if not isinstance(data, dict) or not data or len(data) > 9:
        raise RuntimeError('Live source configuration must be a non-empty camera-to-URL object.')
    known = set(camera_ids or ())
    sources = {}
    for camera_id, url in data.items():
        if not isinstance(camera_id, str) or (known and camera_id not in known):
            raise RuntimeError('Live source configuration contains an unknown camera.')
        if not isinstance(url, str) or len(url) > 2048 or any(ord(char) < 32 for char in url):
            raise RuntimeError('Live source configuration contains an invalid URL.')
        try:
            parsed = urlsplit(url)
            if parsed.scheme.lower() not in ('rtsp', 'rtsps') or not parsed.hostname or parsed.fragment:
                raise ValueError
            parsed.port  # validate port syntax/range
        except ValueError as exc:
            raise RuntimeError('Live source configuration contains an invalid RTSP URL.') from exc
        sources[camera_id] = url
    return sources


class LiveCapture:
    """One daemon reader per camera, keeping only the freshest decoded frame."""
    def __init__(self, camera_id, url, capture_factory=None, clock=time.time):
        self.camera_id = camera_id
        self._url = url
        self._capture_factory = capture_factory or cv2.VideoCapture
        self._clock = clock
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest = None
        self._status = 'idle'
        self._thread = None
        self._sequence = 0
        self._generation = 0

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f'ai26-rtsp-{self.camera_id}', daemon=True)
        self._thread.start()

    def _open(self):
        params = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS,
                  cv2.CAP_PROP_READ_TIMEOUT_MSEC, READ_TIMEOUT_MS,
                  cv2.CAP_PROP_N_THREADS, 1]
        return self._capture_factory(self._url, cv2.CAP_FFMPEG, params)

    def _run(self):
        delay = 1.0
        while not self._stop.is_set():
            capture = None
            try:
                with self._lock:
                    self._status = 'connecting'
                capture = self._open()
                if not capture.isOpened():
                    raise RuntimeError('not opened')
                delay = 1.0
                with self._lock:
                    self._generation += 1
                    self._status = 'connected'
                while not self._stop.is_set():
                    ok, frame = capture.read()
                    captured_at = self._clock()
                    if not ok or frame is None:
                        raise RuntimeError('read failed')
                    with self._lock:
                        self._sequence += 1
                        self._latest = (captured_at, self._sequence, self._generation, frame)
                        self._status = 'connected'
            except Exception:
                # OpenCV errors can contain the full URL, including credentials.
                with self._lock:
                    self._latest = None
                    self._status = 'reconnecting'
                log.warning('Live capture unavailable for %s; retrying with backoff', self.camera_id)
            finally:
                if capture is not None:
                    try:
                        capture.release()
                    except Exception:
                        pass
            self._stop.wait(delay)
            delay = min(delay * 2, 30.0)
        with self._lock:
            self._latest = None
            self._status = 'stopped'

    def latest(self, max_age=MAX_FRAME_AGE_SECONDS):
        with self._lock:
            value = self._latest
            status = self._status
        if value is None or self._clock() - value[0] > max_age:
            return None, status
        return value, status

    def stop(self, timeout=READ_TIMEOUT_MS / 1000 + 2):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
