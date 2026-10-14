# AI26 performance and retention update — 9 October 2026

The wall previously mounted a native MP4 for each camera plus a low-rate focused
MJPEG stream. The available inputs are six 960×540, 25 FPS recordings; three plate
sources are missing. Nine video elements were observed before missing-source
errors settled. Actual concurrent decode work depended on source availability.
The focused MJPEG updates at the inference sampling rate, about 0.2 FPS per source,
so apparent video stutter was also a sampling limitation.

The wall now mounts six cached 320×180 JPEG previews and one focused native player.
Recorded playback and sampled detections are separate controls with explicit labels.
Inference still processes independently of viewers. Hidden pages stop serial polls,
abort pending reads, pause native playback, and remove the MJPEG consumer. Returning
refreshes the data. The log requests its last 40 rows rather than downloading every
read in the window. Analytics/activity reuse the root catalog request.

## Local measurements

These were 12 sequential HTTP reads per endpoint on the same desktop while the
main processor was active. CPU and RSS are short process samples (3.31 seconds
before, 3.37 seconds after), with no fixed replay-frame alignment or controlled
background load. They are observations, not sustained throughput guarantees.
CPU percentages can exceed 100% because multiple logical cores are used.

| Measure | Before | After |
| --- | ---: | ---: |
| Backend CPU, short sample | 123.1% | 64.2% |
| Backend RSS | 733.3 MiB | 545.5 MiB |
| Camera catalog median response | 2.68 ms | 2.35 ms |
| Stats median response | 2.05 ms | 1.60 ms |
| CAM-05 full-window reads, median | 10.56 ms | 8.82 ms |
| CAM-05 reads downloaded by log | 99,323 bytes (full window) | 62,177 bytes (40 rows) |
| CAM-05 full annotated snapshot after change | — | 170,564 bytes |
| CAM-05 cached preview after change | — | 12,963 bytes |

The preview/snapshot comparison shows the new smaller image representation; it
is not a measured before/after total MP4 network-byte comparison. CUA confirmed
one playing native video, six decoded 320×180 previews and no horizontal overflow
on desktop and at 390×844. Switching to detections removes the native video;
missing-source selection and recovery work, analytics mounts no video, and an
unknown plate still shows an empty result with export disabled.

A separate warm YOLO test used the same CAM-05 decoded frame, 12 samples per
thread count, under the existing desktop load. Medians: 8 threads 319.4 ms;
1 thread 135.4 ms; 2 threads 77.1 ms. The default now uses two Torch intra-op
threads and one FFmpeg decoder thread per source. Ultralytics resets its thread
count during initial predictor setup, so the application restores the configured
budget afterward. The first prediction may still use the library's setup default.
This test does not validate detector accuracy or ALPR performance.

## Evidence retention

Schema version 2 migrates existing report artifact leases. A maintenance thread
runs every minute even with inference disabled. Seven-day source cleanup respects
active report leases, keeping referenced images until their report expires after
24 hours. Creation verifies source images under the repository cleanup lock and
rejects missing/corrupt images. Hash checks cannot restore files removed manually.
Tests exercise migration, source-age/report-expiry boundaries, processing-disabled
maintenance, preview ETags/stale responses, async consumer cancellation, and missing
source rejection. All 55 backend tests pass; frontend build and lint pass (two
existing shared-component Fast Refresh warnings).

## Limits and next measurements

INP/LCP/CLS, dropped playback frames, browser CPU, low-end physical mobile devices,
network throttling, sustained decode/inference latency and real OCR accuracy were
not measured. Sparse shared inference remains visible and is not full-rate video.
Readable CAM-07–09 footage, original recording clocks and held-out labels are still
needed to validate the plate pipeline and cross-camera journeys.

Evidence files are under `docs/validation/`: performance-before.json,
performance-after.json, cpu-thread-benchmark.json, browser-performance.json and
runtime-smoke.json. The local deliverable also contains desktop/mobile screenshots.

Implementation references: [React effect cleanup](https://react.dev/reference/react/useEffect),
[Page Visibility](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API),
[Torch intra-op threads](https://docs.pytorch.org/docs/2.14/generated/torch.set_num_threads.html),
and [OpenCV capture thread settings](https://docs.opencv.org/4.13.0/d4/d15/group__videoio__flags__base.html).

## Sampling-budget correction — 11 October 2026

A later update fixes slot allocation: missing sources and retry backoff no longer
spend inference intervals, while all-unavailable sweeps still sleep. Health now
contains bounded six-phase timings, failure/overrun counters and a processor run
identity. A local read-only profiler records counter deltas, health latency and
optional Linux CPU/RSS. See [RUNTIME_PROFILE.md](RUNTIME_PROFILE.md) and
[Current validation](validation/sampling-budget-validation.json). The 55-test and
short CPU/browser observations above remain the earlier milestone's evidence;
that milestone had 182 tests. Current measurements do not establish
full-rate detection, long-term throughput or real plate accuracy.

## Disabled-processor preview polling — 14 October 2026

The local app was running with `AI26_PROCESSING_ENABLED=0`. Before the UI checked
processor health, its six camera tiles each retried `/api/preview` every three
seconds and received 503, adding about two failing preview requests per second
while no sampled image could exist. Camera health now exposes the processing
switch; tiles poll only when an available source reports an active loading or
processing state. When inference is disabled or a camera is in an error state,
the tiles show a short status and stop preview requests. The focused recorded
player remains usable when privacy mode is off.

Verification used the same open local browser and API process with processing
disabled: after the change, camera tiles displayed `Processing paused`, the
focused recorded player played, and no `/api/preview` requests appeared in the
next five seconds of server logs. This only measures the disabled-processor
case; it is not a general Core Web Vitals or enabled-inference benchmark.

## Bounded forward decode — 12 October 2026

A decode-only comparison of 24 target indices per bundled clip found bounded
forward advancement faster than always seeking under the sampled local load.
All 144 raw frame hashes matched the existing method. The implemented decoder
was then checked against those same hashes and a moving, colour-changing MJPG
fixture decoded sequentially as a frame-index reference. Nearby advancement is
bounded and requires verified cursor/target positions; resets, larger jumps and
unsupported positions retain seeks. The current backend suite has 190 tests.
See [DECODE_SAMPLING.md](DECODE_SAMPLING.md) and its validation for actual
measurement conditions. These comparisons do not establish OCR accuracy or
full-frame-rate throughput. Main-service concurrency was not sampled during the
preliminary comparison and is not claimed.
