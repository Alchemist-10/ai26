# Heuristic quality and enhancement routing

`quality_router.py` reports image statistics and proposes offline enhancement
candidates. It always retains `raw` as the reference. Example:

```bash
uv run --frozen --directory backend python evaluation/quality_router.py input.jpg \
  --output /tmp/input-quality.json
```

The rules check luminance, contrast, Laplacian variance, saturation, clipping,
and channel balance. A low-contrast/low-saturation combination is labeled only
as a *haze or fog-like appearance hint*; the report explicitly says weather is
unverified. Threshold flags and candidate methods are descriptive suggestions,
not automatic processing or a trained classifier. JSON output includes the raw
file hash; existing output reports are never replaced.

Thresholds are fixed engineering heuristics without camera-specific calibration.
Validate them against diverse, labeled camera frames before using them to select
an OCR path. The tool does not infer verified weather, plate quality, or OCR
accuracy.
