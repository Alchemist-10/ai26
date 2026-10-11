# AI26 — Multi-camera vehicle analytics

Independent AI course project for recorded-camera vehicle detection, plate OCR,
candidate journeys, local rule review, and traffic activity. The SIH submission
and competition materials remain in the original Godseye repository.

One background processor samples every available camera. Browser streams and
snapshots consume its cached output; opening more viewers does not add inference
workers. Six included vehicle clips work locally. CAM-07–09 need readable plate
footage before real OCR and cross-camera accuracy can be evaluated.

## Start

On Linux, install Python 3.12, Node.js 22.12+ with npm, and `uv`, then run:

```bash
uv run run.py
```

Open **http://localhost:5174**, API **http://127.0.0.1:8001**. The frozen lock uses
CPU PyTorch on Linux. After the first installation, restart with
`uv run run.py --skip-install`. See [RUN.md](RUN.md) for configuration and checks.

## Working functionality

- YOLO detections, local motion/box association with ambiguity abstention, and shared annotated feeds.
- SQLite observations, replay sessions, deduplicated passages, review history,
  local rules, versioned camera metadata, queried journey decisions, report snapshots,
  and audit records that survive API restart.
- Per-camera/per-track OCR consensus with abstention on conflicting reads;
  raw, failed, and canonical OCR reads remain separate. Exact ALPR weight/config
  digests and pipeline component hashes identify newly processed reads. Each new
  sampled read attempts its own frame/crop capture, with explicit missing coverage
  and a configurable 2 GiB image budget.
- True empty investigations, explicit walkthrough selection, time filters, and
  distinct accepted/rejected/unresolved candidate paths.
- Offline recorded-source onboarding with original-byte preservation, validated
  browser playback, explicit replacement and restart activation.
- Browser source uploads prepare inactive, validated releases with manual status/cancel;
  browser hash-checked selection and retained-parent rollback take effect after host restart.
- Camera settings with source inspection/pending-restart status, bounded import history,
  audited metadata edits, read-only revision history, preserved
  drafts and explicit concurrent-save recovery.
- Editable local watchlists, zone sightings, elapsed-time dwell rules, and review.
- Actual processing health, sampled passage counts, and computed accepted-link
  flow counts. Model confidence is labeled separately from measured accuracy.
- Bounded rule-based plate/camera/class/date queries; no LLM or registry lookup.
- Immutable JSON reports, verified frame/crop ZIP packages, dedicated print/PDF
  views, expiry enforcement, and empty-report rejection.
- Isolated regression tests, a reproducible evaluation CLI, and CI configuration.

## Limits and remaining work

Recorded clips have replay timestamps, not synchronized original capture times.
Their cross-camera links remain unresolved candidates. Heuristic local tracking and OCR
are not validated identity systems; passage counts are camera-local sampled
counts, not unique vehicles across the city. Occupancy, calibrated speed,
historical congestion, fuzzy plate linking, learned appearance tracking, held-out accuracy
measurements, production access controls, and optional weather restoration are
pending. A hash detects changes to a report; it is not a digital signature.

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
| `docs/SOURCE_IMPORT.md` | Validated recorded footage import, activation and recovery |
| `docs/SOURCE_STATUS.md` | Read-only source inspection, pending imports and history |
| `docs/SOURCE_UPLOADS.md` | Streamed browser preparation, cancellation and retained receipts |
| `docs/SOURCE_SELECTION.md` | Browser selection, retained-parent rollback and host restart |
| `docs/PROVENANCE.md` | Exact model/config identity, report coverage and validation limits |
| `docs/READ_IMAGES.md` | Per-read images, failure coverage, storage budget and measured capture cost |
| `docs/IMPORT.md` | Import provenance and separation from the SIH project |

Camera metadata revisions and queried journey-link history are durable in schema 3.
See [persistence API and limitations](docs/PERSISTENCE.md).
