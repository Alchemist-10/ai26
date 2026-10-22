# Sakshi — Citywide vehicle tracking and analytics

**[Story site](https://moneytosms.github.io/ai26/) · [Slides](https://moneytosms.github.io/ai26/present)** (source in `site/`, run `cd site && npm ci && npm run dev`)

Sakshi is a citywide vehicle tracking and analytics system for camera networks.
It detects and tracks vehicles, reads number plates, links sightings into
candidate journeys across cameras, and gives traffic and investigation teams one
place to review activity, alerts, and evidence. Processing is partitioned by
camera, so the design is meant to scale to any number of feeds.

The prototype has been exercised on the sample feeds. The included clips work
locally; CAM-07–09 need readable plate footage before real OCR and cross-camera
accuracy can be evaluated. One background processor samples every available
camera, and browser views read its cached output, so more viewers add no
inference load.

This is an independent AI course project. The SIH submission and competition
materials remain in the original Godseye repository.

## Start

On Linux, install Python 3.12, Node.js 22.12+ with npm, and `uv`, then run:

```bash
uv run run.py
```

Open **http://localhost:5174**, API **http://127.0.0.1:8001**. The frozen lock
installs the default PyTorch build on Linux. After the first installation, restart with
`uv run run.py --skip-install`. The launcher serves the optimized frontend by
default; use `--dev-frontend` when actively editing the UI. See [RUN.md](RUN.md)
for configuration and checks.

## Capabilities

- **Detection and tracking:** YOLO vehicle and person detection, local motion-based
  box association that abstains when ambiguous, and shared annotated feeds.
- **Plate reading:** per-camera, per-track OCR consensus that abstains on
  conflicting reads. Raw, failed, and canonical reads stay separate, and each new
  read records exact model and pipeline hashes.
- **Read evidence:** every new sampled read attempts its own frame and crop capture,
  with explicit missing coverage and a configurable 2 GiB image budget.
- **Journeys:** deduplicated passages, distinct accepted, rejected, and unresolved
  cross-camera candidate paths, explicit walkthrough selection, time filters, and
  true empty investigations.
- **Footage onboarding:** offline recorded-source import that preserves original
  bytes, with validated browser playback and explicit replacement and restart
  activation. Browser uploads are prepared as inactive, validated releases with
  manual status and cancel. Selection is hash-checked, supports retained-parent
  rollback, and takes effect after a host restart.
- **Camera settings:** versioned metadata with source inspection, pending-restart
  status, bounded import history, audited edits, read-only revision history,
  preserved drafts, and explicit concurrent-save recovery.
- **Rules and alerts:** editable local watchlists, zone sightings, dwell-time rules,
  and a durable alert-escalation queue with reassignment and audit history.
- **Queries:** bounded rule-based plate, camera, class, and date queries. No LLM or
  registry lookup.
- **Sampling and health:** recorded sampling advances nearby verified frames with
  bounded grabs. Available cameras share one sampling budget. Health reports actual
  processing state, sampled passage counts, and accepted-link flow counts. Model
  confidence is labelled separately from measured accuracy. A read-only runtime
  profiler exposes bounded phase timings.
- **Reports:** immutable JSON reports, verified frame and crop ZIP packages, print
  and PDF views, expiry enforcement, and rejection of empty reports.
- **Quality and deployment:** isolated regression tests, a reproducible evaluation
  CLI, CI configuration, and optional Docker Compose packaging with same-origin
  Nginx API routing and verified SQLite snapshot and restore scripts.

## Current status and next steps

Recorded clips carry replay timestamps, not synchronised original capture times,
so cross-camera links remain unresolved candidates. Heuristic tracking and OCR are
not validated identity systems, and passage counts are camera-local sampled counts,
not unique vehicles citywide. A report hash detects changes; it is not a digital
signature.

Next steps:

- Held-out accuracy evaluation for detection, OCR, and cross-camera linking.
- Synchronised clocks and surveyed camera locations before any identity or journey claims.
- Occupancy, calibrated speed, and historical congestion.
- Fuzzy plate linking and learned appearance tracking.
- Production access controls and optional weather restoration.

The separate `demo/` walkthrough is synthetic. Missing cameras and empty
investigations never receive its observations automatically.

| Path | Purpose |
| --- | --- |
| `backend/` | API, shared inference owner, SQLite repository, rules and artifacts |
| `frontend/` | React/TypeScript investigation and activity dashboard |
| `evaluation/` | Labeled-record evaluation contract and synthetic metric fixture |
| `tests/` | Deterministic backend regression and contract tests |
| `docs/IMPLEMENTATION.md` | Data contracts, architecture and current limits |
| `docs/PROGRESS.md` | Full implementation checklist with completion evidence |
| `docs/PERSISTENCE.md` | Camera revision and stored journey decision API |
| `docs/SETTINGS.md` | Metadata editor, draft/conflict recovery and browser validation |
| `docs/ALERT_REVIEW.md` | Alert decisions, durable escalations and workflow limits |
| `docs/DEPLOYMENT.md` | Local Compose deployment, database backup and restore |
| `docs/MODEL_ROLLOUT.md` | Pinned detector weights, camera-scoped canary assignment and rollback |
| `docs/SOURCE_IMPORT.md` | Validated recorded footage import, activation and recovery |
| `docs/SOURCE_STATUS.md` | Read-only source inspection, pending imports and history |
| `docs/SOURCE_UPLOADS.md` | Streamed browser preparation, cancellation and retained receipts |
| `docs/SOURCE_SELECTION.md` | Browser selection, retained-parent rollback and host restart |
| `docs/RUNTIME_PROFILE.md` | Sampling budget, bounded timing metrics and runtime profiling |
| `docs/DECODE_SAMPLING.md` | Bounded recorded-frame advancement, exact-pixel validation and runtime limits |
| `docs/PROVENANCE.md` | Exact model/config identity, report coverage and validation limits |
| `docs/READ_IMAGES.md` | Per-read images, failure coverage, storage budget and measured capture cost |
| `docs/IMPORT.md` | Import provenance and separation from the SIH project |

Camera metadata revisions and queried journey-link history are durable in schema 3.
See [persistence API and limitations](docs/PERSISTENCE.md).
