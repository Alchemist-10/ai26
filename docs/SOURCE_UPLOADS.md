# Prepare recorded footage from a browser

Camera settings → Source footage → **Import or replace recorded footage** now
accepts a file from the browser. Preparation preserves original bytes and creates
validated playback in an inactive retained release. Running inference and playback
keep their cached source. **Ready does not mean active.** Selection remains a
host command with the processor stopped, followed by API restart.

## Operator workflow

1. Install FFmpeg/libx264 and ffprobe on the API host. Choose an existing camera,
   a nonempty video up to 128 MiB, your name and a reason. Existing footage requires
   an explicit replacement checkbox. These are local unauthenticated claims;
   review location metadata separately.
2. Choose **Upload and prepare clip**. **Cancel upload** aborts the request.
   After transfer, use **Check preparation** to retrieve progress or **Cancel
   preparation** to stop the owned conversion process. There is no progress timer.
   Camera selection and source/current-revision refresh stay disabled until a
   terminal state is checked; other pages remain usable. Draft fields survive
   internal navigation and source refresh, but not browser reload.
3. At **ready**, follow the camera/release-specific command displayed. Export the
   same `AI26_DATA_ROOT` / `AI26_SOURCE_ROOT` used by the API, stop the app with
   Ctrl+C and run, from the repository root:

   ```bash
   uv run --frozen --directory backend python select_source.py CAM-07 RELEASE_ID --expected-current PREVIOUS_RELEASE_ID_OR_default
   uv run run.py --skip-install
   ```

   Replace the capitalized placeholders with the values shown in settings.
   Selection verifies both file hashes, acquires processor/import ownership and
   rejects a managed release selection changed since preparation. Repeating an
   already selected release is idempotent. `default` means no managed pointer;
   it does not fingerprint changes to configured/bundled default files.
4. Refresh source status after restart. Both original inference and derivative
   playback activate together. The preparation then reports running. Original
   recording clocks, content, site and plate/OCR accuracy remain unverified.

Only the most recent returned job ID per camera is stored in browser localStorage.
Reopening the same camera fetches that receipt once; file/name/reason drafts are
lost on reload. Server terminal receipts survive restart. There is no job browser,
resume of an interrupted transfer, live activation, rollback control, new-camera
creation or RTSP ingestion. An API failure during a check preserves the current
job and offers manual retry. If the transfer response is lost after acceptance,
the browser may not know its ID: inspect host receipts before retrying to avoid
an unnecessary retained duplicate. A stopped API does not resume an unfinished
preparation automatically.

## Bounds and processing behavior

- One upload/preparation per source root, protected in memory and with a process
  ownership lock. Upload body size is enforced while streaming and must exactly
  match declared metadata; optional Content-Length must match too.
- Transfer stream: 120 seconds. Video conversion: 600 seconds, with a 650-second
  worker bound. Original and playback each fit within the 128 MiB allowance;
  the proxy must be strictly below that limit. At reservation, free space must
  cover three allowances plus 16 MiB.
- The raw file is streamed to a private staging file; disk writes run off the API
  event loop. A separately owned Python/FFmpeg process prepares and validates the
  release with one decode/encode/filter thread. This avoids extra ML workers and
  synchronous conversion in the API, but conversion still consumes host CPU/I/O.
  It is not a guarantee of latency on every machine.
- Preparation checks full decode/conversion, matching duration and available
  frame counts, H.264/yuv420p, file bounds, hashes and containment as documented
  in [source import](SOURCE_IMPORT.md). Selection and API startup rehash files.
  Explicit job checks inspect manifest/file presence and size without hashing.
  Same-size post-preparation tampering is caught at selection/startup.
- Temporary uploads are removed after success, failure, cancellation or graceful
  shutdown. Normal cancellation targets only the owned process group. Ready
  releases and terminal receipts remain on disk; in-memory receipt cache is
  bounded to 16. There is **no aggregate managed-video budget or automatic
  video/receipt cleanup**. Forced kill/power loss may leave unreferenced staging.
  Review host files while stopped before any manual cleanup.
- No observations, configuration revisions or SQLite audit rows are created by
  preparation/selection. The manifest records the local reviewer/reason and
  conversion identity. Existing observation provenance is unchanged. Prepared
  releases are unlinked from source history until selected.

## API

`POST /api/cameras/{id}/source/prepare` accepts `application/octet-stream` and
an ASCII base64 UTF-8 JSON `X-AI26-Upload` header containing `filename`, integer
`bytes`, `reviewer`, `reason`, and boolean `replace`. Metadata is limited to 8192
header characters and rejects unknown fields. A successful transfer returns 202
with job ID and status; work can already have reached a terminal state. Unknown
cameras return 404, wrong content type 415, validation errors 422, busy ownership
409, timeout 408 and disconnected upload 400 where a response remains possible.

`GET /api/source-preparations/{job_id}` returns projected filename/status/error,
creation time and a projected ready release. `POST .../{job_id}/cancel` requests
cancellation; check again to confirm the terminal state. Cancelling an already
ready release retains its files. Unknown/invalid IDs return 404. Receipt/manifests
are bounded to 64 KiB. Host absolute paths and arbitrary receipt fields are omitted.

The raw-body route uses [Starlette request streaming](https://starlette.dev/requests/)
and [FastAPI's direct Request interface](https://fastapi.tiangolo.com/advanced/using-request-directly/)
so the application enforces its byte bound rather than buffering a multipart file.
The existing local prototype remains unauthenticated; authenticated source
administration and remote deployment controls are separate work.

## Validation scope

[Upload validation](validation/source-upload-validation.json) records two generated
one-second color clips uploaded through the actual browser and FFmpeg worker.
Original bytes were preserved; unreadable video failed and a readable retry
succeeded; a prepared replacement retained the running/selected first release.
Offline selection was rejected under processor ownership, then selection/restart
activated both roles. A real worker cancellation cleaned private stages. A 502
check recovered after API restart; browser reload restored the retained ready job.
The fixture had zero observations/audit rows and nine seeded camera revisions.
Temporary fixture services/storage were removed; generated footage never entered
the main app.

Seventeen new contract tests cover streaming/cancellation/ownership, receipt write
failure, restart projection, file corruption, stale selection and process bounds.
All 157 backend tests and frontend lint/build pass; two existing Fast Refresh
warnings remain. Desktop 1280×720, requested mobile 390×844 (capture 390×843),
and user 786×758 showed no horizontal overflow, 16px fields and zero videos.
Six idle seconds added zero source/preparation requests. The finish reviewer
returned **ship** at upload-extension scope. These are synthetic workflow checks,
not real plate/OCR accuracy or sustained conversion/inference measurements.
