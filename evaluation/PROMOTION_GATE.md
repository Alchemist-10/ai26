# Held-out model promotion gate

`promotion_gate.py` checks whether a digest-pinned canary meets a deployment
policy against a stable model. It never installs weights or changes the live
model. An `eligible` result is a review artifact, not an automatic promotion.

Create a policy from [`promotion-policy.template.json`](promotion-policy.template.json)
and replace every `null` with an explicitly approved value. Frame, box and plate
minimums are positive integers. Accuracy floors and allowed regressions are
fractions from 0 through 1. False-positive/read limits are counts per 100 labeled
objects/plates. The plate exact-match floor must be greater than zero; an
all-abstaining candidate cannot pass.

Generate separate stable and candidate reports with the same held-out manifest
and prediction records. For each real prediction record, include its exact
`model_sha256`; pass the same digest to `evaluate.py`. The evaluator binds each
report to the manifest bytes, model digest, test-only split, and a hash of the
exact sample-ID set. Synthetic and real records cannot be mixed.

Use a digest of a canonical bundle descriptor that identifies every model
weight/configuration and relevant inference-pipeline version used to create the
predictions. Hashing only the vehicle checkpoint is insufficient when plate
detector/OCR or preprocessing differs between runs.

```bash
python evaluation/evaluate.py \
  --records evaluation/results/stable-test.jsonl \
  --manifest evaluation/dataset-manifest.json \
  --model-sha256 STABLE_MODEL_SHA256 \
  --output evaluation/results/stable-report.json

python evaluation/evaluate.py \
  --records evaluation/results/candidate-test.jsonl \
  --manifest evaluation/dataset-manifest.json \
  --model-sha256 CANDIDATE_MODEL_SHA256 \
  --output evaluation/results/candidate-report.json

python evaluation/promotion_gate.py \
  --manifest evaluation/dataset-manifest.json \
  --stable-report evaluation/results/stable-report.json \
  --candidate-report evaluation/results/candidate-report.json \
  --stable-records evaluation/results/stable-test.jsonl \
  --candidate-records evaluation/results/candidate-test.jsonl \
  --stable-model-sha256 STABLE_MODEL_SHA256 \
  --candidate-model-sha256 CANDIDATE_MODEL_SHA256 \
  --policy evaluation/promotion-policy.json \
  --output evaluation/results/promotion-gate.json
```

The gate requires a ready manifest with verified clip hashes and disjoint
vehicle/camera/location/session splits; both reports must use the same manifest,
sample count and sample IDs, and the gate verifies the exact prediction-record
file hashes against each report. It checks configured candidate floors plus
non-inferiority against stable for detector precision/recall, exact plate reads,
false detections and false reads. Exit code `0` means eligible, `2` means the
valid reports failed the policy, and `1` means the inputs are invalid or
insufficient. A model hash and a manifest hash establish file identity, not
whether prediction generation was honest or human labels are correct.

No deployment thresholds are prefilled: they depend on the intended use and
must be approved by the operator. The current workspace has no reviewed,
held-out labels, so this gate cannot produce an eligible real-model report from
the bundled synthetic fixtures.
