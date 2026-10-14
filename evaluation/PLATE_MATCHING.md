# Review-only plate-string matching

`backend/plate_matching.py` compares two format-valid canonical plate strings
using edit distance. If OCR confidences are supplied for both reads, it also
reports a heuristic score weighted by their geometric mean. The score is not a
probability, and a threshold only selects strings for human review. The helper
always sets `identity_linked` to false; it is not called by live queries,
trajectory construction, alerts, or evidence reports.

For a labeled pair dataset, `evaluate_labeled_pairs()` reports the positive and
negative denominators, candidate counts, false-candidate fraction among selected
pairs, false-positive candidate rate on known negatives, and recall across a
caller-provided threshold sweep. Example record shape:

```python
{
    "left_plate": "KL07AB1234",
    "right_plate": "KL07AC1234",
    "same_vehicle": False,
    "left_ocr_confidence": 0.82,
    "right_ocr_confidence": 0.79,
}
```

Evaluation requires both positive and negative labels and format-valid plates.
Split pairs by vehicle and recording session before threshold selection; never
use adjacent frames as independent pairs. The included regression tests use
synthetic examples only and are not a measured false-link limit. CAM-07–09
readable footage and independently labeled identity pairs are still required
before selecting an operational threshold or making accuracy claims.

Run the helper tests from `backend/`:

```bash
uv run --frozen python -m unittest discover -s ../tests -p 'test_plate_matching.py' -v
```
