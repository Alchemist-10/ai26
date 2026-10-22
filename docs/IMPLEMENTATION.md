# Sakshi implementation

## Data path

1. `cameras.py` resolves input files and proxy playback, with explicit availability.
2. FastAPI lifespan starts one `processing.Processor`. A Linux advisory lock
   prevents a second owner of the same data directory. Sequential bounded sampling
   covers every available source without a browser request or growing queue.
3. `inference.py` lazily initializes YOLO only when the vehicle/person branch runs and,
   for plate inputs, lazy Fast-ALPR. `AI26_VEHICLE_DETECTION_ENABLED` and
   `AI26_PLATE_RECOGNITION_ENABLED` independently disable those branches at API startup;
   health reports the active settings. Privacy mode refuses to start without the
   person-detection branch used for sampled pixelation. Camera-local motion/box
   assignment IDs and OCR consensus are scoped to camera/session/track and reset on replay
   loops. Three consistent normalized reads support an identity; conflicting
   reads abstain. Ambiguous association retires implicated old IDs and retains raw
   OCR without a supported identity. Invalid/low-confidence reads stay in history.
4. Typed ingestion writes immutable frame reads and camera-local passage summaries
   to SQLite WAL. Retries of the same session/frame/kind/track are idempotent.
   A contradictory supported identity invalidates its passage for identity queries.
5. The processor attempts current unannotated-frame/crop JPEG derivatives for every new sampled read with
   SHA-256 references. Observations contain replay position, processing time,
   session/frame IDs, source clip digest, and model/version metadata. YOLO records
   checkpoint and pipeline component digests. ALPR lazily loads hashed copies of
   detector/OCR/config files and records their digests, package versions and
   execution providers; see [model provenance](PROVENANCE.md). Frame capture is
   shared per processed frame, crop bounds are clipped, and write/capacity failures
   retain raw reads with explicit incomplete image status. See [per-read images](READ_IMAGES.md).
6. Stream/snapshot endpoints read cached annotated JPEGs; previews use cached
   320-pixel JPEGs with ETag revalidation. MJPEG consumers wait asynchronously. MP4 playback never runs
   inference. Health reports availability, errors, FPS, frame age and latency.
7. Repository services derive interval statistics, candidate journeys, editable
   local rules, persistent human review and immutable report snapshots. React
   polls those services and separates explicit walkthroughs from API results.

## Contracts and persistence

`schemas.py` validates finite timestamps/confidence, ordered boxes, query strings
and rule configuration. Invalid requests return a consistent JSON error envelope.
SQLite schema version 15 has users, per-case and case-to-camera grants, hashed authentication sessions, encrypted TOTP enrollment, one-use recovery-code hashes and TOTP replay counters,
atomic authentication-attempt limits, observations, passages, alerts, reports, settings, hash-chained audit,
report artifact leases, camera revisions, directed camera-pair travel constraints and immutable
queried journey-link decisions, plus 90-day live-source traffic buckets. Existing
versions migrate automatically; unknown future versions fail. Audit consistency
is locally verifiable, and an operator can sign a verified chain-head checkpoint
for off-host retention. Sensitive-access entries include the user, case ID, purpose, route,
and method. New observations retain camera metadata snapshots. Legacy reads
explicitly use current-catalog fallback. See [persistence contracts](PERSISTENCE.md)
for API edits, version history and limits. The repository is intended for a
single local API process, not a distributed ingestion deployment.

Authenticated active alert escalations retain the case used when they were
created; non-admin users can list and resolve only that case's queue. Admins
assign cameras to cases, and scoped analytics, alert, route, evidence and footage
requests are limited to those cameras. This is a coarse camera boundary:
observations are not individually assigned to cases, so separate cases sharing
a camera can see the same observations. Legacy alerts without camera IDs remain
admin-visible, and global rule editing is administrator-only.

Evidence report version 5 can optionally include an Ed25519 signature. Signing
uses a protected host-mounted private key; an offline verifier checks the report
digest and signature against a separately trusted public key. Unsigned reports
remain available when no key is configured, and signatures establish neither
camera truth nor OCR/identity accuracy. See [report signing](REPORT_SIGNING.md).

Authentication is an optional overlay with role checks, CSRF protection,
case/purpose access auditing, and a first-run administrator bootstrap secret.
See [authentication and access scope](AUTHENTICATION.md).

A read ID identifies an immutable model observation. A passage ID combines camera,
replay session, model kind and local track. Plate and vehicle tracks remain
separate; their association has not been validated. A vehicle passage is counted
once when at least one observation falls in the interval. It is not a unique
city-wide vehicle. Raw reads are API-limited to 5,000; SQL aggregate queries do
not inherit that limit. Default windows expire at read time even if no data arrives.

`ts` is replay observation time; `source_time_seconds` is position in the clip;
`processed_at` is the processing completion time. Imports may also carry an
operator-claimed original recording start and uncertainty; reads and image
references retain the derived UTC claim as unverified metadata. It does not replace
replay time or enable physical cross-camera links. Replay clocks and live
capture-arrival clocks cannot support physical travel-time inference; those
links remain unresolved candidates with null speed until synchronized capture
clocks are available. The claimed offset uses frame index divided by reported
FPS and is approximate for variable-frame-rate sources. For manual observations
or legacy data, an unknown time basis now stays unresolved even when a route
window exists. Only an explicit `synchronized_capture_clock` basis can pass the
clock gate; no current runtime source emits it. Location coordinates and travel
windows still require independent validation, and an accepted link would remain
a candidate association rather than proof of identity. Rejected links and mixed
routes require review, with null speed for equal/nonpositive timestamps.

## API

| Method | Route | Output |
| --- | --- | --- |
| GET / POST | `/api/auth/status`, `/api/auth/login` | Authentication mode and session creation |
| GET / POST | `/api/auth/me`, `/api/auth/logout` | Current identity and session termination |
| POST | `/api/auth/me/password` | Change the signed-in user's password after current-password verification; revokes all sessions |
| GET / POST / PATCH | `/api/auth/users` | Administrator account management; password reset is a nested POST |
| GET | `/healthz` | Minimal public liveness response |
| GET | `/api/cameras`, `/api/health` | Persisted catalog, availability and actual processor health; detailed global health requires admin when authentication is enabled |
| GET | `/api/metrics` | Prometheus 0.0.4 text metrics for bounded processor health and inference timings; administrator session or route-limited bearer token when authentication is enabled |
| GET / PUT | `/api/cameras/{camera}/configuration` | Current/historical metadata or audited revision update with stale-edit protection |
| GET | `/api/journey-links` | Stored queried decision history; plate/arrival-time filters and bounded limit |
| GET | `/api/video/{camera}`, `/api/stream/{camera}` | MP4 playback / shared annotated MJPEG |
| GET | `/api/preview/{camera}` | Cached 320-pixel sampled JPEG; ETag / 304; missing 404 or unready 503 |
| GET | `/api/snapshot/{camera}` | Fresh annotated JPEG; 404 missing or 503 not ready |
| GET | `/api/events` | Raw reads; camera/plate/time filters and bounded limit |
| GET | `/api/stats`, `/api/flows` | Frame/passages counts, confidence, computed accepted-link flows |
| GET | `/api/trajectory/{plate}` | Supported observations, accepted/rejected/unresolved links |
| GET | `/api/alerts`, `/api/rules` | Persistent rule alerts / current local configuration |
| PUT | `/api/rules` | Audited persistent watchlist, history/effective-date conditions, local zone permits, camera zones and dwell zones |
| POST | `/api/alerts/{id}/review` | Acknowledgement/review/disposition with history |
| POST | `/api/nlquery` | Supported deterministic intent or explicit unsupported response |
| POST | `/api/evidence/{plate}` | Immutable versioned report; empty interval rejected |
| GET | `/api/reports/{id}` | Stored JSON attachment, hash-checked and expiry-enforced |
| GET | `/api/reports/{id}/package`, `/print` | Verified artifact ZIP / dedicated printable snapshot |
| GET | `/api/artifacts/{sha256}` | Verified JPEG derivative or missing/corrupt error |

Interval-capable routes accept UTC epoch `since`/`until`. Query dates use
`AI26_TIMEZONE`, not the browser's accidental timezone. Supported query grammar
includes one plate/camera, vehicle class, busiest camera, alerts and simple
calendar/time bounds. Multiple identities/clocks and unsupported colors/congestion
are rejected rather than silently broadening a query. There is no LLM, fake SQL,
external government registry or permit authority, or measured congestion classifier.

## Alerts and traffic

Watchlist rules are editable local matches; initial entries are labeled examples.
Restricted-camera rules mean a zone sighting, not an unauthorized-access finding.
Dwell requires one local track inside a configured normalized rectangle over an
elapsed duration, at least three samples, and bounded inter-sample gaps. Exits and
gaps reset it. Review is persistent; unauthenticated local reviewer names are
claims, while authenticated reviews use the signed-in account. External
notification delivery remains unavailable. Class-only cross-camera
re-identification and six-frame loitering are removed.

Analytics separate raw frame reads, camera-local sampled passages, model confidence
and available/fresh-processing cameras. Accepted-link flows are computed, not fixed
example rows. Activity-map counts do not claim calibrated congestion, occupancy,
road density, traffic speed or historical weekday/hour baselines.

## Reports and retention

Reports since version 2 store a deduplicated model-provenance summary with
missing/exact-file coverage. Version-4 reports also store heuristic top-three
image review candidates; version-3 reports store current sampled-read
frame/crop coverage and explicit legacy/failure counts. Version-1/2/3 reports retain
their original snapshots.
Each report stores its exact interval, deduplicated supporting observations, all
raw reads from those passages, raw/canonical OCR, link decisions, artifact references,
provenance, timestamps and limitations. More than 5,000 raw reads requires a shorter
interval. JSON, ZIP and print use that snapshot, regardless of subsequent reads.
SHA-256 hashes canonical JSON excluding its own hash field; artifact bytes must
match their referenced digests. Packages over 64 MiB are refused. Print contains
both passage observations and supporting raw reads, rather than the dashboard.

Reports expire after 24 hours. A separate lifespan maintenance thread cleans
expired reports/leases and observations/images using the configured retention
period (seven days by default, 7–365 days) every minute, including when inference
is disabled or fails. Active reports protect their existing source images until
report expiry; version-1 reports receive leases during migration. Report creation
checks referenced images and acquires leases under the same repository lock as
cleanup. Missing or corrupt images reject creation; later manual file removal or
corruption still fails download explicitly. A model input frame is a decoded JPEG
**derivative**, not the original recording. The source clip digest identifies that
recording. Hashes are not signatures, authenticated chain of custody, or proof of
correct OCR. Report accesses and review changes receive local audit records.
Optional report signing and operator-run signed audit checkpoints are available;
automatic off-host anchoring, key lifecycle controls and independently protected
audit storage remain operational work.

## Validation and remaining gates

Unit/contract tests use temporary storage and deterministic fixtures. The
`evaluation/` CLI measures box precision/recall, exact OCR strings/abstentions,
ID switches, visible-track fragmentation, link/rule decisions and passage error. Its example is synthetic and
cannot establish real accuracy. Held-out tracking accuracy, independently split data, measured
fusion gains, calibration, labeled adverse conditions, original recording clocks,
and sustained target-hardware benchmarks remain release gates.

See `PROGRESS.md` for every task from the implementation plan. Core engineering
improvements do not satisfy missing-footage accuracy gates. Restoration,
learned identity/topology, hardware RTSP validation and deployment hardening remain
separate work packages; their implementation and evidence status is tracked there.

## Desktop performance

The camera wall shows one 320×180 sampled preview per visible tile and one focused native MP4 player.
Switch to “Sampled detections” for the shared annotated stream, which shows its
actual low sampling FPS. Playback has no detection overlay and can be paused or
seeked independently; it does not seek the shared processor. The camera wall
loads no video. In the default mode the focused player stays idle until an
operator chooses a view; opt-in privacy mode defaults to sampled detections.
Viewport-distant tiles do not poll previews. Hidden pages stop polling, abort
pending reads and pause playback; return triggers refresh. Serial polling cannot
pile up overlapping requests. Analytics/activity share the root camera catalog,
and the log requests only its most recent 40 rows. The CPU default uses two Torch
intra-op threads and one FFmpeg decoder thread per capture; `AI26_CPU_THREADS`
permits 1–8 Torch threads.

See `PERFORMANCE.md` for measured results and their limits. Sparse sampling remains
an accuracy limitation; these changes do not claim real-time full-frame inference.

## Local association

`tracking.py` retains the public `CentroidTracker` name for compatibility. Its
implementation now predicts box motion from the last two observed positions,
gates class/size/shape/distance, and solves a global assignment with explicit
unmatched choices. Near-equal competing assignments retire implicated old tracks
and assign fresh ambiguous IDs. The plate pipeline keeps raw/canonical strings
but abstains from supporting identity for those associations. Track histories
contain observed positions only; they never present predicted motion as evidence.

Tracks expire after at most 12 elapsed seconds or the configured missed-frame
bound. The processor resets trackers/fusion at replay/session boundaries.
Observations include association status/cost and tracker version. Cost is a
heuristic used for local association, not a probability or human verification.
Sparse samples, nonlinear motion, similar boxes and camera occlusion can still
fragment tracks or overcount passages. Vehicle/plate tracks remain separate;
learned appearance and validated vehicle/plate linkage are not implemented.

See `TRACKING.md` for synthetic tests, timing samples and evaluation requirements.

## Managed source selection

Browser upload prepares an immutable release outside the running binding. Source
inspection separates cached original/playback from next-startup selection. The
selection POST rehashes both files in a worker thread under source import ownership,
checks a canonical metadata token, and atomically publishes a linked local selection
record with the pointer. Rollback uses only the displayed retained parent chain.
Source roles activate together on host restart; a pending selection never changes
per-frame or playback resolution. See [SOURCE_SELECTION.md](SOURCE_SELECTION.md).

## Processing timing and scheduling

Only attempted source/decode/inference work consumes a sampling slot. Missing or
backoff sources are checked in round-robin order without a slot delay; sweeps with
no attempts sleep one second. Failed attempts still spend a slot and use the
existing retry deadline. Successful phase timings use a bounded 64-sample window
per camera; failed/overrun attempts and first-success timing remain separate.
Health uses a monotonic FPS denominator and a stable run ID for counter-window
verification. The read-only profiler adds no producer or source mutation. See
[RUNTIME_PROFILE.md](RUNTIME_PROFILE.md).

## Bounded recorded-frame advancement

The owner can reuse a verified decoder position for nearby increasing sample
indices. It performs at most 128 explicit grab calls, then retrieves the target
once and verifies the next frame position. Initial, backward, repeated, large
or unverified positions use seeking. Failure removes the cursor and enters the
existing error/backoff/reopen path before any observation is inserted. Decode
state is per camera and cleared on missing source, failure, reopen and shutdown.
No extra reader, worker or full-frame archive is added. See
[DECODE_SAMPLING.md](DECODE_SAMPLING.md).
