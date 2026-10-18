# AI26 implementation progress — 16 October 2026

This records the current reliability, tracking, persistence and performance implementation. Accuracy release gates remain open.
The original audit/plan remain the baseline. AI26 alone was changed; the Godseye
SIH source was left intact. The app runs on http://127.0.0.1:5174/.

## Status

Across all 80 planned tasks: **53 done, 27 partial, 0 pending**. Done means the stated engineering behavior works within the documented local prototype scope. It does not imply real OCR/identity accuracy. Partial tasks retain explicit remaining work below.

Student evaluation preparation on 2026-10-18 adds a private 45-frame review set
(five temporal-stratum midpoints from each current camera source), with blank
vehicle counts, optional vehicle/plate boxes, per-plate readability, browser
draft saving, and JSON export/import. Existing 21 plate crop labels remain
untouched. CAM-01–06 samples use available playback copies; CAM-07–09 use their
managed originals. Three synthetic preparation tests and isolated desktop/mobile
browser checks pass. No human counts or new recognition metrics have been
created, and the inspected source clips do not form an independent held-out set.
See [the review workflow](../evaluation/FRAME_REVIEW.md). Evaluation tasks remain
partial until reviewed labels, corresponding predictions, and suitable data exist.

## What now works

Shared background six-camera processing; durable SQLite observations/passages;
per-track OCR abstention; real empty investigations; editable persistent local
rules and review; operator-managed camera-pair travel constraints; truthful camera health/activity; bounded historical query
intents; immediate camera-wall startup without a blocking welcome gate; immutable evidence JSON/ZIP/print; source/derivative hashes; report expiry and artifact leases; cached camera previews;
revisioned camera metadata, settings editor with draft/conflict recovery and queried decision history; CPU lockfile; clean launcher shutdown/restart; regression and evaluation tooling.

## Persistence update

Schema 14 stores user/session records, per-case grants and camera assignments, encrypted TOTP enrollment with replay counters, recovery-code hashes, active escalation case scope, audit context, camera metadata revisions, directed camera-pair travel constraints, immutable queried journey-link decisions, locally hash-chained audit records, and 90-day camera traffic buckets. Non-admin analytics and footage requests are filtered to case-assigned cameras. This is a coarse camera boundary: observations are not individually assigned to cases, so cases sharing a camera can see that camera's observations. The read-only verifier detects changed rows; an operator-run Ed25519 tool signs and checks audit-head checkpoints that must be retained off-host. New observations preserve configuration snapshots; legacy metadata fallback is explicit. Source routes remain fixed, calibration remains unverified, and stored decisions are historical conclusions rather than verified identity.
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
The isolated full backend suite passes 364 tests, including simultaneous TOTP
replay protection, audited admin-only ONVIF profile/clock inspection, and
case-camera-scoped source-job and alert-review regressions; frontend TypeScript build and lint
pass with the repository's two existing Fast Refresh warnings. See
`docs/AUTHENTICATION.md`.

## Optional privacy mode update

Opt-in privacy mode now uses a protected installation key to pseudonymize valid
plate identifiers in analytics responses. Sampled camera views pixelate detected
person boxes, including faces inside those boxes, and detected plate regions;
recognized plate overlay text is pseudonymized, and the API rejects raw recorded
playback while enabled. Database observations and signed evidence remain raw for
authorized review. The browser defaults to sampled detections in this mode.
Integration tests verify person-box masking and keyed plate redaction. Detection
can miss people or plates, intermediate footage frames are not processed, and no
labeled footage has established a false-negative rate. This is best-effort display
masking, not complete anonymization. See `docs/PRIVACY.md`.

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
freeform reviewer names as claims. Authenticated active handoffs are scoped to
the selected case. Active escalations remain visible outside the recent-alert
window, with stable cursor pagination beyond 200 items. The API rejects
escalation without a recipient. Isolated contracts verify target validation,
case scope, stale-window queue visibility, persistence across repository reopen,
pagination, reassignment and resolution. Notifications are conditional in the
task and were not required by the local project scope; external delivery remains
an optional deployment integration. General evidence row-level case isolation
remains tracked separately under OP-02. See `docs/ALERT_REVIEW.md`.

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

## Evidence storage monitoring update — 18 October 2026

Prometheus now exports managed sampled-read image bytes used, configured capacity
and utilization. The optional alert rules warn when utilization remains at or above
90% for two minutes, with deterministic firing/recovery coverage. The current local
runtime measured 2,004,195,098 of 2,147,483,648 bytes used (93.3%). Existing images
were preserved and the configured budget was not changed; some new read images may
therefore be missing until retention cleanup frees space or the operator increases
`AI26_ARTIFACT_MAX_BYTES`. This runtime measurement is specific to the local data
directory and is not a deployment capacity recommendation.

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

- The current branch passes all 354 backend tests with the frozen Python 3.12 CPU environment (verified 2026-10-15).
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

1. Obtain permission and source/export provenance for the locally supplied
   CAM-07–09 candidate clips, verify their original recording clocks, and label
   an independent vehicle/camera/session evaluation set (P0-01/02, EV-01). The
   current clips are active locally and four reviewed readable crops have been
   compared, but source authorization, NVR time verification and held-out labels
   remain open. `docs/FOOTAGE_REQUEST.md` records the location sources, request
   template and intake checklist; no external request has been sent.
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
   backend restart/health-check helper and a Linux systemd service template with
   install, restart and health-check instructions are available; other host
   managers still need their own procedures.
   Metadata settings UI, metadata/link persistence, exact ALPR model provenance and per-read image capture are implemented.
6. Optional research/production phases remain separate. No restored/reconstructed
   pixels, registry verification, authenticated investigator identity, anchored
   audit history, RTSP capture or production access control is represented as done.

## Full checklist

### Correctness and investigation

| ID | Status | Task | Evidence / remaining work |
| --- | --- | --- | --- |
| P0-01 | Partial | Verify source provenance and obtain authorized readable-plate footage, or reduce the catalog honestly to available inputs. | Supplied CAM-07–09 clips were imported, fully decoded (1,285/627/540 frames), selected as active local managed sources and returned successfully by playback range requests. On 2026-10-18, each original byte stream was re-hashed against its member in the supplied ZIP and the active-release manifest; all three matched. The archive digest and per-camera comparisons are in [the integrity report](validation/source-archive-integrity-2026-10-18.json). This establishes byte integrity and local import mapping only. A separate local ZIP/MP4 metadata inspection found timezone-unknown DOS member mtimes, generic `Lavf` muxer tags, no embedded `creation_time` or camera/NVR identifier, and stale CAM-08/09 container frame counts; see [the metadata report](validation/source-media-metadata-2026-10-18.json). Four readable crops have user-transcribed labels, but the sample is too small for validation. Burned-in camera/location and time overlays remain unverified claims. The browser onboarding form now captures optional archive creator, export system, external camera ID, IANA recording timezone, authorization basis and retention terms in the immutable release manifest; the release view labels them as unverified operator claims, and retention notes explicitly do not schedule deletion. Focused source-import/preparation coverage passes (40 tests total) and the frontend production build passes. These fields are not retroactively populated for the current CAM-07–09 release, and source authorization, factual provenance, timezone/clock accuracy, retention approval and independent site verification remain open. The earlier repository/archive search and authorized-footage request template are recorded in [FOOTAGE_REQUEST.md](FOOTAGE_REQUEST.md); no external request has been sent. |
| P0-02 | Partial | Prove real plate reads on supplied footage, retaining raw and canonical strings. | The local evaluator verifies crop hashes and exact source/session/frame/crop references and emits aggregate counts only. It was rerun against the current local database on 2026-10-18 at 06:20 UTC: four readable crop labels produced four stored OCR mismatches, all explicitly rejected by the format gate; 16 were unreadable and one uncertain. An offline probe tested 17 resize, contrast, sharpening, threshold and padding variants on each of the four reviewed readable crops. The grayscale linear-contrast candidate exactly matched CAM-07-02 and passed the existing format and confidence gates when run on its detector crop; the other three crops had no exact candidate. This was not a production read. The exact source-frame detector found an overlapping box on all four samples, but full-frame OCR and OCR on an expanded reviewed region had zero exact matches. A short neighboring-frame check found a target candidate only at the reviewed CAM-07-02 frame, so repeat-read consistency is unproven. The offline probe now also counts format-valid, confidence-at-least-0.35 variants without exposing OCR text: 5 of 68 transformed crop outputs passed these two gates, but 4 were wrong candidates and only 1 was exact; association and repeat-read gates were not tested. This directly rules out promoting the transform on current evidence. Three probe tests, seven review-evaluator tests and 17 focused enhancement/router tests pass. Four selected labels and 68 correlated transformations do not estimate accuracy or false-positive risk. Exact labels remain only in git-ignored local review files under `backend/data/review/`; held-out evaluation remains unavailable. See the [sanitized candidate review](validation/cam07-09-candidate-review-2026-10-16.json), the [reproducible aggregate](validation/ocr-groundtruth-evaluation-2026-10-18.json), and `backend/evaluate_review.py`. |
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
| P1-04 | Done | Preserve source clip/frame timestamp separately from processing time; define cross-camera clock handling. | Source media position and its basis are retained separately from processing time; decoder media time is preferred with explicit frame-index/FPS fallback. Optional timezone-aware recording starts remain operator-claimed/unverified. Replay and live capture-arrival clocks produce unresolved candidate links with null physical speed, never accepted physical journeys. Three source-clock, 17 source-import, and 8 decoder tests pass. Original NVR timestamps and synchronized camera clocks are unavailable and remain field-calibration gates under P1-15/16. |
| P1-05 | Done | Add persistent observations, camera catalog, tracks, links and alert storage with migrations. | Schema-15 migration chain retains reads/local passages/alerts and active escalation case scope, preserves camera history while withdrawing unverified CAM-07–09 default location assertions, seed a revisioned camera catalog and persist directed pair constraints plus immutable queried link decisions with support and algorithm/config snapshots; 90-day camera traffic buckets store live-source samples/passages; audit records are locally hash chained and verifiable; offline source onboarding and metadata editing work; browser source preparation binds the authenticated uploader separately from reviewer claims, persists the attribution across API restart, and supports authenticated selection attribution, bounded selection-history display and retained-parent rollback; activation requires host restart, and authenticated calibration remains separate work. |
| P1-06 | Done | Expose a validated ingestion path rather than relying only on streaming request side effects. | Processor writes through typed validated ingestion rather than request-side streaming effects. No external ingestion API is claimed. |
| P1-07 | Done | Store source-frame and plate-crop references with hashes and model/version metadata. | Every new sampled read attempts its own frame/crop references with exact camera/session/frame/source context, clipped crop bounds, image/model hashes and nine component digests; capture failures/capacity/legacy gaps are explicit. Shared frame encoded once; reports store current-image coverage. Not a full video-frame archive. |
| P1-08 | Done | Test reconnect, corrupt video, end-of-file, missing clips and inference exceptions with bounded retry/backoff. | Controlled reconnect, loop boundary, missing/corrupt input, decode failure and model-download exception tests; 10-second retry and stale-frame suppression. |
| P1-09 | Done | Reset camera and panel errors after input changes or successful recovery. | Camera change/success clears focused-feed failures; API panels clear errors after recovery. Missing-to-available thumbnail remount supported. |
| P1-10 | Done | Return correct HTTP status/error schemas for invalid cameras, plates and request bodies. | Known invalid cameras/missing sources 404; invalid bodies/plates/times 422; unready snapshot 503; JSON error envelope. |
| P1-11 | Done | Add actual health/FPS/frame-age/queue/last-event metrics per camera. | Real per-camera frame age, monotonic FPS, bounded six-phase timings, failed/overrun attempt counters, last read and source/error state; missing/retry cameras do not consume sampling slots. Queue depth zero for the no-queue architecture; health also reports the active recorded-video decoder thread setting. |
| P1-12 | Done | Separate local tracking from cross-camera identity; improve association under occlusion and clip loops. | Motion/box global assignment, ambiguity abstention, elapsed-time expiry and loop/reopen resets are tested; this is heuristic local tracking, with real occlusion/ID accuracy still unmeasured. |
| P1-13 | Done | Deduplicate repeated same-track plate reads and retain corrections without silently overwriting evidence. | Immutable raw reads, deduplicated plate passages and conflict exclusion; uncertain corrections do not silently become supported identity. |
| P1-14 | Partial | Add plate matching confidence and fuzzy matching with measured false-link limits. | Review-only canonical plate edit-distance scores and labeled-pair threshold metrics report denominators plus two-sided Wilson intervals for false-candidate fraction, false-positive rate and recall; interval assumptions are explicit, identity linking is always false. Pair results now distinguish equal observed characters (ignoring separators) from strings that match only after OCR normalization repairs; repaired-equivalent pairs require human review even when canonical strings are identical. Evaluations require unique pair/read IDs, disjoint vehicle/session IDs across rows and labels consistent with the supplied vehicle IDs; they reject reused IDs, cap raw plate text at 64 characters and bound input to 100,000 pairs/100 thresholds. IDs are caller assertions, and camera/location grouping and residual correlation remain unchecked. Scores remain uncalibrated, and operational false-link limits require independently labeled vehicle pairs and held-out recordings. |
| P1-15 | Partial | Use validated camera locations and camera-pair travel constraints for cross-camera links. | Directed, audited min/max travel windows gate new cross-camera links; missing pair data stays unresolved and disabled pairs are rejected. Configuration requires both camera locations marked confirmed with coordinates and is snapshotted with each link. Unconfirmed or incomplete positions now emit null hop coordinates, route distance and implied speed rather than turning display-only placeholders into measurements. CAM-07–09 repository defaults remain unconfirmed because the clip overlay is only a source claim; schema 15 adds a preserved unconfirmed revision when the old default is still current, without changing later operator edits. Independent coordinate validation, road topology and measured travel windows remain absent. |
| P1-16 | Partial | Handle missing cameras, clock skew, conflicting identities and disconnected routes explicitly. | Missing sources, replay/live arrival clocks, conflicting tracks and operator-marked disconnected camera pairs are explicit. Route acceptance now fails closed for manual, missing, legacy or unknown time bases; only the explicit `synchronized_capture_clock` basis can pass the timing gate, and no current runtime source emits it. Live arrival and recorded replay therefore remain unresolved with null physical speed. Calibrated per-camera skew/uncertainty, a verified capture-clock source and independently verified road connectivity remain pending. The supplied CAM-07–09 MP4/ZIP metadata contains no verified recording timestamps, timezone or camera/NVR identifiers; see [the local metadata inspection](validation/source-media-metadata-2026-10-18.json). |
| P1-17 | Done | Add an explicit mock known-plates registry if that is part of course scope, or remove registry-verification wording. | Removed registry-verification wording; no government registry or mock registry is presented as real verification. |
| P1-18 | Done | Make watchlist and restricted-zone data editable and persistent; add permit/history conditions where required. | Operator UI and validated persistent API manage watchlists, active windows, minimum supported sighting counts/lookback, restricted cameras, local permit periods and dwell zones. Rule changes are audited. Matching local permits yield informational visits; missing permits remain review prompts. Permits are not externally verified and the alerts make no legal determination. |
| P1-19 | Done | Add supported plate/camera/type/time intents and clear unsupported-query responses. | Bounded plate/camera/class/time/busiest/alert intents; unknown cameras and unsupported/multiple identities rejected; no fake SQL. |
| P1-20 | Done | Fix timezone/date filters; a today query must not silently mean only the last five minutes. | Timezone-aware today/yesterday/date/time bounds query retained SQL history, not just the default five-minute view. |
| P1-21 | Done | Refresh trajectory results as new observations arrive; debounce typing and clear stale export state. | Submitted searches refresh every three seconds without overlapping requests; typing does not query; changing filters replaces export state. |
| P1-22 | Done | Add a persistent CPU setup/profile and tested restart command; current manual CPU installation must not be replaced by unintended CUDA sync. | Frozen Linux CPU torch/torchvision lock; clean install, restart and launcher process-group shutdown verified. |

### Dashboard and evidence

| ID | Status | Task | Evidence / remaining work |
| --- | --- | --- | --- |
| P2-01 | Partial | Define and compute unique vehicle counts, occupancy/density and any speed metric using suitable calibration. | Stats now returns an explicit `metrics` block: sampled camera-local passage count plus null/`not_measured` globally unique vehicle count, occupancy, road density and physical speed values with reasons. The dashboard labels those values unavailable rather than treating them as zero. Only camera-local passages are computed; cross-camera identity, road/lane geometry, route distance and synchronized clocks remain uncalibrated. |
| P2-02 | Partial | Store historical segment counts/speeds and compare weekday/hour baselines rather than relative detection share. | Schema-11 introduced 90-day 15-minute buckets of successfully processed live-source samples and unique camera-local vehicle passages; schema 13 adds case-scoped active alert escalations. `/api/traffic/baselines` compares the latest completed local hour with covered prior matching weekday/hour counts, excludes replay clocks and requires at least four processed frames across two quarter-hours. Synthetic tests cover local-time alignment, replay exclusion, coverage, deduplication, expiry and baseline math. A 2026-10-18 read-only query confirms all nine currently configured sources return `no_live_history`; the snapshot is recorded in [the baseline API report](validation/traffic-baseline-api-2026-10-18.json). Physical segment counts/speeds, independently calibrated zero-traffic interpretation, qualifying live deployment history and independent route/capture-clock validation remain absent. |
| P2-03 | Done | Implement computed OD aggregation from accepted, deduplicated trajectories and remove fixed live flow rows. | OD counts derive from accepted deduplicated links; fixed sample rows removed. Unsynchronized footage yields no accepted flow. |
| P2-04 | Partial | Implement a measured spatial/road-segment heatmap with honest unobserved/unknown states. | Camera map, analytics and congestion views omit unconfirmed coordinates; missing sources show unknown passage counts, and investigation maps plot only confirmed locations/transitions. A fresh local `/api/cameras` snapshot on 2026-10-18 confirms all nine locations are unconfirmed, so none are eligible for spatial plotting even though numeric placeholders remain in the catalog. See [the location-status snapshot](validation/camera-location-status-2026-10-18.json). CAM-07–09 defaults no longer appear as confirmed based on burned-in overlays; schema 15 preserves old metadata revisions while withdrawing the default assertion. A measured road-segment heatmap still needs independently calibrated coordinates, road/lane geometry and validated passage counts. |
| P2-05 | Done | Keep detector confidence separate from measured accuracy and human verification status. | Model confidence is explicitly separate from measured accuracy and human verification. |
| P2-06 | Done | Persist alert IDs, trigger observations, acknowledgement/review/disposition and reviewer timestamps. | Stable alert IDs, supporting read IDs, review state/history, named reviewer and timestamps persisted across reopen. |
| P2-07 | Done | Connect a real human-review/escalation workflow; add notifications only if required by the project. | Durable local escalation/reassignment queue records recipient, reviewer, note, timestamp and audit history; authenticated mode binds reviewer to the session account and scopes active handoffs to the selected case, while local mode labels freeform names as claims. Stable cursor pages keep active handoffs reachable beyond both the recent-alert window and the first 200 entries. The project scope does not require external notifications; general evidence row-level isolation remains tracked under OP-02. |
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
| EV-01 | Partial | Prepare labeled vehicle/plate data and split by vehicle, camera/location and recording session. | Dataset manifest template and validator verify clip SHA-256, explicit labels/conditions and require disjoint vehicle/camera/location/session splits; manifests can no longer omit a leakage dimension. Synthetic validation covers the fail-closed dimension gate and rejects boolean/float schema-version coercion. No labeled held-out clips have been supplied, so accuracy evaluation remains pending. |
| EV-02 | Partial | Measure vehicle precision/recall and false positives rather than quoting model confidence. | IoU ≥ 0.5 detector precision/recall and false positives use maximum-cardinality one-to-one same-class matching; malformed/non-finite boxes are rejected. Detector metrics now require expected and predicted box arrays as a pair, count explicitly labeled empty/negative frames, expose their sample denominator and reject empty or non-object reports. Synthetic tests cover a greedy-match counterexample and missing ground-truth input. No real labeled measurements or model-accuracy claim; held-out annotations remain required. |
| EV-03 | Partial | Measure exact plate-string accuracy and rejected/invalid read rates on readable and difficult footage. | Added `backend/evaluate_review.py`, which validates each private crop digest, matches persisted output by camera/session/frame/source/crop box, separates missing/inconsistent output, and prints sanitized aggregates only. Seven regression tests cover exact mapping, privacy, unreadable exclusion, crop tampering, repeated-output disagreement and rejection evidence. The aggregate was rerun against the current local database on 2026-10-18 at 06:20 UTC: four readable crop labels, four exact OCR mismatches, all explicitly rejected by the format gate; 16 unreadable and one uncertain. An offline 17-variant audit on those same four crops found five transformed outputs meeting format/confidence gates, four of them inexact; this small correlated probe is not a false-positive rate and no preprocessing change was promoted. This selected sample is not representative; difficult-input strata, false negatives and held-out evaluation remain unavailable. See [the sanitized run](validation/ocr-groundtruth-evaluation-2026-10-18.json). |
| EV-04 | Done | Compare per-track fusion against single-frame OCR; verify it never mixes identities. | A bounded synthetic sequence evaluator compares the last OCR read with per-track consensus and scores review-only character candidates. An interleaved two-track fixture yields one incorrect last-read result while consensus returns one correct result and abstains on the conflict; the character candidate exactly matches one expected plate and abstains on the other, without overriding identity status. The evaluator verifies every supported output came from that same camera/session/track's reads. Four evaluator tests pass, including a deliberately wrong review candidate. This is a synthetic aggregation contract, not a real OCR-accuracy or identity-risk estimate; labeled field evaluation remains data-dependent. |
| EV-05 | Done | Measure tracker ID switches, fragmentation and passage-count error. | The two-frame synthetic report records one ID switch and +1 passage error; a separate known-track sequence verifies one fragmentation after visible loss/reacquisition. All 16 tracker tests pass, including camera/session/frame-order safeguards. This closes synthetic metric behavior only; field rates remain data-dependent. |
| EV-06 | Done | Measure accepted/rejected trajectory-link precision and impossible-travel false alerts. | The synthetic link fixture reports TP=1, FP=1, FN=0 (precision 0.5, recall 1.0); a deterministic impossible-travel case is rejected with an explicit reason while a reachable pair is accepted. Sixty reliability tests and eight backend contract tests pass. These are synthetic checks, not real false-alert estimates; calibrated route validation remains pending. |
| EV-07 | Done | Evaluate loitering/restricted-zone/watchlist rules with both positive and negative cases. | Synthetic positive/negative cases cover elapsed dwell versus zone exit/gap, active and expired watchlist history, and local permitted versus unpermitted restricted-zone visits. Sixty reliability tests pass. This verifies rule behavior only; footage-level precision/recall remains data-dependent. |
| EV-08 | Done | Validate derived traffic metrics against independent counts or known synthetic ground truth. | Synthetic fixtures encode exact live passage totals and expected same-weekday/hour baselines; tests verify the derived count and median, suppress incomplete-hour results, and exclude replay observations. Six targeted tests pass. This closes the synthetic-ground-truth validation requirement only; independent real traffic counts, speed, and density calibration remain pending under P2-01 and field validation. |
| EV-09 | Partial | Benchmark warm/cold inference latency, sustained multi-stream throughput, dropped frames and memory. | Bounded timings, read-only CPU/RSS/counter profiling, verified forward decode, and browser-local native-player dropped-frame accounting are implemented. The camera wall now memoizes card state to skip renders when five-second health polls change only off-card metrics, and it defers preview polling for tiles outside the viewport. A local nine-camera ETag probe found 7/9 previews unchanged after 3 seconds and 4/9 unchanged after 5 seconds while all sources were processing; visible preview polling is now 5 seconds instead of 3, reducing request frequency by 40% near the 4.5-second average per-camera scheduling interval. See [the poll-cadence probe](validation/preview-poll-cadence-2026-10-18.json). This measures API frame freshness, not browser paint savings. An earlier 918×870 browser capture was taken with processing paused and playback media unloaded, so active-inference preview savings were not measurable in that sample. Five local `/api/cameras` checks returned 11,499 bytes in 7.4–9.4 ms; that is API response time, not interaction latency. Two 10-second desktop samples of one recorded stream measured 1.20% and 1.38% incremental dropped frames with processing disabled; six-camera runtime samples, 144 same-frame decoder checks, and an isolated 120-second replay soak are also recorded. Paired 2026-10-16 decode-only runs measured 72 CAM-01 samples at 50-frame gaps and 32 samples per method on each of six proxies at 75-frame gaps. At 75-frame spacing, forward decode medians were 20.0–30.3 ms versus 65.7–73.0 ms for seek/read; all 192 frames matched hashes and decoder positions. This does not reproduce six concurrent decoders plus inference. The bounded ALPR profiler measured 1.708 s base imports, 559 ms for ALPR initialization plus synthetic preflight from the already-warm model cache, 53.2/63.9 ms median/p95 full predictions on 12 CAM-01 frames (zero plate detections), and 7.0/7.5 ms median/p95 for synthetic OCR crops; it records no OCR text. The 2026-10-16 isolated active-inference profile completed 31 frames over a valid 19-second window (1.63 FPS against a two-FPS budget); the first CAM-01 inference took 4.42 s, warm per-camera inference medians were about 82–99 ms, median RSS was 548.9 MiB, and CPU p95 briefly reached 468.4% across 12 logical CPUs. The detector/OCR wrappers pass synthetic output-contract checks, but ONNX Runtime lenient shape-merge warnings and positive detector behavior remain unverified. This does not measure OCR on a real plate crop or browser playback under this run. The warmed follow-up completed 38 frames in 19.006 seconds (1.999 FPS), with no failures or overruns in the measured window; the first CAM-01 attempt took 4.90 seconds and exceeded the interval once. CPU p95 was 102.1%, and RSS p95 of 548.8 MiB; one Analytics click-plus-accessibility-capture observation took 566 ms with the route content present. This single action sample is not INP or click-to-paint. A further 2026-10-16 nine-source active-inference profile completed 229 frames over a verified 119.005-second window (1.9243 FPS); all sources remained available, with zero failed attempts or health-read failures. CAM-07/08/09 had 7/12/7 cumulative budget overruns during the interval; CPU p95 was 225.7% and RSS p95 788.1 MiB. See [the nine-camera profile](validation/active-inference-profile-9cams-2026-10-16-120s.json) and [evaluation register](EVALUATION_REGISTER.md). A further 2026-10-16 nine-source active-inference profile completed 229 frames over a verified 119.005-second window (1.9243 FPS); all sources remained available, with zero failed attempts or health-read failures. CAM-07/08/09 had 7/12/7 cumulative budget overruns during the interval; CPU p95 was 225.7% and RSS p95 788.1 MiB. See [the nine-camera profile](validation/active-inference-profile-9cams-2026-10-16-120s.json) and [evaluation register](EVALUATION_REGISTER.md). Longer sustained load and cold-download startup remain pending. 2026-10-18 isolated headless Chromium active-inference samples at desktop and 390×844 mobile-sized viewports measured LCP 1,100/708 ms, CLS 0.0012/0, and camera-filter action-to-DOM p95 122/198 ms; 9 preview images loaded and no video was requested. Sparse Event Timing p95 was 64/72 ms, not a production INP result; the mobile document had no horizontal overflow. See [the browser samples](validation/browser-active-inference-ui-2026-10-18.json). That headless sample selected no video view; a paired 30-second in-app CAM-07 playback check on the same 572×758 camera wall recorded 36/865 dropped frames (4.16%) with inference active versus 21/850 (2.47%) with processing disabled. Both runs served the exact active-manifest playback hash. This is one uncontrolled local comparison; processing-off also replaced active preview images with paused placeholders, so it does not isolate inference as the cause. The app was restarted with all nine cameras processing and the user view was restored unloaded; see [the playback pair](validation/browser-playback-active-inference-2026-10-18.json). A 2026-10-16 active-inference smoke test on all nine available sources completed 37 frames over a 19-second verified counter window at 1.9996 FPS; process CPU p95 was 202.5% across 12 logical CPUs and RSS p95 was 770.5 MiB. CAM-07–09 each completed 13 frames without attempt failures after replay scheduling was changed to use import-verified decoded counts. Two format-valid unreviewed OCR outputs occurred on CAM-09; no exact-read accuracy is claimed. See [the smoke-test evidence](validation/cam07-09-inference-smoke-2026-10-16.json). A corrected 119.007-second nine-source run on 2026-10-18 measured 138 completed frames (1.1596 FPS against the 2 FPS budget), zero failed attempts/health reads, CPU p95 205.2% and RSS p95 773.8 MiB. CAM-07/08/09 produced 15/15/16 budget overruns; decoder medians were 1.09/1.66/1.22 seconds. The profile is a valid steady-state counter window after the profiler was fixed to ignore normal frame-age resets when frame counters advance. Live capture, browser interaction/dropped frames and long multi-hour reliability remain. A paired decode-only diagnostic on actual 1080p CAM-07–09 originals verified every tested pixel hash at 120/180/200/220-frame gaps; forward decode won consistently on CAM-07/09, while CAM-08 seeks were faster at 200/220. A source-hash-scoped 221-grab limit now applies only to the exact tested CAM-07/09 originals; CAM-08 and changed sources retain the 128-grab cap, and explicit global overrides remain authoritative. Ten decoder tests cover the measured 220-frame gap and fallback. A post-restart production `Processor.decode_frame` check confirmed CAM-07/09 choose 221 grabs and CAM-08 seeks at a 220-frame gap; all three pixel hashes and decoder positions matched seek/read (see [production policy check](validation/decode-production-policy-cam07-09-2026-10-18.json)). The 58-second nine-source follow-up completed 112 frames (1.9309 FPS), with no failures and three CAM-08 budget overruns, but its largest observed gap was 112 grabs and it did not exercise the >128 policy; no FPS gain is attributed to that bound (see [source-tuned profile](validation/active-inference-profile-9cams-2026-10-18-source-tuned-60s.json)). The recorded decoder now defaults to two FFmpeg threads (bounded 1–4); the following valid 119.010-second run completed 163 frames at 1.3696 FPS versus 138 at 1.1596 FPS with one thread, with CPU p95 rising from 205.2% to 256.8% across 12 logical CPUs and RSS p95 from 773.8 to 809.7 MiB. Plate-camera decode p50 improved to 0.51/0.71/0.75 seconds. Throughput remains below budget and this is not a controlled workload or browser latency test; see the [profile](validation/active-inference-profile-9cams-2026-10-18-2decode-threads.json).  A full-system four-thread repeat fell to 1.2772 FPS and raised CPU p95/RSS p95 to 326.0%/907.6 MiB, so the running app was restored to two threads. Among the tested bounded settings, two threads delivered the highest observed full-system throughput; these are adjacent local runs under uncontrolled load, not a universal tuning result; see the [four-thread profile](validation/active-inference-profile-9cams-2026-10-18-4decode-threads.json). A 300-second all-source replay profile verified 298.011 seconds of counters and 149 health samples: 349 frames (1.1711 FPS vs 2 FPS), zero failed attempts or health failures, all nine sources processing at both ends, CPU p95 226.9%, RSS p95 851.5 MiB, and no profile-quality anomalies. CAM-07/08/09 exceeded their 0.5-second budget on 36/38, 37/38 and 39/39 attempts. This is sustained local replay evidence only; live capture, browser playback drops and multi-hour recovery remain unmeasured. See [the five-minute profile](validation/active-inference-profile-9cams-2026-10-18-300s.json). |
| EV-10 | Done | Test page changes, multiple clients, restart, idle expiry, duplicate events, bad input and model-download failure. | Isolated tests cover multiple consumers, restart, idle expiry, duplicates, invalid input, corrupt capture, replay boundaries and simulated model-download failure; live launcher restart verified. |
| EV-11 | Done | Record sample sizes, hardware, conditions and failure cases; do not infer accuracy from the current smoke tests. | [Evaluation register](EVALUATION_REGISTER.md) indexes sample counts, host/settings, observed failures and limits for the major synthetic, browser, runtime, decoder, ALPR and edge evidence files. It explicitly distinguishes agreement from accuracy and records that no held-out labeled evaluation is available. Real failure strata remain data-dependent under EV-01–03/05–07. |
| EV-12 | Done | Add CI for regression/build checks and a reproducible evaluation command. | Pinned-action CPU/backend/frontend CI workflow and reproducible evaluation CLI; local equivalent checks pass. Remote result recorded separately. |

### Optional research

| ID | Status | Task | Evidence / remaining work |
| --- | --- | --- | --- |
| RS-01 | Partial | Rule-based scene/plate quality and weather router with an unchanged raw-reference branch. | Offline reports separate whole-scene hints from optional operator-supplied or explicitly requested hash-snapshotted ALPR detector boxes and suggested OCR preprocessing candidates; OCR text is discarded, `raw` remains first, regions are bounds-checked, zero-sized and malformed images reject with a clear validation error, pixels are unchanged, and existing reports are atomically protected from replacement. Low-light/low-contrast regions now also suggest the explicit grayscale-contrast derivative; this remains review-only. Tests cover crop isolation, detector metadata, no-candidate results, invalid image/box inputs, raw preservation and no-clobber CLI behavior (10 focused tests pass). Threshold calibration, verified weather/readability classification, and held-out validation remain pending. |
| RS-02 | Done | Classical CLAHE/gamma/white-balance/Retinex/dark-channel enhancement and restrained sharpening. | Offline CLAHE, gamma, gray-world, single-scale Retinex, dark-channel dehazing, unsharp masking, and a pinned grayscale linear-contrast transform write hashed research derivatives without replacing source images. The latter exactly recovered one user-reviewed read in an exploratory four-crop probe, but not the other three and not consistently on adjacent frames; it remains an offline candidate, not a production OCR path. Synthetic correctness tests pass; OCR benefit and safety require held-out labeled footage. |
| RS-03 | Partial | Per-track best-shot/top-k frame selection and OCR character-level consensus. | Per-read crop statistics now produce top-three review candidates per local passage in version-4 reports and a capped Timeline preview. Conflicting reads expose review-only character-vote suggestions with per-position weighted shares, margins and abstention reasons; a synthetic evaluator now scores exact, incorrect and abstained suggestions without promoting them. Weights are explicitly uncalibrated, raw conflicts remain unresolved and all raw reads/images remain. Ranking and OCR fusion still need calibration and labeled validation. |
| RS-04 | Partial | Frame alignment/optical flow, probabilistic fusion and calibrated plate confidence. | Offline Farneback alignment for bounded same-camera image bursts with forward/backward consistency diagnostics and synthetic translation tests. It is not integrated with OCR; probabilistic fusion, calibrated plate confidence and held-out footage evaluation remain pending. |
| RS-05 | Partial | Collect adverse-weather data and build a controlled degradation generator. | Offline deterministic rain, fog, low-light, motion-blur and sensor-noise derivatives support no-clobber PNGs and bounded MP4 sequences with source/output hashes, seed and explicit synthetic-only labels. Real adverse-weather clips, held-out labels and OCR robustness measurements remain pending; synthetic temporal effects are not observed weather. |
| RS-06 | Partial | Train/evaluate a quality classifier, dehazing and deblurring models, and Indian-plate OCR adaptation. | Added a supervised readability-classifier trainer with crop/source hashes, camera/session/source-clip disjoint splits, validation-only regularization selection and held-out per-class metrics. Synthetic fixtures validate the trainer but no reviewed crop dataset exists, so there is no real model metric. Classical dark-channel dehazing/unsharp candidates exist separately; learned restoration models, paired restoration labels and Indian-plate OCR adaptation remain unimplemented pending field data. |
| RS-07 | Partial | Add restoration safety checks and preserve raw versus enhanced/reconstructed artifact provenance. | Offline enhancement derivatives carry method/parameter metadata and hashes while source hashes/status remain explicit and outputs never overwrite files; live restoration/reconstruction integration, OCR safety tests on labeled footage and deployment provenance remain. |
| RS-08 | Partial | Optional burst super-resolution with an explicit reconstructed status, not a raw-evidence claim. | Offline 2× phase-correlation/shift-and-add utility accepts bounded same-camera bursts, rejects weak registration or missing subpixel diversity, and writes no-clobber PNG derivatives with source/output hashes and explicit `reconstructed` status. Synthetic tests cover bounds, plumbing and provenance; real burst quality, motion/occlusion handling and OCR benefit remain unmeasured. |
| RS-09 | Partial | Learned camera topology and calibrated travel-time distributions. | Offline trainer estimates directed edge windows from positive training sessions and reports held-out precision/recall/false-accept denominators on session-disjoint positive/negative candidates. Both the JSONL loader and direct fitting API now validate bounded row counts, identifiers, labels, elapsed times, duplicate IDs/samples, session splits and calibration declarations, so callers cannot bypass the input gate. Tests are synthetic; declarations, labels and route coverage are not independently verified. Output is review-only and never writes production constraints. |
| RS-10 | Partial | Complete raw/classical/learned/fusion ablations and model cards with data lineage. | Paired ablation runner enforces identical manifest-hashed test samples, exact labels, per-variant configuration/weight provenance and reports deltas against raw. The current configured vehicle/ALPR bundle has a digest-pinned descriptor and filled model card with upstream OCR lineage, runtime observations and explicit unknown training splits, unverified weight licenses, missing labels and no accuracy claim. A validator checks report/bundle/checkpoint/source hashes and rejects repository path escapes. No complete labeled dataset or real four-way ablation is available, so no best-variant claim is made. |

### Optional production and edge

| ID | Status | Task | Evidence / remaining work |
| --- | --- | --- | --- |
| OP-01 | Partial | RTSP/ONVIF camera integration and resilient capture queues. | Optional protected JSON mapping configures RTSP/RTSPS for existing cameras. Dedicated readers use bounded open/read timeouts, one-frame buffers, freshness checks and reconnect backoff; live frames use the normal inference/event/preview pipeline and capture-arrival timestamps. Fake-capture tests cover private config and reader behavior. Admin-only WS-Discovery lists local devices; a read-only profile action now queries capabilities, media profiles, stream URIs and device time with transient PasswordDigest credentials, strict same-device private-IP checks, URL redaction and a clock-offset estimate that explicitly does not assess AI26 host clock accuracy. Actual camera/NVR authentication/interoperability, source setup, camera-clock synchronization and live failover on hardware remain unverified. |
| OP-02 | Partial | Authentication, role-based access and purpose/case-scoped sensitive operations. | Optional auth includes sessions, roles, CSRF, case/purpose audit, per-account grants, administrator-managed case-to-camera assignments, and camera-scoped camera catalogs, direct footage, source-preparation status/cancellation, observations, statistics, traffic baselines, route links, trajectories, evidence reports, alert queries and alert-review mutations. Case camera scopes apply in SQL for data queries; out-of-scope direct camera requests, source jobs and review mutations are denied. Detailed per-camera health is admin-only when auth is enabled; `/healthz` exposes only minimal liveness. Active escalations and report/package/print/artifact reads remain case-bound. MFA uses encrypted TOTP secrets and one-use recovery codes; password recovery/change/reset flows are audited, and account access changes revoke sessions. Auth remains opt-in. Camera assignment is a coarse case boundary rather than per-row case ownership; legacy alerts without camera IDs remain admin-visible, while rule editing is admin-only because rule storage is global. External identity and independent identity proofing for help-desk resets remain pending. |
| OP-03 | Done | Occupant face blurring and keyed plate pseudonyms in analytics views if those privacy features remain in scope. | Opt-in keyed plate pseudonyms apply to analytics responses and overlays; sampled views pixelate detected person regions, covering faces inside those boxes, plus detected plate regions. Raw playback is blocked in privacy mode while evidence remains raw for authorized review. Regression tests cover person-mask integration and response redaction. Coverage remains best-effort: model misses and unsampled frames can expose pixels, and no labeled field validation measures masking recall. This is not complete anonymization. |
| OP-04 | Partial | Durable audit logs, retention jobs, secrets handling and TLS. | Local SQLite audit chain detects row/link edits; optional TLS 1.2/1.3, authentication/MFA and Ed25519 report-signing overlays use host-managed secrets/keys. A Caddy overlay now requires authentication, enables Secure cookies, and packages automatic public certificate issuance/renewal with persistent certificate state; real-domain reachability/renewal remains unverified. `backend/audit_checkpoint.py` signs a verified chain head; an optional mount-guarded wrapper and systemd timer can schedule daily checkpoints. Offline MFA/privacy-key rotation records fingerprints, writes protected DB backups, and enforces the configured key at startup; MFA rotation also re-encrypts factors, reissues recovery codes and revokes sessions. Report/checkpoint signer rotation supports trusted-key overlap and fingerprint-selected offline verification while preserving prior artifacts. Source retention plus configurable observation, aggregate-traffic and report windows now have bounds and cleanup tests; see `docs/RETENTION_POLICY.md`. The append-only audit ledger is intentionally retained indefinitely until a signed archive/pruning policy is designed. `docs/INCIDENT_RESPONSE.md` links containment, restore, key rotation, audit and source recovery; isolated database-only and managed-data backup/restore drills passed. External footage/custom model restore and key/TLS/off-host incident exercises remain unverified. Independent audit anchoring, audit retention approval and off-host incident exercises remain pending. |
| OP-05 | Done | Container/Compose setup, database backups and production frontend-to-API routing. | Compose packages a non-root single-worker API and production-built Nginx same-origin frontend behind loopback by default; persistent app data, online integrity-checked SQLite snapshots and explicit stopped-service database restore are implemented. A stop-required full archive covers the database plus managed source releases, uploads, model cache and evidence artifacts with manifest verification and rollback-on-failure restore. Externally mounted footage/custom model files and public-network hardening remain. |
| OP-06 | Partial | Edge model export/quantization and benchmark on actual target hardware. | Reproducible FP32/INT8 ONNX exporter and CPU-host benchmark use hashed CAM-01–06 frames. On this i5-12450H, INT8 median forward latency was 55.782 ms versus 95.309 ms FP32 ONNX; it matched 15/16 FP32 detections at the 0.4 threshold on the same 60 unlabeled calibration frames. No accuracy claim or model promotion; target hardware, held-out labels, recommended ONNX preprocessing and live integration remain. |
| OP-07 | Partial | Canary/model-version pinning, rollback and branch-level disablement. | Frozen dependencies, exact loaded model/config identifiers and branch-disable switches are present. Custom vehicle weights require a SHA-256 pin; a second digest-pinned checkpoint can be assigned to an explicit camera allowlist, copied to immutable hash-named storage, and reported with its exact event model ID. First use fails closed on a wrong detection task/class map or invalid 640×640 synthetic forward result. The plate detector/OCR pipeline likewise fails closed on invalid synthetic output contracts. A new offline gate checks paired stable/candidate reports against a ready disjoint held-out manifest, exact model and sample-set hashes, operator-supplied precision/recall/exact-read floors and non-inferiority limits. It never promotes automatically. Removing canary settings and restarting returns cameras to the stable model. No approved thresholds or reviewed held-out labels are available, so no real model has passed the gate and positive plate detection remains unverified. See `evaluation/PROMOTION_GATE.md`. |
| OP-08 | Partial | Operational monitoring and sustained reliability/recovery tests. | Public health and camera-catalog endpoints report configured source availability separately from processor state, including while processing is paused. Prometheus `/api/metrics` exports bounded per-camera availability, FPS, frame age, queue, retry/failure/overrun counters and recent inference timings without event or identity data; authenticated mode supports administrator sessions or a read-only, route-limited scraper bearer token. An optional loopback-only Prometheus Compose profile scrapes the endpoint and loads API/source/frame/failure alerts; isolated end-to-end authenticated scraping and deterministic alert firing/recovery tests pass. Long-duration live recovery runs and external alert delivery remain. A 119-second all-source replay profile recorded zero inference failures or health-read failures, but replay performance was 1.16 FPS against the 2 FPS budget and the plate cameras repeatedly exceeded their sampling interval. This is bounded replay evidence, not a live recovery or long-duration reliability test; see the [profile](validation/active-inference-profile-9cams-2026-10-18.json). A repeated 119-second all-source run with bounded two-thread recorded decoding completed 163 frames (1.37 FPS), zero inference/health failures and higher CPU/RSS; plate cameras still exceeded the sampling interval 18 times each. This improvement does not establish live recovery, browser responsiveness or long-duration reliability; see the [profile](validation/active-inference-profile-9cams-2026-10-18-2decode-threads.json).  A bounded four-thread replay repeat underperformed the two-thread run (1.28 vs 1.37 FPS) while raising CPU p95/RSS p95 to 326%/908 MiB; the local app is back on two threads. 2026-10-18 isolated headless Chromium runs under the active nine-source inference process measured desktop/mobile-sized LCP 1,100/708 ms and CLS 0.0012/0. Twelve camera-filter action-to-DOM updates took 61–122 ms on desktop and 95–198 ms on the 390×844 viewport; nine preview images loaded, no video was requested, and the mobile document had no horizontal overflow. Sparse Event Timing p95 was 64/72 ms, not a production INP estimate. See [the browser sample](validation/browser-active-inference-ui-2026-10-18.json). Long-duration live recovery and playback frame-drop measurements remain pending; see the [four-thread profile](validation/active-inference-profile-9cams-2026-10-18-4decode-threads.json). A 300-second nine-source replay repeat completed a verified 298.011-second window with 349 frames (1.1711 FPS), no failed processing or health reads and no profiler anomalies; all sources were processing at both ends. CPU p95/RSS p95 were 226.9%/851.5 MiB, and CAM-07/08/09 overran 36/38, 37/38 and 39/39 attempts. This strengthens bounded replay reliability evidence, but does not establish live recovery, browser frame drops, external alert delivery or multi-hour uptime. See [the five-minute profile](validation/active-inference-profile-9cams-2026-10-18-300s.json). |

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
