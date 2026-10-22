# Prepare recorded footage from a browser

Camera settings → Source footage → **Import or replace recorded footage** now
accepts a file from the browser. Preparation preserves original bytes and creates
validated playback in an inactive retained release. Running inference and playback
keep their cached source. **Ready does not mean active.** Select a ready release in settings, then restart
the app on the host. An offline host selector is also available.

## Operator workflow

1. Install FFmpeg/libx264 and ffprobe on the API host. Choose an existing camera,
   a nonempty video up to 128 MiB, your name and a reason. The optional original
   recording start and clock uncertainty are retained as operator claims, not
   verified timestamps. Existing footage requires an explicit replacement checkbox.
   These are local unauthenticated claims; review location metadata separately.
2. Choose **Upload and prepare clip**. **Cancel upload** aborts the request.
   After transfer, use **Check preparation** to retrieve progress or **Cancel
   preparation** to stop the owned conversion process. There is no progress timer.
   Camera selection and source/current-revision refresh stay disabled until a
   terminal state is checked; other pages remain usable. Draft fields survive
   internal navigation and source refresh, but not browser reload.
3. At **ready**, enter the selection reviewer and reason, then choose **Select
   for restart**. Both files are rehashed and the displayed selection token must
   still match. A stale or unconfirmed request preserves the entries and requires
   **Refresh source status** before another explicit attempt. For the local
   launcher, stop the app with Ctrl+C on the host, then run
   `uv run run.py --skip-install` using the same exported `AI26_DATA_ROOT` /
   `AI26_SOURCE_ROOT`. For Docker Compose, run `ops/restart-backend.sh` from the
   deployment directory and refresh source status after its health check passes.
   See [SOURCE_SELECTION.md](SOURCE_SELECTION.md).

   **Select with a host command instead** retains the offline path:

   ```bash
   uv run --frozen --directory backend python select_source.py CAM-07 RELEASE_ID --expected-current PREVIOUS_RELEASE_ID_OR_default
   uv run run.py --skip-install
   ```

   Stop the processor first. Replace placeholders with the values shown in settings.
   This CLI checks the expected release ID, not the browser's metadata token, and
   does not create browser selection records. `default` means no managed pointer;
   it does not fingerprint configured/bundled files.
4. Refresh source status after restart. Both original inference and derivative
   playback activate together. The preparation then reports running. Original
   recording clocks, content, site and plate/OCR accuracy remain unverified. An
   optional clock claim is retained with an approximate frame-index/reported-FPS
   offset but excluded from replay-time trajectories and cross-camera speed decisions.

Only the most recent returned job ID per camera is stored in browser localStorage.
Reopening the same camera fetches that receipt once; file/name/reason drafts are
lost on reload. Server terminal receipts survive restart. There is no job browser,
resume of an interrupted transfer, live activation, new-camera
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
  bounded to 16. There is no automatic managed-video or receipt cleanup. The
  offline `prune_source_releases.py` command can remove old, verified, unselected
  releases, aged terminal receipts and abandoned `.upload-*`/`.import-*` staging
  after dry-run review. It preserves the latest receipt per camera. Forced
  kill/power loss may leave staging until that operator cleanup is run.
- No observations, configuration revisions or SQLite audit rows are created by
  preparation/selection. The manifest records the reviewer/reason claim and
  conversion identity. When authentication is enabled, the API separately binds
  the verified uploader account to the prepared manifest; this does not convert
  the reviewer, location or recording-clock fields into verified claims.
  Existing observation provenance is unchanged. Prepared
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
The default local prototype remains unauthenticated. When authentication is
enabled, source routes require an operator role, case/purpose scope and CSRF on
mutations. The upload's reviewer/reason fields remain operator-entered claims;
prepared releases bind the signed-in uploader account on the server, and source
selection records separately bind the account selecting a release. A ready
browser receipt and the later source history display the reviewer claim and
authenticated uploader as separate fields. The
Compose helper restarts only the backend and waits for its local health endpoint;
other deployment managers still need their own restart procedure.

## Validation scope

[Upload validation](validation/source-upload-validation.json) records two generated
one-second color clips uploaded through the actual browser and FFmpeg worker.
Original bytes were preserved; unreadable video failed and a readable retry
succeeded; a prepared replacement retained the running/selected first release.
Offline selection was rejected under processor ownership, then selection/restart
activated both roles. A real worker cancellation cleaned private stages. A 502
check recovered after API restart; browser reload restored the retained ready job.
The fixture had zero observations/audit rows and seeded camera revisions.
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

The later [source-selection milestone](SOURCE_SELECTION.md) adds browser selection
and retained-parent rollback. Its suite has 170 tests; the 157-test figures above
remain the preparation milestone's historical evidence.
