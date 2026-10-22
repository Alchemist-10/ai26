# Sakshi local tracking update — 9 October 2026

The earlier tracker greedily chose nearest centers and expired identities only by
missed-frame count. At sparse inference rates this could retain stale identities,
steal another track's closest detection, or swap two crossing subjects.

The local tracker now uses elapsed time, last-observed motion, box overlap and
class/shape/distance gates, followed by global minimum-cost assignment with an
explicit unmatched option. Near-equal competing assignments retire implicated old
IDs and return fresh ambiguous IDs. The OCR pipeline retains those raw reads with
`tracking_ambiguous` status and keeps them out of supported plate searches. Motion
trails show observed points only. Clip-loop/reconnect resets still isolate sessions.
Observations carry association status/cost and tracker version
`motion-box-assignment-v2`. These costs are heuristics, not identity probabilities.

## Checks

69 backend tests pass. New regression cases cover global assignment against exhaustive
small matrices, greedy track theft, two crossing subjects, brief occlusion, elapsed
expiry, class/shape rejection, ambiguity retirement, OCR abstention/raw persistence,
ordered clocks and missed-frame expiry. They also exercise fragmentation and camera/
session-scoped sequence order. Existing pipeline/replay/report tests continue to pass.
The model-integration test uses stub model outputs and the actual tracking/fusion/
normalization/rendering pipeline; it does not measure OCR/detector accuracy.

The evaluator now reports visible-track fragmentation and denominators. A fragment
requires a tracked → missed → tracked interruption while ground truth remains
visible. Ground-truth absence ends the visible span; initial misses do not count.
A nonnegative integer `frame_index` on every camera/session sequence frame enables
strict ordering checks. Missing indices make chronology explicitly unverified.

## Timing sample

The before/after replay used the latest 1,000 persisted vehicle detections grouped
into 897 camera/session/frame batches, at most two detections per batch. Each tracker
was run ten times over the batches (8,970 timing samples). Median association time
was 0.0038 ms for the previous tracker and 0.0126 ms for the new tracker. Maximum
observed times were 0.3787 ms and 0.2209 ms, respectively. These timings exclude model
inference, empty frames without stored detections and video decode; the main backend
was running concurrently. They do not establish complete live throughput.

A separate synthetic 64-box frame, repeated 20 times, measured medians of 2.1042 ms
before and 10.5226 ms after (new maximum 10.9976 ms). Global assignment adds CPU work,
especially in crowded inputs. It stays small in the available sparse batches; target
footage with hundreds of objects requires its own sustained performance check.

Raw measurements and the constructed before/after scenarios are in
`docs/validation/tracking-validation.json`; the previous implementation came from
commit `4290b8c`. The synthetic scenarios are examples chosen to reproduce failures,
not an unbiased held-out benchmark.

## Remaining work

Conflicting valid OCR strings can now expose a confidence-weighted character vote
for reviewer context. It never changes the conflicting status or the null fused
identity. This suggestion remains unvalidated and is not used by plate queries.

Tracking still uses heuristic motion/boxes and has no learned appearance. Sparse
sampling, nonlinear motion, similar subjects and longer occlusion can break identity.
Ambiguity abstention can fragment tracks and inflate camera-local passage counts;
it prioritizes avoiding unsupported identity carryover. Plate and vehicle tracks
remain separate and their association remains unvalidated. Readable plate footage,
held-out identities, original recording clocks and calibrated camera locations are
needed for real OCR, passage-count and cross-camera accuracy estimates.
