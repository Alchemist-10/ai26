# Vehicle model pinning and camera canaries

Sakshi loads the bundled `backend/yolov8n.pt` lazily by default. Operators may
override it with a pinned compatible vehicle checkpoint, or assign a second
checkpoint to a fixed list of cameras. Assignments are read once when the API
starts. Candidate files are copied into the protected data volume under their
content hash; inference loads that immutable snapshot, checks the configured
digest, and records the loaded digest and profile on each vehicle observation.
The model ID identifies exact bytes and does not establish model accuracy or
authenticity.

Create the ignored `models/` directory, place operator-managed checkpoints in
it, and set the corresponding values in `.env`. Compute each digest from the
exact file:

```sh
sha256sum models/stable.pt models/candidate.pt
```

To pin a replacement for all cameras, set `AI26_VEHICLE_MODEL_PATH` and
`AI26_VEHICLE_MODEL_SHA256`. To stage a canary, keep the stable checkpoint
settings and also set `AI26_VEHICLE_CANARY_MODEL_PATH`,
`AI26_VEHICLE_CANARY_MODEL_SHA256`, and `AI26_VEHICLE_CANARY_CAMERAS` (a
comma-separated allowlist such as `CAM-01`). The canary must use compatible
vehicle classes and preprocessing. The API refuses incomplete settings,
unknown camera IDs, unreadable files, or a digest mismatch. Model initialization
stays lazy, so unused branches do not load either checkpoint.

Administrator-only `GET /api/health` (when authentication is enabled) exposes
path-free rollout status, loaded digests and the checkpoint compatibility
result. `/healthz` remains a minimal liveness endpoint. Each vehicle event also carries
`model_profile`, `checkpoint_sha256`, and a `model_id` used as its persisted
`model_version`. No runtime traffic split,
automatic promotion, accuracy gate, or UI-based hot swap is performed. To
rollback, remove the three canary variables and restart the API; the camera
allowlist then uses the stable model. A stable-checkpoint change also requires
an API restart. Existing events retain the model version that produced them.

On first use of either checkpoint, Sakshi requires Ultralytics task `detect`, the
COCO class IDs/names used by this pipeline (and `person` when privacy masking is
enabled), then runs a 640×640 synthetic BGR forward pass and verifies the returned
detection-box/class interface. Failed compatibility checks prevent the model
from entering the active cache; that camera reports the inference error and no
observations are produced by that failed attempt. This is a runtime compatibility
check, not accuracy validation or a canary quality gate. It uses Ultralytics'
documented [`task` and `names` properties](https://docs.ultralytics.com/reference/models/yolo/model/)
and [detection result boxes](https://docs.ultralytics.com/tasks/detect/).

## Plate detector and OCR startup check

The plate pipeline now runs a small synthetic check when its exact model files
are first loaded. It passes a blank 640×640 BGR frame through the plate
detector and checks that candidate boxes, if any, have finite, ordered
coordinates. It also passes an in-memory generated crop through the OCR model
and checks for a string result and finite confidence values in [0, 1]. The
recognized text is discarded. A failed check prevents the pipeline from being
cached and the processing attempt fails; a passed check records only the probe
shapes, result type and candidate/confidence counts in model provenance.

This catches broken result containers, coordinates or OCR-confidence contracts.
It cannot prove that the detector finds real plates or that OCR is accurate. A
2026-10-16 local run passed the wrapper checks, but the sampled camera clip
produced zero detector candidates. ONNX Runtime also emitted lenient graph
shape-merge warnings; the synthetic contract checks do not establish their
effect on positive plate detection. The result is recorded in
[`validation/alpr-runtime-cam01-2026-10-16.json`](validation/alpr-runtime-cam01-2026-10-16.json).

This supports a controlled operator-managed canary and exact rollback target,
not a measured canary result. Validate the candidate on held-out labeled data
and monitor detection/plate outcomes before choosing the camera allowlist.
