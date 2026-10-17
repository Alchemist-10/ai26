#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Install locked dependencies and start the AI26 backend and frontend."""
import atexit
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROCS: list[subprocess.Popen] = []


def cleanup():
    for process in PROCS:
        if process.poll() is None:
            process.terminate()
    for process in PROCS:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    backend_port = os.environ.get("AI26_BACKEND_PORT", "8001")
    frontend_port = os.environ.get("AI26_FRONTEND_PORT", "5174")

    subprocess.run(["uv", "sync", "--frozen"], cwd=ROOT / "backend", check=True)
    subprocess.run(["npm", "ci"], cwd=ROOT / "frontend", check=True)
    PROCS.append(subprocess.Popen(
        ["uv", "run", "--frozen", "uvicorn", "main:app", "--reload", "--host", "127.0.0.1", "--port", backend_port],
        cwd=ROOT / "backend",
    ))
    PROCS.append(subprocess.Popen(["npm", "run", "dev"], cwd=ROOT / "frontend"))
    print(f"AI26: http://localhost:{frontend_port} (API :{backend_port}). Ctrl+C to stop.", flush=True)
    while all(process.poll() is None for process in PROCS):
        time.sleep(0.2)
    return next((process.returncode for process in PROCS if process.returncode is not None), 0)


if __name__ == "__main__":
    sys.exit(main())
