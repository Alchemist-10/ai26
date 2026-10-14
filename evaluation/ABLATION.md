# Paired model ablations

`ablation.py` compares raw, classical, learned and fusion predictions on exactly
the same held-out samples. It refuses synthetic records, missing variants,
changed labels, duplicate/missing samples, non-test clips, mismatched camera or
session metadata, inconsistent model provenance, and manifest-hash mismatches.
The output includes per-variant metrics, metric deltas from the raw baseline,
paired plate-correctness changes, model/configuration hashes and the manifest
hash. It does not select a model automatically or claim results beyond the
labeled test set.

Each JSONL record contains the fields accepted by `evaluation/evaluate.py`, plus
`variant`, `clip_id`, `manifest_sha256`, and `run_metadata`. Supported variants
are `raw`, `classical`, `learned`, and `fusion`. The `run_metadata` object requires
`model_id`, `model_version`, `weights_sha256`, `preprocessing_id`, and a distinct
`configuration_sha256` per variant. Every variant must contain the same
`sample_id` values and identical ground-truth labels.

```bash
uv run --frozen --directory backend python ../evaluation/ablation.py \
  --manifest ../evaluation/dataset-manifest.json \
  --records ../evaluation/ablation-predictions.jsonl \
  --output ../evaluation/results/ablation-report.json
```

The command requires a ready dataset manifest with non-empty train, validation,
and test splits, verified clip hashes and complete labels. The repository has no
such supplied held-out dataset, so no real ablation report or accuracy result is
claimed. A starting point for documenting intended use, data lineage, known
limitations, evaluation conditions and failure cases is
[`model-card.template.json`](model-card.template.json).

Run helper tests from `backend/`:

```bash
uv run --frozen python -m unittest discover -s ../tests -p 'test_ablation.py' -v
```
