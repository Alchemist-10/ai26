# Evaluation inputs

Run from the repository root:

```bash
python evaluation/evaluate.py --records evaluation/example.jsonl --output evaluation/results/fixture.json
```

## Dataset manifest

Start from [`dataset-manifest.template.json`](dataset-manifest.template.json),
then record each supplied clip's relative path and SHA-256, camera/location/session,
split, clock and coordinate status, recording conditions, and manual vehicle/plate
labels. Paths must resolve inside the manifest directory. Keep the same vehicle,
camera, location, and recording session in only one split. Do not use adjacent
frames or repeated clips as independent examples.

Validate current inputs and report missing work:

```bash
python evaluation/dataset_manifest.py evaluation/dataset-manifest.json
```

Use `--require-ready` in an evaluation job to fail until files and labels exist
and all three splits are represented. `ready` means the manifest is structurally
complete and clip hashes match; it does not establish annotation quality, sufficient
sample size, or model accuracy. A dataset whose coordinates or capture clocks are
not independently validated is not ready for cross-camera travel evaluation. The
manifest records those declarations; the validator does not independently prove
coordinate survey or clock synchronization.

Non-synthetic evaluation records must include `clip_id`, `camera`, and `session`,
and the evaluator requires `--manifest`. It checks that every record maps to a
manifest clip in the test split and that camera/session match the clip. Synthetic
fixtures remain available without a manifest and are reported as synthetic.

The included records are **synthetic correctness fixtures**, not model accuracy.
Supply held-out, manually labeled prediction records to measure the real models.
Each line has a unique sample_id and optional expected_plate/predicted_plate,
expected_boxes/predicted_boxes (class label, bbox; optional ground-truth identity
and predicted track_id), expected_link/predicted_link and expected_rule/predicted_rule
Booleans, and independently counted expected_passages/predicted_passages.
Tracking labels require nonblank `camera` and recording `session` strings, plus
one ground-truth identity per box (each identity occurs once per frame). Include
nonnegative integer `frame_index` on every frame in an evaluated sequence, including
frames without visible subjects. Indices must strictly increase within each camera
and recording session; interleaved cameras/sessions are allowed. Without indices,
input order is assumed and `chronology_verified` remains false.

Tracking output reports ID switches, fragmentation, labeled identity/frame counts,
matched identity/frame counts and how many sequence frames have verified order.
A fragmentation is a tracked → unmatched → tracked interruption during one span
of ground-truth visibility. An initially missed subject or a true ground-truth
absence does not count as fragmentation. ID switches compare successive matched
IDs for the same labeled subject within a camera/session. Absence ends a visibility
span, while a detection miss on a visible labeled subject does not.
Plate strings should be canonical; null predicted_plate means abstention.

Keep a dataset manifest with clip hashes, camera/session/vehicle split membership,
source/capture clock metadata, location calibration, readable/unreadable plate labels,
and recording/weather conditions. Never use adjacent frames from the same vehicle
as independent training and test examples. Report denominators, abstentions,
positive/negative pair selection, hardware and inference settings with results.
The runner does not verify split independence or replace manual labeling. Add
held-out conditions and balanced rule/link negative cases
before making reliability claims. No detector/OCR benchmark target is claimed met.

## Runtime observation

`profile_runtime.py` samples an already-running local API and optionally a Linux
API PID. It writes endpoint latency, camera counter deltas, bounded timing windows
and CPU/RSS conditions. It is separate from labeled accuracy evaluation, creates
no model/processor and writes only the requested output. See
[Runtime profiling](../docs/RUNTIME_PROFILE.md) for bounds, command and limits.

For isolated classical image experiments, see
[Classical enhancement](CLASSICAL_ENHANCEMENT.md). Those derivatives are not
used in live processing and do not imply an OCR accuracy gain.
For seeded rain, fog, low-light, motion-blur and sensor-noise derivatives, see
[Synthetic degradation](DEGRADATION_GENERATOR.md). These are controlled image
corruptions, not collected adverse-weather footage or OCR robustness evidence.
For read-only condition hints and enhancement candidates, see
[Heuristic quality routing](QUALITY_ROUTER.md); its weather-like flags are
unverified and do not control the live pipeline.

Per-track character voting can expose a review-only candidate when OCR strings
conflict. See [tracking limits](../docs/TRACKING.md): the identity remains
conflicting and the candidate is never used as a supported plate.
Evidence reports also contain a heuristic top-three crop shortlist per passage;
see [per-read image evidence](../docs/READ_IMAGES.md). All source reads/crops remain.
