# Exact model provenance — 11 October 2026

This records the provenance milestone (96 tests) before the per-read image update.
Current reports are version 4 and reads hash seven components, including
`processing.py` and `artifacts.py`; see [per-read images](READ_IMAGES.md) for the
113-test current validation, capture coverage and storage limits.

New plate reads identify the exact detector ONNX, OCR ONNX and OCR configuration
bytes used by the inference session. The selected models remain
`yolo-v9-t-384-license-plate-end2end` and `global-plates-mobile-vit-v2-model`.
Model selection and OCR normalization/consensus behavior are unchanged.

## Loading and recording

ALPR initialization remains lazy. A missing plate-camera source never provisions
unused models. When needed, the loader resolves the package-cache files, copies
and hashes their bytes into `AI26_DATA_ROOT/models/<sha256>.<extension>`, then passes
those explicit paths to the detector and OCR constructors. Publication is atomic;
existing corrupt digest files fail explicitly. Files are verified again after
session construction before the model and metadata are published together.
Download/session failures leave initialization retryable under the processor's
existing backoff. Hashing runs during initialization, not on every frame. Package metadata is cached;
an initialized frame does not rescan model files or package metadata.

Metadata records model names, file roles, digests, sizes and basenames; it does not
expose local absolute paths. It also records Fast-ALPR/FastPlateOCR/Open Image
Models/ONNX Runtime versions, execution providers and the thread budget. ONNX
sessions use the configured Sakshi thread count (default 2) and one inter-op thread.
The loader APIs are locked to Open Image Models 0.6.0 and FastPlateOCR 1.1.0.

Successful, tentative, invalid, low-confidence and ambiguous reads share the
initialized provenance. Vehicle and plate reads also record separate hashes for
`inference.py`, `model_provenance.py`, `tracking.py`, `fusion.py` and
`plate_format.py`. This names source coverage rather than implying that the
inference file digest covers every backend or frontend module.

## Evidence exports

Version-2 reports retain all per-read metadata and add an immutable deduplicated
model-set summary with read counts, missing metadata and exact ALPR-file coverage.
Incomplete or malformed digests never count as exact identification. JSON, ZIP
manifest and print use the stored summary. Later model changes/read ingestion do
not alter an existing manifest/hash. Version-1 reports remain downloadable and
print an explicit unavailable-summary notice rather than backfilling current
model metadata. Model weights are not bundled in the evidence ZIP.

Print now formats provenance JSON for reading. At narrow screen widths, tables
use focusable horizontal scroll regions with a visible instruction, while print
layout retains the full tables. Desktop and 390×844 browser checks verified no
root horizontal overflow and visible provenance. The layout fixture was explicitly
synthetic, used its own database and was stopped/removed after verification.

## Verification and limits

96 isolated backend tests pass, including 14 new provenance cases for copy/hash
identity, changed files, corruption/empty inputs, initialization failure/retry,
thread/provider wiring, raw-read branches, coverage summaries, immutable exports,
HTML escaping and version-1 compatibility. Frozen dependency sync, frontend lint
and TypeScript/Vite build pass; lint retains two existing Fast Refresh warnings.

Both real cached ONNX models loaded from isolated hashed snapshots. The detector
ran on a 384×384 all-black image and returned zero detections. OCR ran separately
on a 32×100 all-black crop and returned `AB251D`, which is not a supported Indian
registration. This verifies execution and illustrates why raw OCR output is not
accuracy evidence. ONNX Runtime emitted shape-merge warnings while loading the
legacy OCR graph but completed initialization and prediction. These synthetic
inputs were never ingested into the main database.

| File role | SHA-256 | Bytes |
| --- | --- | --- |
| Plate detector | `888397b96d761c89db40bc9c305838e8652660f5e282c2cadebbe8d2951a77a8` | 7,771,218 |
| OCR weights | `e2fe5946c02e73901f73d21b3b7223a0c3e3b02059d4964fbf279b01af38d63c` | 4,991,602 |
| OCR configuration | `202b90f2a1f3a0d486b8f1fbd5cdc2f19f4f4881a094f086b983976ed3108aaf` | 507 |

A live restart retained all ten historical sample IDs and decoded snapshots from
six available sources. Twenty live vehicle reads had matching checkpoint and all
five component hashes, with the default two-thread budget. The main database has
zero plate-camera reads and zero synthetic layout-fixture records. CAM-07–09 remain
unavailable, so no real plate OCR or identity accuracy is measured.

Digests identify bytes; they do not authenticate a model, verify its accuracy or
provide a signed chain of custody. Older/manual reads cannot have their original
weights reconstructed. At this milestone, frame/crop evidence was selectively captured. The subsequent
[per-read image update](READ_IMAGES.md) completes capture attempts for new sampled
reads and reports legacy/capacity/write gaps explicitly (P1-07 done in that scope). The local model cache has no
automatic expiry and should be preserved for reproducibility.

See [raw provenance validation](validation/provenance-validation.json),
[real-model smoke](validation/alpr-model-validation.json),
[camera/link persistence](PERSISTENCE.md) and the [full checklist](PROGRESS.md).
The constructor contracts were checked against the official
[Fast-ALPR reference](https://ankandrew.github.io/fast-alpr/latest/reference/),
[Open Image Models factory](https://github.com/ankandrew/open-image-models/blob/main/open_image_models/detection/factory.py)
and [FastPlateOCR recognizer](https://github.com/ankandrew/fast-plate-ocr/blob/master/fast_plate_ocr/inference/plate_recognizer.py),
as well as the installed locked package sources.

## Source import extension

New reads now also hash cameras.py and source_catalog.py, for nine named components.
Earlier validation records describe their original five/seven-component scope.
See [SOURCE_IMPORT.md](SOURCE_IMPORT.md) for managed original/proxy manifests and
128-test current validation. Older stored provenance is not rewritten.
