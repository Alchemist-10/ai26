# Per-track plate-fusion comparison

The bounded evaluator compares the last OCR string in each labeled sequence
against Sakshi's conservative `PlateConsensus` result. It requires explicitly
synthetic JSONL records so the fixture cannot be mistaken for a model accuracy
benchmark:

```bash
uv run --frozen --directory backend python ../evaluation/plate_fusion_eval.py \
  --records ../evaluation/plate-fusion-example.jsonl \
  --output /tmp/plate-fusion-report.json
```

Every observation includes a unique `sample_id`, `synthetic: true`, camera,
recording session, track ID, strictly increasing per-track frame index, expected
plate, predicted plate (or `null`), optional confidence and association status.
Tracks are evaluated independently by camera, session and track ID. Ambiguous
association resets that track's vote history; an unread matched frame is not
treated as a character vote. The report includes sequence-level exact/incorrect/
unread counts for the last-read baseline, exact/incorrect/abstained counts for
consensus, coverage and a check that every supported output appeared among that
track's own OCR reads. The report is written without replacing an existing file
and includes the input SHA-256.

Schema version 2 also compares any review-only character candidate with the
fixture's expected plate and reports exact, incorrect and abstained counts plus
coverage. This is a synthetic behavior check; the candidate never changes the
`conflicting` identity status or fills `fused_plate`.

The included fixture has two interleaved tracks. The last-read baseline gets one
of two sequences wrong; per-track consensus supports one correct sequence and
abstains on the conflicting sequence, with no incorrect output and no identity
crossing. This illustrates the coverage/error tradeoff only. It does not measure
OCR quality, confidence calibration, real identity risk or field performance.
Real-data analysis still requires authorized held-out clips and labels.

When reads conflict, the runtime also includes per-character vote diagnostics:
the winning character, its weighted share, its margin over the runner-up, and an
abstention reason. These shares are heuristic summaries of the supplied OCR
confidence weights, not calibrated probabilities. A character suggestion stays
review-only; the identity remains `conflicting` and `fused_plate` stays null.
