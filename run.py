#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Install locked dependencies and start the Sakshi backend and frontend."""
import atexit
import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROCS: list[subprocess.Popen] = []
SHUTDOWN_REQUESTED = False


def request_shutdown(*_):
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True


def cleanup():
    # uv and npm each spawn children. Stop the complete session so Ctrl+C and a
    # failed sibling cannot leave Vite, Uvicorn, or inference running behind.
    for process in PROCS:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 35
    for process in PROCS:
        try:
            process.wait(timeout=max(0, deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-install', action='store_true', help='Reuse an already synced backend and frontend installation')
    parser.add_argument('--dev-frontend', action='store_true', help='Run Vite with hot reload instead of the optimized production build')
    options = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('The current shared-processor launcher requires Linux')
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    backend_port = os.environ.get("AI26_BACKEND_PORT", "8001")
    frontend_port = os.environ.get("AI26_FRONTEND_PORT", "5174")

    if not options.skip_install:
        subprocess.run(["uv", "sync", "--frozen"], cwd=ROOT / "backend", check=True)
        subprocess.run(["npm", "ci"], cwd=ROOT / "frontend", check=True)
    if not options.dev_frontend:
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "frontend", check=True)
    PROCS.append(subprocess.Popen(
        ["uv", "run", "--frozen", "--no-sync", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", backend_port],
        cwd=ROOT / "backend", start_new_session=True,
    ))
    frontend_command = ["npm", "run", "dev"] if options.dev_frontend else ["npm", "run", "preview"]
    PROCS.append(subprocess.Popen(frontend_command, cwd=ROOT / "frontend", start_new_session=True))
    mode = "Vite development" if options.dev_frontend else "optimized production build"
    print(f"AI26: http://localhost:{frontend_port} (API :{backend_port}, {mode}). Ctrl+C to stop.", flush=True)
    while not SHUTDOWN_REQUESTED and all(process.poll() is None for process in PROCS):
        time.sleep(0.2)
    return next((process.returncode for process in PROCS if process.returncode is not None), 0)


if __name__ == "__main__":
    sys.exit(main())
