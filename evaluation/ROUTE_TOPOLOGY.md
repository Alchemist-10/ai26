# Session-held-out route topology experiment

`route_topology.py` estimates empirical travel-time quantile windows for directed
camera pairs from manually labeled historical transitions. The JSONL input has
one record per recording session and directed camera pair:

```json
{"record_id":"r-001","session_id":"session-01","from_camera":"CAM-01","to_camera":"CAM-02","elapsed_seconds":84.2,"traversed":true,"split":"train","coordinates_validated":true,"clocks_synchronized":true}
```

The input must include `train` and `test` sessions with positive and negative
test candidates. A session cannot cross splits or contribute repeated samples
for the same directed pair. Each edge needs at least five positive training
sessions. The default candidate window is the 5th to 95th empirical quantile;
the held-out report includes precision, recall, false-accept rate, sample
denominators and unmodeled edges.

```sh
python evaluation/route_topology.py transitions.jsonl \
  --output evaluation/results/route-topology-review.json
```

This is an offline review artifact. The calibration booleans are input
assertions, not independently verified evidence; output records that limitation
explicitly. The tool requires them to be true before estimating elapsed-time
windows, but does not prove surveyed coordinates, synchronized clocks, or
independent labels. It does not write camera-pair constraints, enable identity
linking, or claim calibrated probabilities. Supply independent route labels and
coordinate/clock validation before considering any operator-reviewed window
for production.
