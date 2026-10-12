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
`processed_fps` uses monotonic elapsed time so wall-clock changes do not inflate it.

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

Start AI26 normally, then run from the repository root:

```bash
uv run --frozen --directory backend python ../evaluation/profile_runtime.py \
  --duration 120 --output ../evaluation/results/runtime.json
```

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
total FPS claim. Older APIs without the new counters/run ID are unverified too.

The output contains conditions, first/last health, bounded per-tick counters,
endpoint latency, optional CPU/RSS distributions and counter deltas. It writes
only its explicit output file and does not create observations or alter sources.
The already-running processor continues its normal database/image writes.

## Validation limits

Twelve isolated contracts cover scheduler fairness, missing/backoff work, idle
waits, slow/failing attempts, bounded telemetry, monotonic FPS, local-origin/response
validation, counter restarts, endpoint outage recovery, PID reuse/procfs parsing
and late sampling. That profiling milestone recorded 182 passing tests. The later
[decoder milestone](DECODE_SAMPLING.md) has the current 190-test suite.

The local before/after measurement uses the six bundled vehicle clips and the same
two-attempt budget under normal desktop load. It is not aligned to identical replay
frames or controlled background conditions. The before window is 30 seconds; the
after profile requests 120 seconds including its initial health check. The actual
verified counter window is recorded separately. Results are in
[Runtime validation](validation/sampling-budget-validation.json). Real CAM-07–09
plate sources, independently cold OCR runs, variable-rate capture accounting,
long-duration load, physical mobile devices, throttled networks and held-out accuracy
remain unmeasured. Sparse replay sampling intentionally omits source frames.

The browser check confirmed one playing native video, six decoded 320×180 previews
and no document overflow at the actual 798×812 viewport. The read-only browser
scope did not expose playback-quality counters, so no frame-drop number is claimed.
Such counters describe native playback rather than inference sampling; see
[MDN playback-quality reference](https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/getVideoPlaybackQuality).
