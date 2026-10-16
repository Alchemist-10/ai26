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

## Dashboard polling cadence — 14 October 2026

The live browser/API log showed the root camera catalog and visible summary panels
refreshing every two to three seconds while inference was disabled. The catalog
now refreshes every five seconds; alerts and the visible evidence log every five
seconds; analytics and congestion summaries every ten seconds. Submitted plate
investigations and active camera previews keep their three-second refresh cadence.
The serial, visibility-aware polling hook still aborts on navigation or a hidden
tab and refreshes immediately when visible again. In a ten-second server-log
sample with Analytics open after the change, the page issued one stats request and
one flows request; camera-catalog polls continued separately. This verifies the
new cadence, not a measured reduction in CPU, end-to-end latency or Core Web
Vitals.

## Six-camera replay soak — 14 October 2026

An isolated API process replayed the six bundled camera clips for 120 seconds
with the vehicle branch enabled, plate recognition disabled, and the configured
2 FPS total sampling budget. Its database and artifacts were kept in a temporary
directory. Across 13 health/metrics samples, the processor advanced 239 frames
with zero failed attempts and one budget overrun; final per-camera rates were
0.318–0.324 FPS. Median phase totals were 209–233 ms and p95 totals 320–454 ms.
The API process averaged 76.16% CPU and peaked at 541,188 KiB RSS. Health and
metrics returned no failures, with median response times of 8.7 ms and 6.5 ms.
The report records clip hashes, per-interval counters, per-camera timing data,
and host/commit metadata in
[`validation/ev09-six-camera-soak-2026-10-14.json`](validation/ev09-six-camera-soak-2026-10-14.json).

## Five-minute six-camera replay soak — 15 October 2026

A second isolated run used the same six bundled clips, a fresh disposable data
root, vehicle detection enabled, plate recognition disabled, and the same
2 FPS total sampling budget. Its verified counter window completed 555 frames,
with zero failed attempts and zero health-read failures. There was one
processing-budget overrun. The three missing cameras stayed unavailable and
consumed no inference attempts. The profile calculated 1.862 FPS, but a single
20.75-second sample gap (expected: 2 seconds) coincided with 1.0% API CPU and
frame ages jumping to about 44 minutes. The cause is unverified, so that
aggregate rate is not a valid steady-state measurement. Sampled health latency
was 5.14 ms at the median and 9.09 ms at p95; sampled API process CPU was 47.0%
median / 82.4% p95, with 541 MiB maximum RSS. Hashed source clips, branch settings, exact commit,
per-sample counters, anomaly details, and machine data are in
[`validation/ev09-six-camera-soak-2026-10-15-300s.json`](validation/ev09-six-camera-soak-2026-10-15-300s.json).

The run documents the processor's behavior and resource samples but does not
validate a sustained 2 FPS rate because of the interruption. A clean repeat is
needed for that comparison. It also does not measure browser playback drops,
production stream behavior, OCR, or accuracy.

## Two-minute continuous repeat — 15 October 2026

A repeat with the same six hashed clips, branch switches and sampling budget
completed 232 frames over a verified 118-second window (1.966 FPS). Across 59
samples, the largest poll interval was 2.008 seconds and maximum observed frame
age was 2.97 seconds; no clock discontinuity or long sample gap appeared. There
were zero failed attempts and zero health-read failures, with four attempts
exceeding the 500 ms per-attempt budget. The three missing sources were not
scheduled. Health latency was 6.99 ms median / 10.36 ms p95, process CPU was
72.5% median / 109.5% p95, and maximum RSS was 542 MiB. The hashed inputs,
per-sample trace, and host/runtime details are in
[`validation/ev09-six-camera-soak-2026-10-15-120s-repeat.json`](validation/ev09-six-camera-soak-2026-10-15-120s-repeat.json).

This repeat is a cleaner short-window measurement close to the configured
sampling budget, not a hard-rate guarantee or a sustained deployment test. It
does not measure browser playback, live RTSP sources, OCR, or accuracy.

These profiles are bounded local replays, not a sustained deployment soak. They do
not measure browser dropped frames, cold-start OCR, plate recognition, real
camera capture, or detector accuracy; CAM-07–09 had no source files.

## Dashboard route chunks — 14 October 2026

The camera wall is the initial view, but map, congestion, timeline, alerts,
analytics, and query pages were statically imported into the initial JavaScript
entry. Those page modules now load on first navigation behind an accessible
loading status. Production builds from the same checkout/toolchain changed the
entry from 343.42 kB (104.04 kB gzip) to 284.20 kB (88.45 kB gzip), saving
59.22 kB (15.59 kB gzip, about 15% compressed) from the initial entry. The
deferred page chunks total 52.32 kB raw / 18.23 kB gzip in this build; they are
requested only when a corresponding page is selected. This is a bundle-size
comparison, not an instrumented LCP/INP or real-device measurement.

## Dashboard startup gate — 15 October 2026

The initial camera wall was hidden behind a full-screen welcome dialog with an
“Enter Console” button and no automatic continuation. Camera metadata was
already being requested behind the dialog, but the camera wall and focused player
did not mount until the user clicked. Removed the blocking intro so the operator
sees and can use the dashboard on the first render. A local browser check against
an isolated API with processing disabled showed all nine camera tiles and the
focused recorded player immediately; six available sources correctly displayed
“Processing paused” and the three absent sources remained labelled missing.
This verifies removal of the interaction gate, not a measured LCP/INP or a
real-device load-time improvement.

The focused native player now shows a browser-local dropped-frame count and
percentage, sampled every two seconds only while the page is visible in playback
mode. It reads `HTMLVideoElement.getVideoPlaybackQuality()`; no metric is sent to
the API. Two 10-second samples of one CAM-01 playback in the 1280×720 local
browser showed 5/416 (1.20%) and 9/650 (1.38%) incremental dropped frames. The
isolated API had processing disabled, so this is a focused player check rather
than a six-stream or production performance result. Raw samples are in
[`browser-playback-quality-2026-10-15.json`](validation/browser-playback-quality-2026-10-15.json).
The browser API defines total frames as frames displayed or dropped and exposes
dropped frames since media load ([MDN reference](https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/getVideoPlaybackQuality)).

## Local production launcher and deferred camera media — 15 October 2026

Two uncached headless Chromium runs at 1280×800 compared the local Vite dev
server with the optimized production preview. Before this change, Vite dev loaded
31–32 resources, transferred 10.8 MB, recorded 1–2 main-thread tasks of
61–91 ms, and reached its final observed LCP at 764–1008 ms. The production
preview loaded 9 resources and transferred 1.55 MB, but 1.43 MB was the focused
camera video automatically loaded on startup. These are local browser samples,
not low-end-device or network-throttling results.

The launcher now builds and serves the production frontend by default. Pass
`--dev-frontend` when hot reload is needed. With playback and detection views
both left unselected, two new runs loaded 31 resources / 9.38 MB in Vite dev,
versus 8 resources / 115 KB in production preview. First contentful paint was
492–552 ms in dev and 208–236 ms in preview; final observed LCP was 776–804 ms
and 384–484 ms respectively. The preview recorded no long tasks in either run;
dev recorded 1–2 tasks of 55–106 ms. Selecting **Recorded playback** then issued
one `/api/video/CAM-01` request; neither video nor MJPEG was requested before
the operator chose a view. The second preview run used a disposable data root and
disabled processor. See
[`validation/local-launcher-performance-2026-10-15.json`](validation/local-launcher-performance-2026-10-15.json).

The launcher changes the local default only; it does not remove the explicit
development-server path. Vite's preview proxy defaults to the configured
development proxy ([Vite preview options](https://vite.dev/config/preview-options)).
These short measurements do not establish real-device Core Web Vitals or
sustained inference performance.

## Browser responsiveness with inference enabled — 15 October 2026

An isolated optimized production preview ran with vehicle/person processing
enabled, plate recognition disabled, six bundled sources and a temporary data
root. During a 10.1-second sample, API health latency was 8.3 ms median / 25.0 ms
p95, CPU was 75% of one core by `/proc` process ticks, and no camera attempt
failed. Accessibility-driven browser action calls took 145–182 ms for opening
navigation, switching to sampled detections, opening Analytics after its first
lazy load, and returning to the Camera Wall. The resulting route states were
visible, but these are single action-call durations, not INP or click-to-paint.
The sample suggests the optimized local UI stayed responsive during warmed
inference on this host; it does not explain lag on lower-powered hardware or
network conditions. Full scope and limits are in
[`validation/live-ui-responsiveness-2026-10-15.json`](validation/live-ui-responsiveness-2026-10-15.json).

## Cache-disabled idle-browser sample — 16 October 2026

A headless Chromium run against the production preview used fresh tabs at
1280×800 and 390×844, with browser cache disabled and backend processing paused.
Both loaded eight resources and transferred about 116 KB. Desktop FCP/LCP were
204/424 ms and mobile FCP/LCP were 220/420 ms. Neither run reported a main-thread
long task; the navigation button reached the next double animation frame in
24 ms and 28 ms respectively. CLS was 0.0012 on desktop and 0 on mobile after
excluding shifts following recent user input. This is one local idle sample,
not INP, a throttled-network test, a physical-device result, or an
inference-enabled CPU measurement. It did not show a frontend main-thread stall;
inference-enabled backend load remains to be measured on the user's target
hardware.

## Reloaded preview API idle sample — 16 October 2026

After restarting the local API so it loaded the current routes, a 10-second
read-only profile sampled nine one-second health intervals with processing still
disabled. Health latency was 5.87 ms median / 6.11 ms p95; process CPU was 1%
median / 3% p95, and RSS was 104.5 MiB maximum. There were no health failures
and no inference attempts, so this confirms only the idle API baseline. It does
not measure browser interaction or multi-camera inference. The exact PID,
processor counters and interval samples are in
[`api-idle-profile-2026-10-16.json`](validation/api-idle-profile-2026-10-16.json).

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
