# Offline burst super-resolution experiment

`burst_super_resolution.py` performs bounded 2× translation-only shift-and-add
reconstruction from 2–8 same-camera images. It estimates frame displacement with
phase correlation, rejects weak or out-of-bound registrations and requires
subpixel phase diversity before fusing onto a higher-resolution grid.

```sh
python evaluation/burst_super_resolution.py \
  --input frame-001.png --input frame-002.png --input frame-003.png \
  --output research/reconstructed.png
```

The PNG is labeled `reconstructed` in its adjacent JSON manifest. The manifest
records every input filename/hash, registration shift/response, output hash and
method limitations. Outputs are no-clobber and cannot replace an input. The
utility preserves source frames and runs offline; it does not alter inference or
evidence reports.

This simple method assumes a fixed camera and approximately translational scene
motion. It does not model parallax, rolling shutter, occlusion, exposure changes,
or moving objects. Registration response and phase spread are diagnostics, not
calibrated confidence. Synthetic tests establish input bounds, registration
plumbing and provenance behavior only; no real burst quality, plate legibility,
or OCR benefit has been measured. Reconstructed pixels must never be described
as raw evidence.
