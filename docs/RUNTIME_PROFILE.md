# Sampling budget and runtime profiling

The shared processor schedules at most `AI26_TOTAL_INFERENCE_FPS` attempts per
second across available cameras. A missing source or a camera waiting for its
retry deadline no longer consumes an inference slot. An all-unavailable sweep
waits one second before checking again. Ready cameras retain round-robin order;
a failed decode/model attempt spends one slot, then enters the existing ten-second
retry backoff. Work exceeding a slot runs to completion without a catch-up queue.

Previously each of the nine catalog cameras consumed a slot, including the three
missing plate sources. With six available sources and a two-attempt total budget,
this allowed roughly 1.33 completed samples per second before startup/overrun costs.
The corrected scheduler can use the same budget for available work. More successful
samples increase useful compute/storage work; this is not a reduction in CPU work
or full-frame-rate detection. Recorded native playback remains independent.

## Health metrics

`GET /api/health` and camera catalog health now include a stable processor_run_id,
attempts, failed_attempts, budget_overruns, missing_source_checks and
retry_backoff_checks. Attempts count source/decode/model work; missing/retry checks
are separate. A budget overrun means an attempted step exceeded `1 / sampling_budget_fps`
seconds. It does not count dropped source frames or browser playback frames.
Prometheus also exports managed sampled-read image bytes used, configured capacity,
and utilization ratio so the optional alert rules can warn before image capture is
blocked by the storage budget.
`processed_fps` uses monotonic elapsed time so wall-clock changes do not inflate it.
The public health and camera-catalog endpoints report configured source availability
independently from processor state: a recorded source can remain available while
inference is paused, while a missing file stays unavailable. `status` and frame
counters continue to describe processor activity, not file presence.

`last_attempt` records total milliseconds, completed/unfinished phase timings and
success. Successful attempts also enter a bounded 64-sample timing window per
camera, with nearest-rank p50/p95/max for total and six phases:

- source: initial open/hash, metadata inspection and replay-session setup;
- decode: seek/read and transition to loading;
- inference: frame copy and detector/tracker/OCR annotation;
- artifacts: read context plus matching frame/crop capture;
- persistence: observation insertion and local rule derivation;
- jpeg: full/preview encoding, resize and cache publication.

Failed attempts do not enter successful timing percentiles. Partial timings remain
in last_attempt; failure and overrun counts are cumulative. `first_success` remains
separate from the rolling window. It is the camera's first completed attempt,
not an independently cold model run: only the first model-using camera may include
shared lazy model initialization. No raw reads or per-frame logs are added.

The legacy latency_ms remains annotation-through-publish latency and excludes
source/decode, for compatibility. Use last_attempt.total_ms for complete attempted
work. Timing window maintenance has bounded memory; health computes summaries from
these samples and creates no extra inference workers, decoder or polling timer.

## Read-only profiler

Start Sakshi normally, then run from the repository root:

```bash
uv run --frozen --directory backend python ../evaluation/profile_runtime.py \
  --duration 120 --output ../evaluation/results/runtime.json
```

When authentication is enabled, `/api/health` requires an administrator
session. For a local authorized profile, place only the session cookie in a
user-readable protected file as `ai26_session=<value>` and pass
`--cookie-file /absolute/path/to/admin-cookie`. The profiler reads it for
requests and never writes the cookie value to its output. `/healthz` is public
but intentionally contains no per-camera counters and cannot be used for a
processor profile.

Optionally pass `--pid API_PROCESS_PID` on Linux for process CPU/RSS. Use the actual
uvicorn PID, not the launcher/npm PID. The profiler reads procfs and never signals,
starts or stops processes. Birth ticks detect process exit/PID reuse; later CPU
samples are excluded after identity loss. CPU percent can exceed 100% across cores;
RSS is current resident memory, not peak RSS.

Only local HTTP API origins are accepted. Duration is bounded to 5–600 seconds,
interval to .25–5 seconds, and each health response to 1 MiB with a five-second
request timeout. A late sampler skips slots rather than sending queued catch-up
requests. A final response may finish after the requested sampling deadline.
API failures are counted and subsequent samples may recover. Monotone counters and
processor_run_id detect API restarts; an unverified counter window receives no
verified counter rate. The profiler also preserves the computed counter rate as a
diagnostic while suppressing the steady-state rate when health reads fail, a sample
gap exceeds 2.5 intervals, frame ages show a wall-clock discontinuity, or the
counter window is unverified. Older APIs without the new counters/run ID are
unverified too.

Each sample includes monotonic elapsed time and host wall time. A frame-age reset
is treated as a clock warning only when that camera's frame counter did not
advance; a newly processed frame normally resets its age and is not a clock jump.
This avoids suppressing a valid rate on sparsely scheduled cameras while retaining
an explicit host wall-clock discontinuity check.

The output contains conditions, first/last health, bounded per-tick counters,
endpoint latency, optional CPU/RSS distributions, counter deltas, profile-quality
flags and the reasons a steady-state rate may be suppressed. It writes only its
explicit output file and does not create observations or alter sources.
The already-running processor continues its normal database/image writes.

## Validation limits

Thirteen isolated contracts cover scheduler fairness, missing/backoff work, idle
waits, slow/failing attempts, bounded telemetry, monotonic FPS, local-origin/response
validation, counter restarts, endpoint outage recovery, PID reuse/procfs parsing,
late-sample quality handling and frame-age clock-jump detection. That profiling
milestone recorded 182 passing tests. The later
[decoder milestone](DECODE_SAMPLING.md) has the current 190-test suite.

The local before/after measurement uses the bundled sample vehicle clips and the same
two-attempt budget under normal host load. It is not aligned to identical replay
frames or controlled background conditions. The before window is 30 seconds; the
after profile requests 120 seconds including its initial health check. The actual
verified counter window is recorded separately. Results are in
[Runtime validation](validation/sampling-budget-validation.json). Real CAM-07–09
plate sources, independently cold OCR runs, variable-rate capture accounting,
long-duration load, physical mobile devices, throttled networks and held-out accuracy
remain unmeasured. Sparse replay sampling intentionally omits source frames.

A later [five-minute nine-camera profile](validation/active-inference-profile-9cams-2026-10-18-300s.json)
recorded 349 completed frames in a verified 298.011-second counter window
(1.1711 FPS against the 2 FPS budget), with no failed attempts, health failures,
counter resets or sampling/clock anomalies. All recorded sample sources were
processing at both ends of the window. CAM-07–09 exceeded their shared-budget
interval on most attempts. This is local replay evidence, not a live recovery,
multi-hour, browser frame-drop, or accuracy measurement.

The browser check confirmed one playing native video, six decoded 320×180 previews
and no document overflow at the actual 798×812 viewport. The read-only browser
scope did not expose playback-quality counters, so no frame-drop number is claimed.
Such counters describe native playback rather than inference sampling; see
[MDN playback-quality reference](https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/getVideoPlaybackQuality).
