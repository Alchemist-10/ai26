# Vehicle model pinning and camera canaries

AI26 loads the bundled `backend/yolov8n.pt` lazily by default. Operators may
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

`GET /api/health` exposes path-free rollout status and loaded digests. Each
vehicle event also carries `model_profile`, `checkpoint_sha256`, and a
`model_id` used as its persisted `model_version`. No runtime traffic split,
automatic promotion, accuracy gate, or UI-based hot swap is performed. To
rollback, remove the three canary variables and restart the API; the camera
allowlist then uses the stable model. A stable-checkpoint change also requires
an API restart. Existing events retain the model version that produced them.

This supports a controlled operator-managed canary and exact rollback target,
not a measured canary result. Validate the candidate on held-out labeled data
and monitor detection/plate outcomes before choosing the camera allowlist.
