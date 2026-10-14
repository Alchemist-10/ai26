# Synthetic degradation generator

This offline utility creates deterministic, image-level research derivatives
for five controlled conditions: rain, fog, low light, motion blur and sensor
noise. It never changes the supplied source image and refuses to overwrite an
existing output. The PNG derivative has a JSON sidecar containing source and
derivative SHA-256 hashes, the condition, severity, seed and transformation
parameters.

```bash
python evaluation/degradation_generator.py path/to/source.png \
  --condition rain --severity 0.6 --seed 17 \
  --output /tmp/ai26-research/rain-017.png
```

The sidecar is written beside the output as `rain-017.png.manifest.json`.
Outputs are explicitly marked `synthetic_degraded_derivative`; the sidecar sets
`condition_is_observed_weather` and `accuracy_claim` to false. This tool only
corrupts individual images. It does not create temporally consistent clips,
collect real adverse-weather footage, label plates/vehicles, run OCR, or measure
recognition accuracy. Keep generated samples out of evidence reports and real
accuracy claims. Real weather collection and held-out labeled evaluation remain
required for those claims.

Run its regression tests with:

```bash
python -m unittest tests.test_degradation_generator
```
