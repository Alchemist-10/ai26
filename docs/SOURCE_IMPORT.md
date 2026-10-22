# Import recorded footage

Sakshi now accepts a recorded clip for an existing camera through an offline local
command. This supplies a managed original and a separate browser playback copy
without editing Python source or overwriting the bundled clips. It does not supply
missing real footage automatically, add cameras, enable RTSP, validate a plate or
calibrate locations/clocks. The browser settings page now [inspects source status/history](SOURCE_STATUS.md)
and edits metadata. [Browser uploads](SOURCE_UPLOADS.md) prepare inactive releases;
activation still uses the host command and restart.

## Use the command

Install `ffmpeg` with the `libx264` encoder and `ffprobe` on the Linux host. They
are system tools, not Python dependencies. Use the same exported `AI26_DATA_ROOT`
and optional `AI26_SOURCE_ROOT` as the API. Managed sources default to
`<AI26_DATA_ROOT>/sources`; the default data directory is `backend/data`.

From the repository root, inspect a supplied file first:

```bash
uv run --frozen --directory backend python import_source.py CAM-07 "/absolute/path/to/clip.mp4" --check
```

`--check` reports a probe and fingerprint without creating source/data directories,
converting playback or loading models. It does not prove a full decode or OCR.
Stop the running app with Ctrl+C, then import:

```bash
uv run --frozen --directory backend python import_source.py CAM-07 "/absolute/path/to/clip.mp4" \
  --reviewer "Local operator" --reason "Supply the recorded input for this camera"
uv run run.py --skip-install
```

The successful JSON result includes `restart_required: true`. A running processor
in the same data directory blocks import using its existing ownership lock.
Concurrent imports into a source root are also rejected. An API started with
processing disabled can remain open, but it keeps its old bindings until restart.
Using the same source root across different data directories does not hot-switch
those processes either; each must restart to activate the new selection.

When the original recording clock is known, optional `--recording-start-utc
2026-10-14T12:00:00+05:30 --clock-uncertainty-seconds 2.5` arguments retain an
operator claim in the release manifest. The timestamp must include a timezone;
uncertainty is optional and bounded to one day. This claim is unverified and does
not change replay-time analytics or physical cross-camera links.

If the camera already has a managed source or configured/bundled footage, use
`--replace` explicitly. Replacement retains prior imported release directories
and leaves configured originals and bundled proxies untouched. Set `--max-bytes`
(default 1 GiB per original/playback) and `--timeout` (default 600 seconds, maximum
3600) for the local workload. Imports require free space for twice the configured
byte allowance plus 16 MiB; this conservative check can be reduced with a smaller
`--max-bytes`. There is no aggregate imported-video budget or automatic cleanup.

## Prepare without selecting

Add `--prepare` to retain a validated release without modifying `active.json`.
This mode permits the existing processor to continue; it still acquires source
import ownership, validates both files and requires explicit replacement. The JSON
result includes `activation_required: true`. Select from a ready browser preparation or use retained-parent rollback in
[Camera settings](SOURCE_SELECTION.md), then restart on the host. For an arbitrary
CLI-prepared release, with the processor stopped, select using `select_source.py CAMERA RELEASE --expected-current PREVIOUS_OR_default`,
then restart the API. The selector rehashes files and rejects a stale managed
selection; an already selected release is idempotent. This is the same preparation
path used by [browser uploads](SOURCE_UPLOADS.md). Normal import without
`--prepare` retains the original stop/import/restart behavior.

## What is validated and preserved

The importer accepts a nonempty regular file within the size bound, a supported
video stream with finite positive duration and average rate, and a catalog camera
ID. It checks supplied operator name/reason, copies with a hard byte bound and
rejects a file whose identity/size/modification time changes during copying. It
probes the staged original actually used by conversion.

Playback is silent H.264/yuv420p MP4, limited to 1280 px width with even dimensions,
CRF 23 / fast preset, one decode/encode/filter thread, and a fast-start index. The
original bytes remain unchanged. Conversion stops on decode/encode errors and is
bounded by time/output size. The read-only `--check` reports container metadata
without decoding the full clip. Import fully decodes the copied original and
playback derivative to count frames, then requires matching decoded frame counts
and durations within the stated tolerance. This avoids trusting stale container
`nb_frames` values while still rejecting a derivative that lost decoded frames.
For managed replay, the scheduler uses this verified decoded frame count instead
of OpenCV's potentially stale container count when calculating seek positions.
Rate/duration probes are metadata checks; they do not independently establish
original capture time. Sampled source offsets prefer the decoder-reported frame
position in milliseconds and fall back to frame-index ÷ reported FPS; each
observation and image reference records which basis was used. Decoder positions
can still be approximate or absent, and neither basis verifies the camera/NVR
clock. Original capture timestamps and synchronized clocks remain separate
pipeline work.

The recipe uses [FFmpeg's error and frame timestamp options](https://ffmpeg.org/ffmpeg.html),
[ffprobe's video metadata output](https://ffmpeg.org/ffprobe.html) and
[MP4 fast-start indexing](https://ffmpeg.org/ffmpeg-formats.html#mov_002c-mp4_002c-ismv).
The manifest records original/playback SHA-256 and sizes, video properties, the
conversion recipe, inspected FFmpeg version, importer source digest, local reviewer
and reason, and the previous imported release. These local records are
unauthenticated and unsigned. Import does not change camera location metadata;
review that separately in Camera settings before treating a clip as that site.
All processing continues to label the clock as `replay_clock`.

## Publication, activation and failure recovery

Files are prepared in a private staging directory. A complete release directory
is published, then `active.json` is atomically replaced; file/directory writes are
synced. Conversion, validation or pre-publication errors preserve the old pointer
and remove newly staged files. An interrupted return after successful pointer
publication keeps the now-active release. A forced process kill/power failure can
still leave an unreferenced staging/release directory; no automatic deletion is
claimed. Existing releases are not deleted by the importer.

At startup the API loads each managed binding once and checks file identity,
size, SHA-256 and path containment. Invalid explicit bindings fail startup rather
than silently substituting bundled footage. Inference uses that release's original
and native browser playback uses its derivative. File hashing/manifest reads do
not occur during catalog polling or per-frame source selection. Startup hashes
both files, and the processor separately fingerprints its opened original, so
large files add startup I/O.

Browser rollback can select a displayed retained parent for the next restart.
For invalid-pointer or configured-default recovery while the app is stopped, use its retained
`manifest.json` to restore `active.json`, then restart. Startup verifies the
selected files. Keep a copy of the prior active manifest when performing manual
recovery. The CLI is not a database backup/restore or forensic custody system.
Managed video retention is independent of configurable sampled JPEG retention (seven days by default) and
the 2 GiB JPEG budget. Avoid manually altering active release files.

Old, unselected prepared releases can be reviewed with the offline cleanup tool.
It verifies release manifests and media hashes, preserves the selected release's
complete rollback chain (and the prior running release when a restart is pending),
and protects releases referenced by recent receipts or the latest ready receipt
for each camera. It
requires the processor, import/selection and upload locks to be free. It also
reports abandoned `.import-*` and `.upload-*` staging directories older than the
same retention period. Start with a dry run and inspect every candidate:

```sh
uv run --frozen --directory backend python prune_source_releases.py --days 30
```

Only after reviewing the inventory, add `--apply` to remove eligible releases.
The allowed age is 30–365 days. Invalid or linked releases are retained and
reported. The tool removes terminal receipts older than the retention period,
except for the newest receipt for each camera, plus old abandoned staging folders.
It never removes the active rollback chain, source-selection history, newest upload
receipt, configured footage outside the managed source root, or model files.
Cleanup is operator initiated; no background source deletion runs.

## Validation

[Source import validation](validation/source-import-validation.json) records two
real FFmpeg conversions of generated one-second red/blue clips in disposable
storage. Original fingerprints matched the input bytes; playback/range responses
matched the proxy; replacement stayed inactive until API restart; and a no-op
annotation processor decoded the newly selected original with zero observations.
The main app catalog/availability stayed unchanged and fixture data/services were
removed. These are synthetic conversion/activation checks, not real plate-source
reads, detection accuracy or measured sustained throughput.

Fifteen isolated contract tests cover copy/hash roles, read-only checks, explicit
replacement, retained releases, ownership locks, conversion/publication failure,
post-publication interruption, input mutation, invalid metadata/limits, proxy
validation, corrupted/dangling file handling, path escapes and cached bindings.
All 128 backend tests and frontend lint/build pass. After the main app's clean
restart, ten sampled historical observation IDs were retained and six snapshots
decoded. New reads record nine named component digests, including the camera and
managed-source resolver; older read/report provenance remains immutable.

The later [source-inspection milestone](SOURCE_STATUS.md) extends the browser
settings page and brings the isolated backend suite to 140 tests. The 128-test
conversion/import milestone above remains historical evidence. The browser
preparation milestone now has 157 backend tests, including 17 new streaming,
worker and offline-selection contracts; see [SOURCE_UPLOADS.md](SOURCE_UPLOADS.md).
The [browser-selection milestone](SOURCE_SELECTION.md) has 170 backend
tests, including 13 new selection/rollback contracts. Historical counts above
describe their own milestones.

The subsequent [sampling-budget milestone](RUNTIME_PROFILE.md) brought the backend
suite to 182 tests; source-import and selection counts above describe their own
validation snapshots.
