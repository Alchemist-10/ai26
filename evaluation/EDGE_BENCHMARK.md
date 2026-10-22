# Detector export and edge-host benchmark

The optional `edge` dependency group adds ONNX export support without making the
larger exporter dependency part of the normal backend install. From the repository
root, the repeatable command is:

```bash
uv sync --frozen --directory backend --group edge
uv run --frozen --directory backend --group edge python ../evaluation/edge_benchmark.py \
  --output ../docs/validation/edge-benchmark-your-host.json
```

The command exports the bundled `yolov8n.pt` to FP32 ONNX, calibrates a separate
static QDQ INT8 model from sampled frames in the bundled CAM-01–06 clips, and
benchmarks PyTorch, FP32 ONNX and INT8 ONNX model-forward latency on the current
test host. Exported models live in a temporary directory and are removed after the
JSON report is written. The report hashes the source model and all calibration
clips, records frame indices, versions, CPU, provider, raw tensor drift and
class-aware detection agreement. Existing report paths are never overwritten.

The checked-in host sample at
[`docs/validation/edge-benchmark-local-host-2026-10-14.json`](../docs/validation/edge-benchmark-local-host-2026-10-14.json)
records 60 calibration frames, 10 measured model-forward runs per runtime, and
the development machine. Median latency was 92.834 ms for
PyTorch FP32, 95.309 ms for ONNX FP32 and 55.782 ms for ONNX INT8. The INT8 graph
was smaller (3.60 MB versus 12.82 MB), but at Sakshi's 0.4 vehicle confidence
threshold it matched only 15 of the 16 FP32 detections on those same calibration
frames. These are unlabeled calibration samples, not held-out evaluation. The
INT8 result is not suitable for promotion based on this run.

This evidence is partial. The development machine is not confirmed as the deployment
edge target; the calibration set is small and unlabeled; ONNX Runtime's suggested
pre-quantization pass was not run; agreement is not precision/recall; and the
exported detector is not integrated into Sakshi live inference. Plate detection/OCR,
full-pipeline throughput, power, thermals, long-duration load and dropped-frame
measurements are also outside this command. Do not replace the active PyTorch
model with the measured INT8 artifact without a larger held-out labeled dataset
and target-device tests.

Helper regression tests run from `backend/`:

```bash
uv run --frozen python -m unittest discover -s ../tests -p 'test_edge_benchmark.py' -v
```
