# Bounded recorded-frame decoding — 12 October 2026

Each camera keeps one owned OpenCV/FFmpeg reader. The replay sampler still chooses
a source-frame index from its existing replay clock. A nearby increasing target
can now advance the reader with bounded `grab` calls, then `retrieve` only the target,
instead of repeatedly seeking back to a codec keyframe and decoding forward again.
There is no extra reader, inference worker, full-frame archive or frontend timer.
The total sampling budget remains unchanged.

## Cursor and failure rules

The first sample uses seek/read. Only a successful read whose next decoder position
matches target + 1 supplies a known cursor. Forward mode also requires the current
OpenCV cursor to match that remembered value. At most
`AI26_FORWARD_DECODE_MAX_FRAMES` explicit grab calls, including the target, are
allowed. The default/hard maximum is 128; values are clamped to 0–128 and 0 disables
forward mode. A gap of 127 intermediate indices uses 128 calls; a larger gap seeks.

Repeated targets, backward targets, replay resets, unknown/drifted starting positions
and larger jumps retain seek/read. Forward retrieval must verify its resulting
next-frame position; failure abstains before observation/image insertion and
enters the existing error/backoff/reopen path. Failed seek/grab/retrieve attempts
clear the remembered cursor. Missing source, fresh reopen and shutdown clear it too.
Each camera has independent cursor state. Unsupported position reporting keeps the
seek path; it does not enable unchecked forward advancement.

Health exposes forward_decode_max_frames, decode_mode, decode_grabbed_frames and
decode_position_verified. The last field is null for an unfinished/failed decoding
operation and false when seek/read succeeds without usable cursor reporting.
The grab field describes explicit advancement/read calls, not all internal codec
work or dropped frames. Existing source/frame timestamps and frame/crop capture
remain unchanged. An OpenCV position check is not capture-clock calibration.

The method follows [OpenCV's grab/retrieve/read contract](https://docs.opencv.org/4.13.0/d8/dfe/classcv_1_1VideoCapture.html).
The find-docs service lookup failed; the official version-matched reference and
actual installed OpenCV 4.13.0 behavior were checked directly.

## Pixel and index validation

A preliminary decode-only comparison used 24 indices per bundled camera, including
wraps, with one FFmpeg decode thread. All 144 bounded-forward raw frame SHA-256
values matched always-seek values. Target positions were identical; hashes are
computed outside the timed decoding interval. Main-service concurrency was not
sampled during that preliminary test and is not claimed. Benchmark order and
background host load were uncontrolled.

The final implementation was checked against all 144 same-source reference hashes.
An independent 180-frame moving, colour-changing MJPG fixture had 180 unique frames
when decoded sequentially. Eleven sample indices, including adjacent, forward,
large, backward, repeated and end-of-file targets, matched those canonical hashes.
The fixture database/media were disposable and removed; no generated footage entered
the main app. Pixel equivalence is a decoder contract, not detector/OCR accuracy.

Eight new contracts cover cursor use, exact advancement count, maximum/repeated/
backward/large targets, unknown and changed positions, grab/retrieve/seek failures,
post-retrieval drift, per-camera isolation and disabling/clamping the option. Existing
missing-source cleanup now also checks cursor removal. All 190 backend tests pass.

## Runtime sample and limits

A paired, decode-only CAM-01 proxy comparison alternated method order across six
rounds, using the same 12 targets spaced 50 frames apart per round. With one
OpenCV thread, 72 samples per method produced identical raw pixel hashes and
decoder positions. Repeated seek/read measured 72.0 ms median and 148.3 ms p95;
verified bounded-forward decode measured 13.3 ms median and 60.8 ms p95. Hashing
was outside the timed region. Conditions and limits are recorded in
[`validation/decode-paired-cam01-2026-10-16.json`](validation/decode-paired-cam01-2026-10-16.json).
This isolated decode result does not measure inference, six-camera contention,
browser responsiveness or playback drops.

To check the gap observed during six-camera round-robin, a second paired run used
75-frame spacing on every bundled proxy (four rounds, 32 samples per method per
camera). Forward decode remained faster: camera medians were 20.0–30.3 ms versus
65.7–73.0 ms for seek/read; p95 ranges were 64.2–74.2 ms versus 93.7–126.2 ms.
All 192 matched targets had identical pixel hashes and decoder positions. This
supports retaining the current 128-frame bound for these proxies; it does not
reproduce concurrent decode plus inference. Per-camera source hashes and timings
are in [`validation/decode-paired-six-camera-75frame-2026-10-16.json`](validation/decode-paired-six-camera-75frame-2026-10-16.json).

The existing app services were absent when the new startup check began. Both ports
were closed; the app was restored with processing enabled, all ten previously
sampled historical observation IDs remained, and six snapshots decoded. This was
a startup recovery, not a newly measured graceful shutdown. The source catalog and
metadata/source selections stayed unchanged; CAM-07–09 remain missing.

A subsequent requested 120-second read-only profile sampled the actual Python
uvicorn PID. The verified counter window and phase/CPU/RSS measurements are in
[Decode validation](validation/decode-validation.json). The current run reached
about 2.00 completed samples/sec with zero failed attempts, health failures or
budget overruns during that window. Timing windows retain at most 64 successful
samples per camera; first-success timing remains separate. More work or different
footage/load can change these results.

The prior scheduler profile ran on another day under different host load; its
CPU/FPS numbers are context, not a controlled optimization comparison. The paired
same-index decoder checks provide the narrower measured timing evidence. Decode
medians varied by clip and benchmark order. Native playback frame drops, UI
INP/LCP/CLS, physical low-end devices, throttled networks, long-duration soak,
independently cold OCR, VFR/capture-clock calibration and held-out accuracy remain
unmeasured. Sparse replay sampling intentionally omits source frames. Imported
recordings with short keyframe spacing or different codecs may favor seeks; use
0 to disable this optimization when measured on such inputs.

## Supplied 1080p plate clips — 18 October 2026

A paired decode-only diagnostic compared seek/read with forward grab/retrieve on
CAM-07–09 originals at 120-, 180-, 200- and 220-frame gaps. All tested target
pixels matched exactly. Forward decode was faster on CAM-07 and CAM-09 through
220 frames, but CAM-08 seek/read was faster at 200 and 220 frames. The profile
was collected while the nine-source inference process was active, so the values
are paired comparisons under shared load, not isolated speed guarantees. The
results do not support raising one global forward-decode bound. A measured,
source-hash-scoped policy now allows 221 grab calls (the target plus up to a
220-frame gap) only for the exact tested CAM-07 and CAM-09 originals. CAM-08 and
any changed/replacement source retain the global 128-call cap. An explicit
`AI26_FORWARD_DECODE_MAX_FRAMES` setting remains authoritative, including `0` to
disable forward decode. Health reports the effective per-camera bound. Ten focused
decoder tests cover source-hash matching, replacement fallback, override behavior
and the exact tested gap. The full 427-test backend suite passes. This changes the
runtime decoder policy, but does not yet establish higher full-system FPS; that
requires a post-restart profile. See the
[paired diagnostic](validation/decode-gap-cam07-09-2026-10-18.json).

After restart, a direct check through the production `Processor.decode_frame`
method primed each exact source at frame 100 and requested frame 321. CAM-07/09
selected forward mode with 221 grabs; CAM-08 selected seek with its 128-call
default. All resulting decoder positions verified at frame 322 and all three
pixel hashes matched independent seek/read results. See the
[production policy check](validation/decode-production-policy-cam07-09-2026-10-18.json).
The accompanying 58.003-second nine-source profile completed 112 frames
(1.9309 FPS), with no failures and three CAM-08 budget overruns. Its largest
observed forward gap was only 112 grabs, so it did not exercise the >128 policy;
no throughput gain is attributed to the source-specific bound. See the
[source-tuned profile](validation/active-inference-profile-9cams-2026-10-18-source-tuned-60s.json).

The same 1080p sources were also decoded at OpenCV/FFmpeg thread counts 1, 2, 4
and the library default. All tested frame hashes matched. Two threads improved
median seeks over one thread on each clip, while the unrestricted library default
was faster but had no bounded CPU cost. Recorded sources now default to two
threads (`AI26_RECORDED_DECODE_THREADS`, clamp 1–4); live RTSP readers retain
their separate single-thread setting. The full nine-source follow-up improved
from 1.1596 to 1.3696 completed FPS, with increased CPU/RSS and throughput still
below the 2 FPS budget. See the
[thread-count results](validation/decode-threads-cam07-09-2026-10-18.json) and
[full-system profile](validation/active-inference-profile-9cams-2026-10-18-2decode-threads.json).
A separate four-thread full-system run was slower at 1.2772 FPS and consumed
more CPU/RSS, so the app has been restored to two threads. See its
[profile](validation/active-inference-profile-9cams-2026-10-18-4decode-threads.json).
