# Running Sakshi

## Prerequisites

- Linux: the single-processor ownership lock and launcher use POSIX process groups.
- Python 3.12 (`backend/.python-version`), `uv`, Node.js 22.12+ and npm.
- Internet for initial dependencies/models and browser map tiles/fonts. Vehicle
  models initialize in the background; ALPR initializes only for plate inputs.
- The committed lock selects the default PyTorch build on Linux. GPU setup is a separate,
  untested configuration; a normal frozen sync must not select CUDA packages.

## Startup and restart

```bash
uv run run.py
# Subsequent starts after dependencies were installed:
uv run run.py --skip-install
# During frontend development, opt into Vite hot reload:
uv run run.py --skip-install --dev-frontend
```

Open http://localhost:5174. Ctrl+C or SIGTERM stops both service process groups,
including their child processes. Allow up to 35 seconds for inference shutdown.
Only one API worker may own a data directory. Do not use Uvicorn `--workers` or
`--reload` with processing enabled. Stop the existing instance before restarting.
Observations remain in SQLite; a restart creates new replay/track sessions.

The default launcher builds and serves the optimized frontend, keeping local
demo startup close to production behavior. `--dev-frontend` uses Vite's
unbundled hot-reload server while you are editing frontend code. The first
command runs `uv sync --frozen` and `npm ci`; `--skip-install` reuses those
installations but still rebuilds the production frontend. If the lock or package
manifest changes, run the first command again. A process exiting stops its
sibling automatically.

## Configuration

The launcher does not load the root `.env` automatically. Export it first:

```bash
cp .env.example .env
set -a
. ./.env
set +a
uv run run.py
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI26_BACKEND_PORT` | `8001` | Launcher API port and frontend proxy target |
| `AI26_FRONTEND_PORT` | `5174` | Frontend port and API CORS origins |
| `AI26_API_TARGET` | `http://127.0.0.1:8001` | Optional frontend proxy override |
| `AI26_FOOTAGE_ROOT` | `backend/data/footage` | Original input root |
| `AI26_DATA_ROOT` | `backend/data` | SQLite, JPEG storage and default managed source root |
| `AI26_SOURCE_ROOT` | `<AI26_DATA_ROOT>/sources` | Optional managed recorded imports; same value for CLI/API |
| `AI26_PROCESSING_ENABLED` | `1` | Set `0` for API/fixture tests without models |
| `AI26_VEHICLE_DETECTION_ENABLED` | `1` | Set `0` to skip the YOLO vehicle/person branch; restart the API to apply. Privacy mode requires this branch for sampled person pixelation. |
| `AI26_PLATE_RECOGNITION_ENABLED` | `1` | Set `0` to skip plate detection/OCR while leaving vehicle detection available; restart the API to apply. |
| `AI26_TOTAL_INFERENCE_FPS` | `2` | Total scheduled sampling budget, clamped 0.1–10 |
| `AI26_FORWARD_DECODE_MAX_FRAMES` | `128` | Global maximum explicit forward grab calls, clamped 0–128; 0 forces seeking. Exact hash-matched CAM-07/09 originals use a measured 221-call bound unless this variable is explicitly set; all other sources remain at the global bound. |
| `AI26_RECORDED_DECODE_THREADS` | `2` | FFmpeg decode threads for recorded sources, clamped 1–4; restart the API to apply |
| `AI26_TIMEZONE` | `Asia/Kolkata` | Calendar/time interpretation for query intents |

Sampling is sequential and skips through recorded clips using elapsed replay
position. Two scheduled frames/second is a budget, not a guaranteed throughput.
Health exposes actual per-camera FPS, frame age, latency and errors. No growing
capture queue is used. The API ports differ from Godseye's 8000/5173.

## Footage

The six H.264 proxies `backend/static/playback/CAM-01.mp4` through `CAM-06.mp4`
support local playback and vehicle inference. For CAM-07–09 provide these files
under `AI26_FOOTAGE_ROOT`:

```text
numberplate-vids/clip 4.mp4
numberplate-vids/clip_2_00_25-00_50.mp4
numberplate-vids/clip_2_00_30-01_00.mp4
```

Alternatively supply H.264 MP4 proxies at `backend/static/playback/CAM-07.mp4`,
`CAM-08.mp4`, and `CAM-09.mp4`. Additional clips and data are ignored by Git.
Managed imports take precedence over these defaults after restart. Use the
[recorded-source import command](docs/SOURCE_IMPORT.md) to validate/copy a clip and
prepare its browser playback without editing Python. Camera settings also offers
[streamed browser preparation](docs/SOURCE_UPLOADS.md), bounded to 128 MiB, with
manual check/cancel. Ready releases can be [selected in settings](docs/SOURCE_SELECTION.md),
including rollback to a retained parent. Selection preserves running inference and
playback until a host restart. The offline selector still requires the processor stopped. Within the original defaults,
originals take precedence for inference and H.264 proxies for playback. Camera
metadata and recording clocks still require independent validation.

The nine configured cameras stay visible; availability explicitly reports six
available and three missing until supplied. Missing video/stream returns 404;
a present source without a fresh processed snapshot returns 503. Processing
starts with the API, independent of which dashboard page is open.

## Separate processes

```bash
# Terminal 1, repository root:
uv sync --frozen --directory backend
uv run --frozen --directory backend uvicorn main:app --host 127.0.0.1 --port 8001
# Terminal 2, frontend development server (the production build is the default launcher mode):
cd frontend
npm ci
npm run dev
```

API catalog: http://127.0.0.1:8001/api/cameras; detailed processing health:
http://127.0.0.1:8001/api/health (administrator session when auth is enabled);
public liveness: http://127.0.0.1:8001/healthz; interactive docs:
http://127.0.0.1:8001/docs.
Vite dev and local preview proxy `/api` to the configured backend. Networked
deployment uses the Nginx same-origin proxy described in [DEPLOYMENT.md](docs/DEPLOYMENT.md).
Model/capture failures appear in health and retry after 10 seconds.

## Checks and evaluation

```bash
uv run --frozen --directory backend python -m unittest discover -s ../tests -v
python evaluation/evaluate.py --records evaluation/example.jsonl --output evaluation/results/fixture.json
cd frontend
npm run lint
npm run build
```

For a local reviewed-crop comparison, first have a reviewer fill the ignored
`backend/data/review/.../groundtruth-template.json` files, then run:

```bash
python backend/evaluate_review.py \
  --database backend/data/ai26.sqlite3 \
  backend/data/review/cam07-09-groundtruth-template.json \
  backend/data/review/followup/groundtruth-template.json
```

The command verifies crop hashes and exact source/session/frame/crop references.
It prints aggregate match, mismatch and pipeline-rejection counts only; reviewed
plate strings remain in the local ignored files. A small selected crop set is not
a held-out accuracy evaluation.

Tests disable background inference and use temporary databases and deterministic
fixtures. The evaluation example is explicitly synthetic; its metrics prove the
metric implementation, not real detector/OCR accuracy. See `evaluation/README.md`
for the labeled JSONL format. Do not recursively compile the backend virtualenv.

## Data and exports

The database and artifacts are local, ignored files. Back up the data directory
with the API stopped (SQLite uses WAL while running). Default views cover the last
five minutes; explicit date/time queries access retained history. Observations
and source JPEG derivatives are cleaned after seven days, reports expire after
24 hours. Active reports lease their referenced images until report expiry.
Maintenance runs independently of inference. Missing/corrupt artifacts fail
explicitly; hashes do not recover manually removed files. Reports are local snapshots, not signed evidence.

## Static walkthrough

```bash
python -m http.server 8080 --directory demo
```

http://localhost:8080 uses synthetic events and simulated queries, without the
backend/models. Its CDN maps/charts need internet.

## Playback and CPU budget

Camera tiles are cached sampled previews. The focused camera defaults to native
recorded playback; choose **Sampled detections** for shared inference overlays and
its measured sampling FPS. Only one video plays, and hidden pages pause media and
polling. The source video and inference sample positions may differ after seeking.

`AI26_CPU_THREADS=2` is the desktop default (range 1–8). Recorded-video decoders
use two FFmpeg threads by default (bounded by `AI26_RECORDED_DECODE_THREADS`, 1–4);
live capture retains its single-thread decoder. The processor retains the total
sampling budget configured by `AI26_TOTAL_INFERENCE_FPS`. Changing these budgets
trades processing cost and temporal coverage;
benchmark on the test host before claiming throughput or detection accuracy.

## Runtime profiling

Missing cameras and sources in retry backoff do not consume inference slots.
Available cameras share `AI26_TOTAL_INFERENCE_FPS`; slow attempts complete without
a catch-up queue, and an all-unavailable sweep waits one second. Health exposes
bounded per-camera source/decode/inference/artifact/persistence/JPEG timings,
failed attempts and budget overruns. These are sampled processing costs, not
browser frame drops or accuracy.

Run the [read-only profiler](docs/RUNTIME_PROFILE.md) while the app runs:

```bash
uv run --frozen --directory backend python ../evaluation/profile_runtime.py \
  --duration 120 --output ../evaluation/results/runtime.json
```

An optional Linux `--pid API_PROCESS_PID` samples CPU/RSS without signaling the
process. The profile uses actual counter deltas and marks restarts/unavailable
counters as unverified. It adds no inference worker or persistent app polling.

Recorded sampling uses bounded forward grabs from a verified decoder position for
nearby targets. Initial/backward/repeated/large targets use the existing seek path.
The hard forward limit is 128 calls, including the target frame; set
`AI26_FORWARD_DECODE_MAX_FRAMES=0` to disable the optimization. Read
[DECODE_SAMPLING.md](docs/DECODE_SAMPLING.md) for target verification and limits.
