# AI26 implementation progress — 15 October 2026

This records the current reliability, tracking, persistence and performance implementation. Accuracy release gates remain open.
The original audit/plan remain the baseline. AI26 alone was changed; the Godseye
SIH source was left intact. The app runs on http://127.0.0.1:5174/.

## Status

Across all 80 planned tasks: **44 done, 35 partial, 1 pending**. Done means the stated engineering behavior works within the documented local prototype scope. It does not imply real OCR/identity accuracy. Partial tasks retain explicit remaining work below.

## What now works

Shared background six-camera processing; durable SQLite observations/passages;
per-track OCR abstention; real empty investigations; editable persistent local
rules and review; operator-managed camera-pair travel constraints; truthful camera health/activity; bounded historical query
intents; immediate camera-wall startup without a blocking welcome gate; immutable evidence JSON/ZIP/print; source/derivative hashes; report expiry and artifact leases; cached camera previews;
revisioned camera metadata, settings editor with draft/conflict recovery and queried decision history; CPU lockfile; clean launcher shutdown/restart; regression and evaluation tooling.

## Persistence update

Schema 13 stores user/session records, per-case grants, encrypted TOTP enrollment with replay counters, recovery-code hashes, active escalation case scope, audit context, camera metadata revisions, directed camera-pair travel constraints, immutable queried journey
link decisions, locally hash-chained audit records, and 90-day camera traffic buckets. The read-only verifier detects changed rows; an operator-run Ed25519 tool signs and checks audit-head checkpoints that must be retained off-host. New observations preserve configuration snapshots; legacy metadata fallback is explicit. Source routes remain fixed, calibration remains unverified, and stored decisions are historical conclusions rather than verified identity. Case scope currently applies to active escalation queues, not general row-level evidence access.
See `docs/PERSISTENCE.md` and `AI26_PERSISTENCE_VALIDATION.json` in the delivery.

## Authentication and access-scope update

The optional auth overlay now bootstraps one administrator, hashes passwords and
session tokens, atomically rate-limits authentication attempts, supports session/CSRF protection, and
enforces administrator/operator/analyst/viewer API roles and per-account case grants.
The UI provides sign-in, case/purpose selection, sign-out, and administrator account
management with case assignment. Sensitive
requests carry case and purpose context and append to the local audit chain; repeated
GET polls for the same route are coalesced once per minute to keep previews light.
Media URLs carry that context as query parameters because native browser media requests
cannot attach custom headers. Auth is disabled in the default local stack. Case
grants gate non-admin access; the service has no shared case registry. MFA is
available through a separate protected-key overlay. MFA-enrolled users can recover
passwords using their authenticator or an unused recovery code; no-MFA accounts still
depend on an administrator, and external identity remains pending.
The isolated full backend suite passes 322 tests, including a simultaneous TOTP
replay regression; frontend TypeScript build and lint
pass with the repository's two existing Fast Refresh warnings. See
`docs/AUTHENTICATION.md`.

## Optional privacy mode update

Opt-in privacy mode now uses a protected installation key to pseudonymize valid
plate identifiers in analytics responses. Sampled camera views pixelate detected
person boxes and detected plate regions, replace recognized plate overlay text,
and the API rejects raw recorded playback while enabled. Database observations
and signed evidence remain raw for authorized review. The browser defaults to
sampled detections in this mode. This remains partial: detection can miss people
or plates, intermediate footage frames are not processed, and no labeled footage
has established a false-negative rate. See `docs/PRIVACY.md`.

## Camera settings update

Camera settings edits location labels, coordinates and label confirmation through
the revisioned API. Unsaved drafts survive internal navigation and catalog refresh;
stale/unconfirmed saves require latest-revision review and a separate explicit save.
Read-only history exposes metadata source and unverified calibration. Reviewer
names remain local claims; source onboarding is separate. The page is lazy loaded,
shares the catalog and adds no polling or video playback. See `docs/SETTINGS.md`
and `AI26_SETTINGS_VALIDATION.json`.

## Source inspection update

Camera settings now separates the running inference/playback files from a selected
import pending API restart. It exposes missing/changed files, invalid selections,
bounded parent-chain history, hashes/operator claims and host-command guidance.
Manual source refresh preserves metadata drafts and adds no polling, video/model
loads or video hashing. Browser preparation, selection and retained-parent rollback
are now implemented; activation still requires host restart. Twelve new contracts plus synthetic browser outage/restart checks pass;
six idle seconds added zero source requests. See `docs/SOURCE_STATUS.md` and
`AI26_SOURCE_STATUS_VALIDATION.json`.

## Browser source preparation update

Camera settings streams a clip up to 128 MiB into an inactive validated release.
Current inference/playback remain cached; one owned worker process handles bounded
conversion with manual status/cancel and cleanup. Receipt IDs survive browser/API
restart; interrupted requests and stale or corrupted selections reject explicitly.
The host selector rehashes files with processor/import ownership, then API restart
activates both roles. No polling timers/media/ML workers or SQLite writes are added.
Seventeen new contracts, actual synthetic browser uploads, failure/retry, cancellation,
502 recovery and restart activation pass. Six idle seconds added zero preparation/source
requests. Desktop/mobile/user captures received ship at extension scope.
Ready videos/receipts are retained without aggregate cleanup; original clocks, real
plate footage and host restart management remain separate. Authenticated source
routes require operator role and case/purpose scope when auth is enabled. See
`docs/SOURCE_UPLOADS.md` and `AI26_SOURCE_UPLOADS_VALIDATION.json`.

## Browser selection and rollback update

A ready browser upload can now be selected for the next restart. Displayed parent
history supports retained-release rollback. Both files are rehashed under source
import ownership; canonical metadata tokens reject stale requests and returning
to the same release after another selection. Local reviewer/reason records are
linked on disk. Running original inference and playback remain cached until host
restart; reverting a pending selection to the running release clears the notice.
The separate POST adds no SQL writes, polling, media or ML workers. Thirteen new
contracts and actual synthetic browser selection/rollback with stale recovery
pass; two host restarts activated both roles, six linked selection records were
retained and the fixture database had zero observations/audit rows. Six idle
seconds added zero source/preparation requests. Authenticated selection records the
server-verified operator in the durable marker and status projection; the API test
confirms spoofed reviewer names are overridden. Camera settings now shows a bounded
linked selection history and reports broken records as partial. See
`docs/SOURCE_SELECTION.md` and `AI26_SOURCE_SELECTION_VALIDATION.json`. Host restart
controls and video cleanup remain separate work.

## Recorded source import update

The offline source command probes a supplied clip, preserves its original bytes,
prepares bounded browser-safe playback and publishes a hashed release manifest.
Explicit replacement retains older releases; bindings activate only on restart.
Existing processor/import ownership blocks conflicting work. Conversion and
publication failures preserve the prior source. The importer adds no API polling,
models. Browser preparation/selection are implemented; real plate footage and clock/location
validation remain separate. See `docs/SOURCE_IMPORT.md` and
`AI26_SOURCE_IMPORT_VALIDATION.json`.

## Per-read image update

New sampled reads attempt matching frame/crop JPEGs regardless of confidence or
identity status. The shared frame is encoded once; identical crop requests are
reused within that frame. Crop bounds and camera/session/frame/source references
are explicit. Write/encode/capacity failures preserve raw reads with incomplete
capture status. A configurable 2 GiB image budget preserves existing/leased files;
minute retention reconciles the cached usage index. Version-3 reports record
exact and missing image coverage; older reports are never backfilled.
See `docs/READ_IMAGES.md` and `AI26_READ_ARTIFACT_VALIDATION.json` in the delivery.

## Alert escalation update

The alert panel now supports a durable local escalation queue with recipient,
reviewer, handoff note, reassignment, resolution and audit history. With auth
enabled, the reviewer is taken from the signed-in account; local mode labels
freeform reviewer names as claims.
Active escalations remain visible outside the recent-alert window. This is an
unauthenticated local workflow; it does not send email, SMS or push notifications.
The API rejects escalation without a recipient. Isolated contracts verify target
validation, stale-window queue visibility, persistence across repository reopen,
reassignment and resolution. See `docs/ALERT_REVIEW.md`.

## Compose deployment update

Compose runs the single-worker API on a private network and serves the production
frontend through Nginx with same-origin API proxying, streaming upload limits,
gzip, immutable caching for hashed assets, health checks and persistent app data.
The published port binds to loopback by default. Online SQLite snapshots validate
integrity, rotate retained backups and support an explicitly confirmed restore
while the backend is stopped. A separate stop-required full backup includes the
database, managed sources/uploads, model cache and read-artifact images in one
manifest-verified archive; externally mounted footage, custom model mounts and
secrets remain separate. Both images, the Nginx-to-API route, six bundled sources,
compression/cache headers and database-only backup/restore were exercised in an
isolated processing-disabled Compose stack. The managed-data archive/restore also
passes isolated round-trip and tamper-rejection tests. See `docs/DEPLOYMENT.md`.

## Model provenance update

ALPR loads hashed detector/OCR/config snapshots once, records package/provider
and thread settings, and preserves them on all raw reads. Reports since version 2
summarize exact/missing model coverage consistently in JSON/ZIP/print; old reports
remain compatible. Two real ONNX sessions executed on blank inputs only. This is
execution verification, not OCR accuracy. See `docs/PROVENANCE.md` and
`AI26_PROVENANCE_VALIDATION.json` in the delivery. New reads now also identify
processing and artifact code, for nine component hashes in total, including camera/source resolution.

## Sampling budget and profiling update

Missing cameras and retry backoff no longer consume inference slots. Available
cameras retain round-robin fairness; slow attempts do not enqueue catch-up work,
and a sweep with no work sleeps. Bounded 64-sample windows report six phases,
first-success timing and successful percentiles, with separate failure/overrun
counters. FPS uses monotonic time. A local read-only profiler records counter
deltas, endpoint latency and optional Linux CPU/RSS, rejecting unverified restart
windows and process identity changes. Twelve new contracts pass. A 30-second
baseline and 120-second six-camera profile use the same two-attempt budget; their
load and replay positions are not controlled. See `docs/RUNTIME_PROFILE.md` and
`AI26_SAMPLING_BUDGET_VALIDATION.json`. Actual source/browser drops, independently
cold OCR, long-duration load, low-end devices and accuracy remain unmeasured.

## Recorded decode update

Nearby increasing source-frame targets now use bounded forward grabs from a
verified decoder position, retrieving only the target. At most 128 explicit calls
are allowed; resets, repeats, backward/large targets and unverified positions use
seeking. Failure clears the per-camera cursor before existing retry/reopen handling.
Eight new contracts pass, all 144 bundled-clip targets matched existing pixel
hashes, and 11 target indices matched an independent sequentially decoded numbered
fixture. No extra decoder, inference worker or database migration is added. See
`docs/DECODE_SAMPLING.md` and `AI26_DECODE_VALIDATION.json`. Variable-rate source
clock calibration, playback drops, low-end devices and real accuracy remain open.

## Tracking update

Local motion/box global assignment, elapsed-time expiry and ambiguity abstention
are implemented and tested. The evaluator measures visible-track fragmentation
and checks frame order within camera/session. See `docs/TRACKING.md` for timing,
constructed failure cases and limits. Real identity/count accuracy is unmeasured.

## Dataset manifest update

Evaluation now has a versioned manifest template and a standard-library validator
for clip SHA-256, relative-path safety, explicit recording/coordinate conditions,
manual plate-label coverage and split separation by vehicle, camera, location and
recording session. `--require-ready` keeps incomplete input from entering a claimed
evaluation. The current manifest remains a draft because CAM-07–09 readable footage,
original capture metadata and held-out labels are still absent. Non-synthetic
evaluation records must map to manifest clips in the held-out test split with
matching camera/session IDs. This validates data organization only; it does not
claim OCR accuracy. See `evaluation/README.md`.

## Validation

- The current branch passes all 328 backend tests with the frozen Python 3.12 CPU environment.
- Frontend lint passes with two existing shared-component Fast Refresh warnings;
  TypeScript/Vite production build passes.
- The local launcher now serves an optimized frontend by default (`--dev-frontend`
  retains hot reload). With privacy mode off, two headless browser runs confirmed
  no video/MJPEG request until a view is chosen; local preview transferred 115 KB
  versus 9.38 MB from the Vite dev server for the initial page. These short
  1280×800 samples are not real-device Core Web Vitals. See `docs/PERFORMANCE.md`.
- Fresh frozen sync installed CPU torch 2.14.0+cpu and torchvision 0.29.0+cpu.
- Live restart retained all ten sampled observation IDs; all six available cameras
  returned decodable JPEG snapshots. No old service children survived launcher stop.
- Twenty live reads had all 40 image hashes recreated from decoded source pixels;
  seventeen new tests cover per-read capture, failure, immutable coverage and storage budget.
- Short isolated capture timings were 4.381 / 6.220 / 18.353 ms median for 1 / 8 / 64
  constructed reads per frame; this adds storage/CPU work and does not establish sustained FPS.
- A separate synthetic report browser check displayed 2-of-3 image coverage and
  its legacy gap on desktop/mobile. Fixture services/data/tab were removed.
- Isolated metadata browser checks verified saves, immutable history, stale edits,
  draft navigation and API outage/restart recovery. Main catalog was unchanged;
  six idle seconds added no configuration requests. Desktop/mobile had no horizontal
  overflow. The temporary database contained no observations.
- Two generated color clips passed real FFmpeg conversion, immutable original
  hashes, API range responses, restart activation and no-op processor decoding.
  Fifteen import contract tests cover failures/replacement/cached bindings.
  No generated footage entered the main app. Source resolution hashes at startup,
  never in API catalog polling or per-frame selection.
- The database-only backup/restore procedure was also exercised against an isolated
  temporary API; restore removed a post-backup mutation and the audit chain remained valid.
- Earlier browser mobile checks at 390×844 verified camera wall, investigation and alerts,
  disabled empty export, and focus trapping/Escape restoration.
- An earlier isolated synthetic fixture on 5175/8002 exercised browser report creation,
  JSON and ZIP downloads, matching manifest/artifact hashes, and dedicated print.
  Fixture services/tabs were closed; its records were never added to the main DB.
- Evaluation command processes two deliberately imperfect synthetic records; these
  are metric regressions, not evidence of model accuracy.

Machine-readable runtime evidence is in the adjacent delivery's
`AI26_RUNTIME_CHECKS.json`. CI remote status belongs to the PR checks, not these
local results. Short runtime samples do not establish sustained throughput.

## Remaining release gates and execution order

1. Supply CAM-07–09 readable footage plus original recording timestamps, and label
   a held-out vehicle/camera/session dataset (P0-02, EV-01). Source availability
   is already explicit while these files are absent.
2. Improve local association and vehicle/plate linkage, benchmark OCR/fusion and
   tracker errors (EV-02–05). Motion/box assignment remains a heuristic baseline.
3. Validate coordinates/clocks and camera-pair topology/travel constraints, then
   evaluate exact/fuzzy identity links (P1-14–16, EV-06).
4. Calibrate traffic counts/density/speed and historical segment baselines;
   evaluate rules on positive and negative real cases (P2-01–04, EV-07–09).
5. Complete source operations: operator/case-gated administration and authenticated
   selection attribution work when auth is enabled; browser preparation records a
   server-verified uploader account separately from reviewer claims when auth is enabled; selection,
   linked history and retained-parent rollback are implemented. A Docker Compose
   backend restart/health-check helper is available; other host managers still need
   documented restart procedures.
   Metadata settings UI, metadata/link persistence, exact ALPR model provenance and per-read image capture are implemented.
6. Optional research/production phases remain separate. No restored/reconstructed
   pixels, registry verification, authenticated investigator identity, anchored
   audit history, RTSP capture or production access control is represented as done.

## Full checklist

### Correctness and investigation

| ID | Status | Task | Evidence / remaining work |
| --- | --- | --- | --- |
| P0-01 | Partial | Supply CAM-07–09 readable-plate clips, or reduce the catalog honestly to available inputs. | Six available sources and three missing sources are explicit; readable plate inputs are still absent. On 2026-10-15 the local AI26/Godseye trees, local project ZIP listings, and all three visible upstream [Godseye branches](https://github.com/moneytosms/godseye) were checked. `main` at `3d575f68de391e178d18380092e816cd1d2b4eef` and both other branch heads list playback clips only for CAM-01–06; no CAM-07–09 media, dataset archive, or Git LFS asset was found. |
| P0-02 | Pending | Prove real plate reads on supplied footage, retaining raw and canonical strings. | Real OCR cannot be proved without CAM-07–09 readable plate footage. |
| P0-03 | Done | Isolate OCR voting by camera + vehicle/plate track, not camera alone. | Camera + local plate-track consensus; independent tracks and conflicts are regression-tested. |
| P0-04 | Done | Keep `plate`, `plate_norm`, watchlist checks and UI labels consistent. | Canonical plate fields, identity queries and local watchlist use the same normalization; raw strings remain separate. |
| P0-05 | Done | Show a true no-results state for an unknown plate; make walkthrough selection explicit. | Unknown-plate browser check shows true empty results with disabled export; walkthrough requires explicit selection. |
| P0-06 | Done | Build the printable report solely from its evidence payload; never hash empty data while presenting demo hops. | Dedicated print reads the immutable snapshot; empty export is HTTP 409; print contains raw supporting reads. |
| P0-07 | Done | Deduplicate frame reads into vehicle observations before traffic counting or dwell rules. | Distinct camera/session/kind/track passages drive counts, rather than repeated frame reads. Baseline count accuracy is unmeasured. |
| P0-08 | Done | Replace six-frame loitering with tested identity/dwell-time logic. | Explicit configured zone, elapsed duration, at least three samples and bounded gaps; exits/gaps tested. Uses local baseline tracks. |
| P0-09 | Done | Rename the class-based cross-camera alert or implement real, validated identity matching. | Removed class-only cross-camera ReID/clone alert; route review does not claim identity. |
| P0-10 | Done | Expire stale observations even while all streams are idle. | Every rolling-window read filters current time, even with no new ingestion; durable history stays separate. |
| P0-11 | Done | Make equal/invalid timestamps serialize safely with an explicit rejection reason. | Equal timestamps produce null speed/rejection; finite and ordered time bounds are validated. |
| P0-12 | Done | Define trajectory status when accepted and rejected hops coexist; do not equate one accepted link with a proven journey. | Mixed routes require review; accepted links remain candidates rather than verified journeys. |
| P0-13 | Done | Plot accepted paths separately from rejected candidate hops. | Solid teal travel-gated links, dashed red rejected links, dashed amber unresolved calibration. |
| P0-14 | Done | Correct online/healthy/verified wording to reflect actual availability and validation. | Source availability and measured processor freshness replace all-camera healthy and registry-verification claims. |

### Reliable core pipeline

| ID | Status | Task | Evidence / remaining work |
| --- | --- | --- | --- |
| P1-01 | Done | Add background per-camera ingestion/inference independent of the current browser page. | One background round-robin owner processes all available cameras without a browser; six live snapshots verified. |
| P1-02 | Done | Define inference ownership so multiple viewers do not create duplicate processing/event streams. | Streams/snapshots only consume cache; two-consumer regression and exclusive Linux data-directory ownership lock. |
| P1-03 | Done | Add a typed observation schema with stable event IDs and per-track passage IDs. | Typed finite observations, deterministic idempotent read IDs, per-session local passage IDs. |
| P1-04 | Partial | Preserve source clip/frame timestamp separately from processing time; define cross-camera clock handling. | Replay frame offsets and processing times remain separate. Sampled frames now prefer FFmpeg/OpenCV's reported media position and fall back to frame index ÷ reported FPS when unavailable; the source-time basis is stored on the observation and image references. Imports can retain an optional timezone-aware, operator-claimed recording start plus uncertainty; derived UTC claims remain operator-claimed and unverified. `replay_clock` continues to block physical cross-camera links. Original NVR capture timestamps and synchronized/verified clocks are still missing. |
| P1-05 | Done | Add persistent observations, camera catalog, tracks, links and alert storage with migrations. | Schema-13 migrations retain reads/local passages/alerts and active escalation case scope, seed a revisioned camera catalog and persist directed pair constraints plus immutable queried link decisions with support and algorithm/config snapshots; 90-day camera traffic buckets store live-source samples/passages; audit records are locally hash chained and verifiable; offline source onboarding and metadata editing work; browser source preparation binds the authenticated uploader separately from reviewer claims, persists the attribution across API restart, and supports authenticated selection attribution, bounded selection-history display and retained-parent rollback; activation requires host restart, and authenticated calibration remains separate work. |
| P1-06 | Done | Expose a validated ingestion path rather than relying only on streaming request side effects. | Processor writes through typed validated ingestion rather than request-side streaming effects. No external ingestion API is claimed. |
| P1-07 | Done | Store source-frame and plate-crop references with hashes and model/version metadata. | Every new sampled read attempts its own frame/crop references with exact camera/session/frame/source context, clipped crop bounds, image/model hashes and nine component digests; capture failures/capacity/legacy gaps are explicit. Shared frame encoded once; reports store current-image coverage. Not a full video-frame archive. |
| P1-08 | Done | Test reconnect, corrupt video, end-of-file, missing clips and inference exceptions with bounded retry/backoff. | Controlled reconnect, loop boundary, missing/corrupt input, decode failure and model-download exception tests; 10-second retry and stale-frame suppression. |
| P1-09 | Done | Reset camera and panel errors after input changes or successful recovery. | Camera change/success clears focused-feed failures; API panels clear errors after recovery. Missing-to-available thumbnail remount supported. |
| P1-10 | Done | Return correct HTTP status/error schemas for invalid cameras, plates and request bodies. | Known invalid cameras/missing sources 404; invalid bodies/plates/times 422; unready snapshot 503; JSON error envelope. |
| P1-11 | Done | Add actual health/FPS/frame-age/queue/last-event metrics per camera. | Real per-camera frame age, monotonic FPS, bounded six-phase timings, failed/overrun attempt counters, last read and source/error state; missing/retry cameras do not consume sampling slots. Queue depth zero for the no-queue architecture. |
| P1-12 | Done | Separate local tracking from cross-camera identity; improve association under occlusion and clip loops. | Motion/box global assignment, ambiguity abstention, elapsed-time expiry and loop/reopen resets are tested; this is heuristic local tracking, with real occlusion/ID accuracy still unmeasured. |
| P1-13 | Done | Deduplicate repeated same-track plate reads and retain corrections without silently overwriting evidence. | Immutable raw reads, deduplicated plate passages and conflict exclusion; uncertain corrections do not silently become supported identity. |
| P1-14 | Partial | Add plate matching confidence and fuzzy matching with measured false-link limits. | Review-only canonical plate edit-distance scores and labeled-pair threshold metrics report false-candidate denominators; identity linking is always false. Scores are uncalibrated, and operational false-link limits require independent labeled vehicle pairs and held-out recordings. |
| P1-15 | Partial | Use validated camera locations and camera-pair travel constraints for cross-camera links. | Directed, audited min/max travel windows gate new cross-camera links; missing pair data stays unresolved and disabled pairs are rejected. Configuration requires both camera locations marked confirmed and is snapshotted with each link. Independent coordinate validation, road topology and measured travel windows remain absent. |
| P1-16 | Partial | Handle missing cameras, clock skew, conflicting identities and disconnected routes explicitly. | Missing sources, unsynchronized replay, conflicting tracks and operator-marked disconnected camera pairs are explicit; calibrated skew and independently verified road connectivity remain pending. |
| P1-17 | Done | Add an explicit mock known-plates registry if that is part of course scope, or remove registry-verification wording. | Removed registry-verification wording; no government registry or mock registry is presented as real verification. |
| P1-18 | Done | Make watchlist and restricted-zone data editable and persistent; add permit/history conditions where required. | Operator UI and validated persistent API manage watchlists, active windows, minimum supported sighting counts/lookback, restricted cameras, local permit periods and dwell zones. Rule changes are audited. Matching local permits yield informational visits; missing permits remain review prompts. Permits are not externally verified and the alerts make no legal determination. |
| P1-19 | Done | Add supported plate/camera/type/time intents and clear unsupported-query responses. | Bounded plate/camera/class/time/busiest/alert intents; unknown cameras and unsupported/multiple identities rejected; no fake SQL. |
| P1-20 | Done | Fix timezone/date filters; a today query must not silently mean only the last five minutes. | Timezone-aware today/yesterday/date/time bounds query retained SQL history, not just the default five-minute view. |
| P1-21 | Done | Refresh trajectory results as new observations arrive; debounce typing and clear stale export state. | Submitted searches refresh every three seconds without overlapping requests; typing does not query; changing filters replaces export state. |
| P1-22 | Done | Add a persistent CPU setup/profile and tested restart command; current manual CPU installation must not be replaced by unintended CUDA sync. | Frozen Linux CPU torch/torchvision lock; clean install, restart and launcher process-group shutdown verified. |

### Dashboard and evidence

| ID | Status | Task | Evidence / remaining work |
| --- | --- | --- | --- |
| P2-01 | Partial | Define and compute unique vehicle counts, occupancy/density and any speed metric using suitable calibration. | Deduplicated sampled camera-local passages work; globally unique counts, calibrated occupancy/density/speed do not. |
| P2-02 | Partial | Store historical segment counts/speeds and compare weekday/hour baselines rather than relative detection share. | Schema-11 introduced 90-day 15-minute buckets of successfully processed live-source samples and unique camera-local vehicle passages; schema 13 adds case-scoped active alert escalations. `/api/traffic/baselines` compares the latest completed local hour with covered prior matching weekday/hour counts, excludes replay clocks and requires at least four processed frames across two quarter-hours. Synthetic tests cover local-time alignment, replay exclusion, coverage, deduplication, expiry and baseline math. Physical segment counts/speeds, independently calibrated zero-traffic interpretation, live deployment history and independent route/capture-clock validation remain absent. |
| P2-03 | Done | Implement computed OD aggregation from accepted, deduplicated trajectories and remove fixed live flow rows. | OD counts derive from accepted deduplicated links; fixed sample rows removed. Unsynchronized footage yields no accepted flow. |
| P2-04 | Partial | Implement a measured spatial/road-segment heatmap with honest unobserved/unknown states. | Camera map, analytics and congestion views now omit unconfirmed coordinates; missing sources show unknown passage counts, and investigation maps plot only confirmed locations/transitions. Camera-local activity is shown honestly; a measured road-segment heatmap still needs calibrated locations and road data. |
| P2-05 | Done | Keep detector confidence separate from measured accuracy and human verification status. | Model confidence is explicitly separate from measured accuracy and human verification. |
| P2-06 | Done | Persist alert IDs, trigger observations, acknowledgement/review/disposition and reviewer timestamps. | Stable alert IDs, supporting read IDs, review state/history, named reviewer and timestamps persisted across reopen. |
| P2-07 | Partial | Connect a real human-review/escalation workflow; add notifications only if required by the project. | Durable local escalation/reassignment queue records recipient, reviewer, note, timestamp and audit history; authenticated mode binds reviewer to the session account and scopes active handoffs to the selected case, while local mode labels freeform names as claims. Stable cursor pages keep active handoffs reachable beyond both the recent-alert window and the first 200 entries. External notifications remain pending; this does not provide general row-level data isolation. |
| P2-08 | Done | Package evidence observations, raw/canonical OCR, frames/crops, accepted/rejected paths and metadata consistently. | Manifest/raw reads/canonical strings/artifacts/link decisions/provenance packaged consistently with verified digests; derivative and coverage limits stated. |
| P2-09 | Done | Provide direct JSON/package download and a dedicated PDF/print layout with matching report data. | Browser JSON/ZIP downloads verified; dedicated print contains the same stored snapshot and raw reads. PDF uses the browser print dialog. |
| P2-10 | Done | Enforce defined retention/expiry rather than displaying a retention string. | 24-hour report expiry, configurable 7–365-day observation/JPEG cleanup (seven-day default), schema-2 artifact leases, and independent maintenance; boundary and processing-disabled tests pass. |
| P2-11 | Done | Add report access/audit records and signing if independently verifiable evidence is required. | JSON, ZIP and print report reads append audit records; regression tests verify each route and the audit chain. Version-5 evidence reports can be Ed25519-signed and verified offline with a separately trusted public key; unsigned mode is explicit. Operators can also sign verified audit heads and retain checkpoints off-host; automated anchoring remains an OP-04 limitation. |
| P2-12 | Done | Keep demonstrations separate from live queries, including colors, confidence values and statuses. | Synthetic walkthrough/alerts are explicit selection; real queries never substitute them or export them as observed evidence. |
| P2-13 | Done | Test query, camera recovery, empty investigation and evidence export flows end to end. | Browser empty investigation, focused missing-to-working camera recovery, keyboard/mobile and isolated synthetic report downloads/print verified; API query regressions pass. |
| P2-14 | Done | Address fixed-width mobile layouts and keyboard/focus behavior in navigation and forms. | 390×844 camera wall, investigation and alerts have no root horizontal overflow; navigation focus trap/Escape restoration verified; focus/reduced-motion styles. |

### Evaluation and release

| ID | Status | Task | Evidence / remaining work |
| --- | --- | --- | --- |
| EV-01 | Partial | Prepare labeled vehicle/plate data and split by vehicle, camera/location and recording session. | Dataset manifest template and validator verify clip SHA-256, explicit labels/conditions and disjoint vehicle/camera/location/session splits. No labeled held-out clips have been supplied, so accuracy evaluation remains pending. |
| EV-02 | Partial | Measure vehicle precision/recall and false positives rather than quoting model confidence. | IoU-matched detector precision/recall evaluator implemented; no real labeled measurements. |
| EV-03 | Partial | Measure exact plate-string accuracy and rejected/invalid read rates on readable and difficult footage. | Exact string/abstention evaluator implemented; no real OCR accuracy or difficult-input strata. |
| EV-04 | Partial | Compare per-track fusion against single-frame OCR; verify it never mixes identities. | Consensus isolation/conflict regression passes; measured single-frame versus fusion ablation is pending. |
| EV-05 | Partial | Measure tracker ID switches, fragmentation and passage-count error. | ID-switch, visible-track fragmentation and passage error metrics implemented, with camera/session order checks; real labeled tracking evaluation remains pending. |
| EV-06 | Partial | Measure accepted/rejected trajectory-link precision and impossible-travel false alerts. | Positive/negative link evaluation implemented; real false-link/false-alert estimates pending. |
| EV-07 | Partial | Evaluate loitering/restricted-zone/watchlist rules with both positive and negative cases. | Positive/negative dwell, watchlist/review and zone configuration tests; labeled footage-level rule evaluation pending. |
| EV-08 | Partial | Validate derived traffic metrics against independent counts or known synthetic ground truth. | Known synthetic passage fixtures verify deduplication; independent real traffic counts/calibration pending. |
| EV-09 | Partial | Benchmark warm/cold inference latency, sustained multi-stream throughput, dropped frames and memory. | Bounded timings, read-only CPU/RSS/counter profiling, verified forward decode, and browser-local native-player dropped-frame accounting are implemented. Two 10-second desktop samples of one recorded stream measured 1.20% and 1.38% incremental dropped frames with processing disabled; six-camera runtime samples, 144 same-frame decoder checks, and an isolated 120-second replay soak are also recorded. The soak processed 239 frames with zero failures and one budget overrun at a 2 FPS total budget; plate OCR was disabled. Independently cold OCR, longer sustained load, and six-stream dropped-frame accounting remain pending. |
| EV-10 | Done | Test page changes, multiple clients, restart, idle expiry, duplicate events, bad input and model-download failure. | Isolated tests cover multiple consumers, restart, idle expiry, duplicates, invalid input, corrupt capture, replay boundaries and simulated model-download failure; live launcher restart verified. |
| EV-11 | Partial | Record sample sizes, hardware, conditions and failure cases; do not infer accuracy from the current smoke tests. | Runtime conditions and synthetic sample sizes documented; held-out accuracy samples/failure strata remain absent. |
| EV-12 | Done | Add CI for regression/build checks and a reproducible evaluation command. | Pinned-action CPU/backend/frontend CI workflow and reproducible evaluation CLI; local equivalent checks pass. Remote result recorded separately. |

### Optional research

| ID | Status | Task | Evidence / remaining work |
| --- | --- | --- | --- |
| RS-01 | Partial | Rule-based scene/plate quality and weather router with an unchanged raw-reference branch. | Offline read-only image-condition hints and enhancement candidates retain a raw reference; fixed thresholds are uncalibrated and no verified weather/plate-quality classifier or live routing is claimed. |
| RS-02 | Done | Classical CLAHE/gamma/white-balance/Retinex/dark-channel enhancement and restrained sharpening. | Offline CLAHE, gamma, gray-world, single-scale Retinex, dark-channel dehazing and unsharp tools write hashed research derivatives without replacing source images. Synthetic correctness tests pass; OCR improvement is unmeasured and requires held-out labeled footage. |
| RS-03 | Partial | Per-track best-shot/top-k frame selection and OCR character-level consensus. | Per-read crop statistics now produce top-three review candidates per local passage in version-4 reports and a capped Timeline preview; confidence-weighted character votes remain review-only. All raw reads/images remain. Ranking and OCR fusion need calibration and labeled validation. |
| RS-04 | Partial | Frame alignment/optical flow, probabilistic fusion and calibrated plate confidence. | Offline Farneback alignment for bounded same-camera image bursts with forward/backward consistency diagnostics and synthetic translation tests. It is not integrated with OCR; probabilistic fusion, calibrated plate confidence and held-out footage evaluation remain pending. |
| RS-05 | Partial | Collect adverse-weather data and build a controlled degradation generator. | Offline deterministic rain, fog, low-light, motion-blur and sensor-noise derivatives write no-clobber PNGs with source/output hashes, seed and explicit synthetic-only labels. Real adverse-weather clips, temporal consistency, held-out labels and OCR robustness measurements remain pending. |
| RS-06 | Partial | Train/evaluate a quality classifier, dehazing and deblurring models, and Indian-plate OCR adaptation. | Added a supervised readability-classifier trainer with crop/source hashes, camera/session/source-clip disjoint splits, validation-only regularization selection and held-out per-class metrics. Synthetic fixtures validate the trainer but no reviewed crop dataset exists, so there is no real model metric. Classical dark-channel dehazing/unsharp candidates exist separately; learned restoration models, paired restoration labels and Indian-plate OCR adaptation remain unimplemented pending field data. |
| RS-07 | Partial | Add restoration safety checks and preserve raw versus enhanced/reconstructed artifact provenance. | Offline enhancement derivatives carry method/parameter metadata and hashes while source hashes/status remain explicit and outputs never overwrite files; live restoration/reconstruction integration, OCR safety tests on labeled footage and deployment provenance remain. |
| RS-08 | Partial | Optional burst super-resolution with an explicit reconstructed status, not a raw-evidence claim. | Offline 2× phase-correlation/shift-and-add utility accepts bounded same-camera bursts, rejects weak registration or missing subpixel diversity, and writes no-clobber PNG derivatives with source/output hashes and explicit `reconstructed` status. Synthetic tests cover bounds, plumbing and provenance; real burst quality, motion/occlusion handling and OCR benefit remain unmeasured. |
| RS-09 | Partial | Learned camera topology and calibrated travel-time distributions. | Offline trainer estimates directed edge windows from positive training sessions and reports held-out precision/recall/false-accept denominators on session-disjoint positive/negative candidates. It rejects repeated pair samples within a session and requires coordinate/clock calibration declarations. Tests are synthetic; declarations, labels and route coverage are not independently verified. Output is review-only and never writes production constraints. |
| RS-10 | Partial | Complete raw/classical/learned/fusion ablations and model cards with data lineage. | Paired ablation runner enforces identical manifest-hashed test samples, exact labels, per-variant configuration/weight provenance and reports deltas against raw. A model-card template captures intended use, data, metrics, conditions and failure cases. No complete labeled dataset or real four-way ablation is available, so model cards remain unfilled and no best-variant claim is made. |

### Optional production and edge

| ID | Status | Task | Evidence / remaining work |
| --- | --- | --- | --- |
| OP-01 | Partial | RTSP/ONVIF camera integration and resilient capture queues. | Optional protected JSON mapping configures RTSP/RTSPS for existing cameras. Dedicated readers use bounded open/read timeouts, one-frame buffers, freshness checks and reconnect backoff; live frames use the normal inference/event/preview pipeline and capture-arrival timestamps. Fake-capture tests cover private config and reader behavior. Admin-only local WS-Discovery now lists ONVIF service endpoints and scopes without connecting to or configuring devices; actual camera/NVR interoperability, GetStreamUri/credential setup, clock synchronization and live failover on hardware remain unverified. |
| OP-02 | Partial | Authentication, role-based access and purpose/case-scoped sensitive operations. | Optional auth includes sessions, roles, CSRF, case/purpose audit, per-account grants, case-scoped active escalation queues, MFA with encrypted TOTP secrets and one-use recovery codes, administrator MFA/password reset, MFA-backed self-service password recovery, and current-password-confirmed password change that revokes sessions. It remains opt-in; this is not general row-level case isolation. Recovery for accounts without MFA, help-desk recovery and external identity remain pending. |
| OP-03 | Partial | Occupant face blurring and keyed plate pseudonyms in analytics views if those privacy features remain in scope. | Opt-in installation-keyed plate pseudonyms, detected-person/plate pixelation in sampled views, and API-blocked raw playback are implemented. Evidence remains raw; model misses and unsampled frames are possible, and no labeled field validation has measured coverage. This is not complete face blurring or guaranteed anonymization. |
| OP-04 | Partial | Durable audit logs, retention jobs, secrets handling and TLS. | Local SQLite audit chain detects row/link edits; optional TLS 1.2/1.3, authentication/MFA and Ed25519 report-signing overlays use host-managed secrets/keys. A Caddy overlay now requires authentication, enables Secure cookies, and packages automatic public certificate issuance/renewal with persistent certificate state; real-domain reachability/renewal remains unverified. `backend/audit_checkpoint.py` signs a verified chain head; an optional mount-guarded wrapper and systemd timer can schedule daily checkpoints. Offline MFA/privacy-key rotation records fingerprints, writes protected DB backups, and enforces the configured key at startup; MFA rotation also re-encrypts factors, reissues recovery codes and revokes sessions. Report/checkpoint signer rotation supports trusted-key overlap and fingerprint-selected offline verification while preserving prior artifacts. Source/evidence retention is configurable, with guarded cleanup for old releases, receipts and staging files. `docs/INCIDENT_RESPONSE.md` links the containment, restore, key-rotation, audit and source-recovery steps; isolated database-only and managed-data backup/restore drills passed. External footage/custom model restore and key/TLS/off-host incident exercises remain unverified. Independent audit anchoring and non-source retention policies remain pending. |
| OP-05 | Done | Container/Compose setup, database backups and production frontend-to-API routing. | Compose packages a non-root single-worker API and production-built Nginx same-origin frontend behind loopback by default; persistent app data, online integrity-checked SQLite snapshots and explicit stopped-service database restore are implemented. A stop-required full archive covers the database plus managed source releases, uploads, model cache and evidence artifacts with manifest verification and rollback-on-failure restore. Externally mounted footage/custom model files and public-network hardening remain. |
| OP-06 | Partial | Edge model export/quantization and benchmark on actual target hardware. | Reproducible FP32/INT8 ONNX exporter and CPU-host benchmark use hashed CAM-01–06 frames. On this i5-12450H, INT8 median forward latency was 55.782 ms versus 95.309 ms FP32 ONNX; it matched 15/16 FP32 detections at the 0.4 threshold on the same 60 unlabeled calibration frames. No accuracy claim or model promotion; target hardware, held-out labels, recommended ONNX preprocessing and live integration remain. |
| OP-07 | Partial | Canary/model-version pinning, rollback and branch-level disablement. | Frozen dependencies, exact loaded model/config identifiers and branch-disable switches are present. Custom vehicle weights require a SHA-256 pin; a second digest-pinned checkpoint can be assigned to an explicit camera allowlist, copied to immutable hash-named storage, and reported with its exact event model ID. Removing the canary settings and restarting returns those cameras to the stable model. No automatic promotion or measured accuracy gate exists; candidate compatibility and held-out accuracy still need validation. |
| OP-08 | Partial | Operational monitoring and sustained reliability/recovery tests. | Prometheus `/api/metrics` exports bounded per-camera availability, FPS, frame age, queue, retry/failure/overrun counters and recent inference timings without event or identity data; authenticated mode supports administrator sessions or a read-only, route-limited scraper bearer token. An optional loopback-only Prometheus Compose profile scrapes the endpoint and loads API/source/frame/failure alerts; isolated end-to-end authenticated scraping and deterministic alert firing/recovery tests pass. Long-duration live recovery runs and external alert delivery remain. |

## Practical limitations

Real plate cameras are absent, original recording clocks are unknown, and camera
locations/topology have not been independently calibrated. Cross-camera replay
links abstain from physical speed/accepted-flow claims. No held-out accuracy can
be reported. CPU sampling is sparse, not full-frame-rate processing. Counts are
local tracked passages; plate and vehicle association remains unvalidated.

New images are sampled-read JPEG derivatives, not a full original-frame archive. Legacy/manual reads retain explicit coverage gaps. Image write/capacity failures preserve raw reads with missing-image status. The default 2 GiB budget applies to managed image writes, not the database, model cache or videos. Their
seven-day source lifetime is extended by active report leases until report expiry.
Missing/corrupt source images reject report creation; later manual file removal or
corruption makes downloads fail explicitly rather than hiding missing evidence. SQLite reviewer/audit data is local and unauthenticated. Hashes
detect changed bytes and do not prove correctness or authenticated custody.
