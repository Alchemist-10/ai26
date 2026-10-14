# Classical enhancement experiments

`classical_enhance.py` applies bounded, classical image transforms for offline
inspection: CLAHE on Lab luminance, gamma, gray-world white balance, single-scale
Retinex, dark-channel dehazing, and restrained unsharp masking. It is not called
by the live camera or OCR pipeline.

Run it from the repository root with the backend's frozen environment:

```bash
uv run --frozen --directory backend python evaluation/classical_enhance.py path/to/input.jpg \
  --output-dir /tmp/ai26-derivatives --method clahe --method gamma
```

The source is read-only. Each result is lossless PNG in a separate output
directory and is marked `research_derivative`; the JSON manifest stores the
source and derivative SHA-256 hashes, method parameters, and descriptive input
image metrics. Existing output names cause an error instead of being replaced.
The metrics describe image statistics only. They do not establish plate
readability, OCR improvement, or model accuracy. Compare derivatives against raw
images using held-out, manually labeled footage before considering deployment.

The dark-channel and Retinex methods are simple research baselines. They may
introduce artifacts or reduce useful detail, especially on small, compressed,
or already well-lit crops. Keep the raw image as the evidence reference.
