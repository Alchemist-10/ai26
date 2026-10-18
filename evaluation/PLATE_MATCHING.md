# Review-only plate-string matching

`backend/plate_matching.py` compares two format-valid canonical plate strings
using edit distance. It distinguishes equal observed alphanumeric characters from strings that become equal only after OCR-to-character normalization repairs. The latter is always labeled for human review. If OCR confidences are supplied for both reads, it also reports a heuristic score weighted by their geometric mean. The score is not a probability, and a threshold only selects strings for human review. The helper
always sets `identity_linked` to false; it is not called by live queries,
trajectory construction, alerts, or evidence reports.

For a labeled pair dataset, `evaluate_labeled_pairs()` reports the positive and
negative denominators, candidate counts, false-candidate fraction among selected
pairs, false-positive candidate rate on known negatives, and recall across a
caller-provided threshold sweep. Example record shape:

```python
{
    "pair_id": "pair-0001",
    "left_read_id": "read-001",
    "right_read_id": "read-009",
    "left_vehicle_id": "vehicle-01",
    "right_vehicle_id": "vehicle-01",
    "left_session_id": "session-01",
    "right_session_id": "session-02",
    "left_plate": "KL07AB1234",
    "right_plate": "KL07AC1234",
    "same_vehicle": False,
    "left_ocr_confidence": 0.82,
    "right_ocr_confidence": 0.79,
}
```

Each threshold also includes two-sided 95% Wilson score intervals for the false
candidate fraction, false-positive rate on negative pairs, and recall. The
confidence level can be supplied to `evaluate_labeled_pairs()`. These intervals
show sampling uncertainty only and assume independent labeled pairs; they do not
account for correlated frames, split leakage or label errors. They are not
probability calibration and do not enable identity linking.

Evaluation requires both positive and negative labels, format-valid plates, a
unique `pair_id`, and unique `left_read_id`/`right_read_id` values across the
dataset. It also requires vehicle and session IDs, checks that the label agrees
with vehicle IDs, and rejects any vehicle or session reused across pair rows.
This prevents read, vehicle and session leakage from inflating the pair count.
Inputs are capped at 100,000 pairs and 100 unique thresholds. IDs are caller
assertions; camera/location grouping, label truth, and residual correlation are
not verifiable from these rows. Raw plate strings are capped at 64 characters.
Never use adjacent frames as independent pairs.
The included regression tests use
synthetic examples only and are not a measured false-link limit. CAM-07–09
readable footage and independently labeled identity pairs are still required
before selecting an operational threshold or making accuracy claims.

Run the helper tests from `backend/`:

```bash
uv run --frozen python -m unittest discover -s ../tests -p 'test_plate_matching.py' -v
```
