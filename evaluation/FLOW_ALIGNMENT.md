# Offline optical-flow alignment

`flow_align.py` aligns two to 32 same-sized, in-memory BGR frames from one fixed
camera to a chosen reference frame using dense Farneback optical flow. It returns
aligned pixel arrays and forward/backward consistency diagnostics. Inputs are
bounded to 3,145,728 pixels each to limit offline memory use.

```python
import cv2
from evaluation.flow_align import align_burst

frames = [cv2.imread(path) for path in frame_paths]
aligned, diagnostics = align_burst(frames, reference_index=0)
```

The helper does not write or replace source files, blend frames, combine OCR
strings, or assign identities. Its consistency fraction is a geometric diagnostic,
not a calibrated probability that a frame, plate, or pixel is correct. It is not
connected to the live camera pipeline. Motion, occlusion, lighting changes,
rolling shutter, and camera movement can all make the flow inaccurate. No
calibrated plate confidence, probabilistic OCR fusion, or held-out footage
evaluation is implemented; those remain necessary before using aligned bursts for
any recognition claim.

Run its regression tests from `backend/`:

```bash
uv run --frozen python -m unittest discover -s ../tests -p 'test_flow_align.py' -v
```
