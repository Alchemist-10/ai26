# Import recorded footage

AI26 now accepts a recorded clip for an existing camera through an offline local
command. This supplies a managed original and a separate browser playback copy
without editing Python source or overwriting the bundled clips. It does not supply
missing real footage automatically, add cameras, enable RTSP, validate a plate or
calibrate locations/clocks. The browser settings page still edits metadata only;
a source upload/management screen is not implemented.

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

If the camera already has a managed source or configured/bundled footage, use
`--replace` explicitly. Replacement retains prior imported release directories
and leaves configured originals and bundled proxies untouched. Set `--max-bytes`
(default 1 GiB per original/playback) and `--timeout` (default 600 seconds, maximum
3600) for the local workload. Imports require free space for twice the configured
byte allowance plus 16 MiB; this conservative check can be reduced with a smaller
`--max-bytes`. There is no aggregate imported-video budget or automatic cleanup.

## What is validated and preserved

The importer accepts a nonempty regular file within the size bound, a supported
video stream with finite positive duration and average rate, and a catalog camera
ID. It checks supplied operator name/reason, copies with a hard byte bound and
rejects a file whose identity/size/modification time changes during copying. It
probes the staged original actually used by conversion.

Playback is silent H.264/yuv420p MP4, limited to 1280 px width with even dimensions,
CRF 23 / fast preset, one decode/encode/filter thread, and a fast-start index. The
original bytes remain unchanged. Conversion stops on decode/encode errors and is
bounded by time/output size. Probe checks require matching duration within the
stated tolerance and matching frame counts when the original reports a count.
Rate/duration probes are metadata checks; they do not independently establish
constant-rate timestamps or original capture time. Variable-rate/frame-index
accuracy and synchronized clocks remain separate pipeline work.

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

To restore an earlier release while the app is stopped, use its retained
`manifest.json` to restore `active.json`, then restart. Startup verifies the
selected files. Keep a copy of the prior active manifest when performing manual
recovery. The CLI is not a database backup/restore or forensic custody system.
Managed video retention is independent of seven-day sampled JPEG retention and
the 2 GiB JPEG budget. Avoid manually altering active release files.

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
