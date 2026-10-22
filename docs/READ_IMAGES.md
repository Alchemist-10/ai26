# Per-read image evidence — 11 October 2026

New sampled reads retain their own unannotated-frame and plate/vehicle-crop JPEG
references. A later, lower-confidence read no longer borrows an earlier track's
image. Valid, tentative, invalid, low-confidence and ambiguous reads use the same
capture path. Empty detection batches do no image work.

The processor encodes the shared frame once per processed frame and reuses
identical role/crop requests within that frame. Each reference records camera,
session, frame index, source clip hash/time and original dimensions. Crops also
record clipped pixel bounds. Fully outside or empty boxes retain the frame and an
explicit missing-crop status; negative coordinates cannot wrap NumPy slices.
JPEG quality remains 92. These are decoded JPEG derivatives, not original encoded
video-frame bytes and not an archive of unsampled video frames.

## Failures and storage

`artifact_capture` records policy `per-read-jpeg-v1`, frame/crop statuses, clipped
bounds and JPEG quality. Failed writes/encoding retain the raw observation with
`write_or_encode_failed`. Capacity failures use `storage_budget_exceeded`. No failure
substitutes a prior image. Existing corrupt digest files fail without overwrite;
unique temporary files are removed after failed publication.

`AI26_ARTIFACT_MAX_BYTES` is a positive integer byte budget, default **2 GiB**.
The budget governs managed new JPEG writes. Existing images and report leases are
preserved when capacity is reached; byte-identical files can still be reused.
It excludes SQLite, models and source/playback videos. External filesystem changes
are reconciled by minute maintenance. Lowering the limit below existing usage
does not delete existing files; new unique images fail explicitly until capacity
becomes available. This is an application budget, not an operating-system quota.

Usage is indexed once and updated after successful publication. Age-based cleanup
reconciles the index while deleting files older than the configured observation
retention period (seven days by default, configurable from 7 to 365), preserving
active report leases. Frame processing and health polling do not scan the directory for
each read. The processor has no best-image reference cache to grow with track IDs.

Administrator `/api/health` and camera catalog health expose `artifact_storage` (used/limit bytes),
`artifact_capture_ms` and the latest processed frame's image attempts/failures,
incomplete reads and storage-budget failures. These are latest-frame measurements,
not cumulative counters. Inference can remain `processing` while image writes
fail; use these capture fields and report coverage to assess image availability.

## Reports and compatibility

Version-3 manifests add immutable `artifact_coverage` counts for matching current
frames/crops, complete/incomplete reads, capture failures and legacy/manual reads.
Version-4 manifests also include immutable top-three image review candidates per
plate passage. Coverage checks the exact camera/session/frame/source context,
dimensions, digest/size descriptors and expected clipped crop bounds. Older
best-shot references are never upgraded to complete current-read coverage.

JSON and ZIP contain the same stored summary and all raw per-read references.
Image files are deduplicated by digest; multiple matching read contexts remain in
the raw-read entries. Print displays the stored coverage and missing-read counts.
Version-1/2/3 snapshots remain immutable and print an unavailable-coverage notice.
Missing/corrupt referenced files still fail report creation/download explicitly.
Reports with recorded capture failures may exist with incomplete coverage; their
raw history and missing-image counts remain visible. Existing 5,000-raw-read and
64 MiB image-package limits apply, so longer intervals can require a shorter export.

New captures also record downsampled luminance, contrast and Laplacian-variance
statistics for stored plate crops. The evidence report uses those statistics with
OCR confidence to expose at most three distinct crop candidates per local passage.
Its fixed score is `0.45*OCR confidence + 0.30*sharpness + 0.15*contrast +
0.10*exposure`; each image component is normalized as recorded in the report.
This is an unvalidated reviewer aid, not a measured “best shot” or accuracy score.
Every raw read and image remains in the JSON/ZIP evidence package. Duplicate crop
hashes consume one candidate slot, and old reads without these metrics are skipped.

Pipeline metadata now identifies seven source files: the prior inference/loader/
tracking/fusion/format components plus `processing.py` and `artifacts.py`. This
does not identify every application module or establish authenticity/accuracy.

## Validation and cost

**113 backend tests pass**, including 17 new image-capture tests. Cases cover shared
encoding, later low-confidence frames, clipped/negative boxes, uncertain raw reads,
write/encoder/capacity failure, temporary cleanup, corrupt existing files, digest
reuse at capacity, lease-aware budget recovery, no repeated directory scan,
immutable reports/ZIP/print and older snapshots. Frontend lint/build pass with the
two existing Fast Refresh warnings. Synthetic evaluation remains separate from
accuracy measurement.

Twenty live vehicle reads from CAM-02–06 had 40 verified image references. All
40 JPEG hashes were recreated from the decoded source frames and exact crop
bounds. Six available cameras returned snapshots, a clean restart retained all
ten sampled historical IDs, and the main database contains no plate or synthetic
print-fixture reads. CAM-07–09 sources remain absent. A separate synthetic browser
report showed two current-image reads and one legacy gap correctly at desktop and
390×844 widths; all four images decoded, tables remained keyboard-scrollable and
the page had no horizontal overflow. Its services/tab/data were removed.

A short capture-only comparison used 20 decoded CAM-01 proxy frames and constructed
constant-confidence boxes/track IDs, writing into disposable directories:

| Reads per frame | Current median capture | Current max | Current unique JPEG bytes |
| --- | --- | --- | --- |
| 1 | 4.381 ms | 6.991 ms | 4,443,757 |
| 8 | 6.220 ms | 6.557 ms | 5,176,447 |
| 64 | 18.353 ms | 20.926 ms | 9,318,457 |

The previous policy wrote only the first frame/crops in these constant-confidence
cases and reused them afterward (2 / 16 / 128 image attempts). Current capture made
40 / 180 / 1,300 attempts, including one shared frame per batch. Additional ongoing
processing/storage work is intentional for current-read coverage; these numbers do not
establish end-to-end FPS, sustained throughput or accuracy. All benchmark outputs
were removed. The sampling/thread budgets and small browser previews are unchanged.

See [raw validation](validation/read-artifacts-validation.json),
[capture comparison](validation/read-artifacts-performance.json),
[model provenance](PROVENANCE.md) and the [full checklist](PROGRESS.md).

The source import extension adds camera/source resolver code to new pipeline
provenance, for nine component hashes. The 113-test and seven-component records
above remain evidence of this image milestone; current validation is in
[SOURCE_IMPORT.md](SOURCE_IMPORT.md).
