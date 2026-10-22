# Heuristic quality and enhancement routing

`quality_router.py` reports image statistics and proposes offline enhancement
candidates. It always retains `raw` as the reference. Example:

```bash
uv run --frozen --directory backend python evaluation/quality_router.py input.jpg \
  --output /tmp/input-quality.json
```

When plate boxes are available from a detector or a reviewer, pass them as
pixel-space `x1,y1,x2,y2` coordinates. Repeat the flag for multiple plates:

```bash
uv run --frozen --directory backend python evaluation/quality_router.py input.jpg \
  --plate-box 120,80,260,126 --plate-box 480,92,618,138 \
  --output /tmp/input-quality.json
```

To request boxes from the currently selected hash-snapshotted ALPR detector,
use `--detect-plates` instead of `--plate-box`. This explicit option can download
the model assets on first use and stores hashed snapshots in the configured Sakshi
model cache. The report includes detector file hashes, records when no candidates
were returned, and deliberately discards OCR text. Detector boxes are still
unverified review hints; they do not represent plate-detection accuracy.

```bash
uv run --frozen --directory backend python ../evaluation/quality_router.py input.jpg \
  --detect-plates --output /tmp/input-quality.json
```

The report keeps whole-frame scene statistics separate from each operator- or
detector-supplied plate crop. Each crop includes its dimensions, image-statistic flags, and a suggested
OCR preprocessing candidate list that always starts with `raw`. These are
review-only hints; the tool does not alter pixels, choose a live OCR path, or
infer weather from a plate crop. Boxes outside the image, empty boxes, and
non-integer coordinates are rejected.

The rules check luminance, contrast, Laplacian variance, saturation, clipping,
and channel balance. A low-contrast/low-saturation combination is labeled only
as a *haze or fog-like appearance hint*; the report explicitly says weather is
unverified. Threshold flags and candidate methods are descriptive suggestions,
not automatic processing or a trained classifier. JSON output includes the raw
file hash; existing output reports are never replaced.

Thresholds are fixed engineering heuristics without camera-specific calibration.
Validate them against diverse, labeled camera frames before using them to select
an OCR path. The plate metrics are descriptive crop-quality hints, not a trained
or calibrated plate-readability score. The tool does not infer verified weather,
plate quality, or OCR accuracy.
