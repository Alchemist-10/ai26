# Synthetic degradation generator

This offline utility creates deterministic research derivatives for five
controlled conditions: rain, fog, low light, motion blur and sensor noise. It
supports individual images and bounded video sequences. It never changes the
supplied source and refuses to overwrite an existing output. Every derivative
has a JSON sidecar containing source and derivative SHA-256 hashes, the
condition, severity, seed and transformation parameters.

```bash
python evaluation/degradation_generator.py path/to/source.png \
  --condition rain --severity 0.6 --seed 17 \
  --output /tmp/ai26-research/rain-017.png
```

The sidecar is written beside the output as `rain-017.png.manifest.json`.
For sequence experiments, pass an MP4 source and `--video`:

```bash
python evaluation/degradation_generator.py path/to/source.mp4 --video \
  --condition rain --severity 0.6 --seed 17 \
  --output /tmp/ai26-research/rain-017.mp4
```

Rain fields translate with a fixed seeded direction and speed; sensor noise
combines fixed-pattern and seeded per-frame noise. Fog, low-light and blur
parameters stay fixed across a sequence. Processing is streamed and bounded to
12,000 frames, 4096 pixels per dimension, and 2 GiB. MP4 audio is dropped. The
video sidecar records frame count and these limits' relevant output metadata.

Outputs are explicitly marked `synthetic_degraded_derivative`; the sidecar sets
`condition_is_observed_weather` and `accuracy_claim` to false. The temporal
effects are simplified synthetic corruptions, not observed weather. This tool
does not collect real adverse-weather footage, label plates/vehicles, run OCR,
or measure recognition accuracy. Keep generated samples out of evidence reports
and real accuracy claims. Real weather collection and held-out labeled
evaluation remain required for those claims.

Run its regression tests with:

```bash
python -m unittest tests.test_degradation_generator
```
