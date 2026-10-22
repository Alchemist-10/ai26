# Student frame review

This local tool prepares a prediction-blind review set for Sakshi's mini-project
evaluation. It runs independently of the dashboard and inference processor.
It never fills human labels from model output, edits prior plate reviews, or
claims accuracy before annotations and corresponding predictions exist.

## Current set

The first set is stored locally at
`backend/data/review/frame-set-2026-10-18/`. It contains 45 full-size JPEG images:
five evenly spaced frame positions in each available sample feed. The
frames are the midpoints of equal-duration strata, chosen without inspecting
predictions. CAM-01–06 use available 960×540 playback fallback files because
their configured originals are absent. CAM-07–09 use the supplied managed
original files. Source roles and dimensions are recorded per clip/frame.

The existing nine initial and twelve follow-up plate crop annotations remain
in their original private files. Their file hashes and aggregate status counts
are referenced in the new manifest; no previous plate text is copied into the
new labels.

## Review in the browser

Serve only the generated review directory on loopback:

```bash
python -m http.server 5176 --bind 127.0.0.1 \
  --directory backend/data/review/frame-set-2026-10-18
```

Open `http://127.0.0.1:5176/` and:

1. Enter your reviewer name.
2. Count visible cars, buses, trucks, motorcycles and bicycles. Include
   identifiable partial vehicles; exclude people, reflections and vehicles on
   signs. Enter zero explicitly when no vehicle is visible.
3. For count-only review, leave the complete-vehicle-boxes checkbox unchecked.
4. To prepare detector scoring, draw every vehicle box, choose each vehicle's
   class and tick the complete-boxes checkbox. Box count must equal the entered
   vehicle count. Tight boxes should cover the visible vehicle extent. A
   reviewer must resolve ambiguous classes before using them for class-specific
   metrics; do not guess a class just to complete an image.
5. Optionally draw plate regions. Choose readable, uncertain or unreadable for
   each region. Transcribe characters only for a readable plate. A frame with
   multiple plates can have different readability labels for each plate.
6. Save the frame as reviewed, then use Next or Next pending. If an image cannot
   be reviewed, add a reason and mark it unusable; it must be excluded from
   accuracy denominators later.
7. Export labels JSON at the end of each session. Use Import labels to restore
   a saved file for the same set. Replacing a nonempty draft needs confirmation.

Drafts are autosaved in this browser's localStorage under the review-set ID.
Changing browser/profile/URL origin, clearing browser data, private-mode limits
or storage failures can make that copy unavailable. The page reports storage
failures and offers JSON export. The server is read-only: browser edits do not
update `labels-template.json` or the observation database. Export the edited
labels and retain that file with `manifest.json` for subsequent evaluation.

### Interface and accessibility

The review tool extends Sakshi's inherited dark/zinc/teal identity and Plex Sans
with system fallbacks. On desktop, the source image and navigation sit beside
the observation form; at widths of 1000px or less, the form stacks below the
image. Visible labels, native controls and teal focus outlines support keyboard
entry of counts, frame navigation, and label import/export. Status messages use
a polite live region.

Creating boxes requires pointer dragging; there is no keyboard drawing mode.
Count-only review remains available without boxes. Use **Open full-size image**
to inspect details beyond the fitted image. The scoped finish review returned
ship for `.impeccable/review/frame-review-desktop.png` and
`.impeccable/review/frame-review-mobile.png`; this records the supplied review,
not a new test run or whole-app accessibility certification.

## Reproduce a new set

From the repository root:

```bash
uv run --frozen --directory backend python ../evaluation/prepare_frame_review.py \
  --per-camera 5 --output data/review/frame-set-NEW-NAME
```

An existing output directory is rejected. The preparation counts frames by
sequentially decoding the selected files rather than trusting stale container
frame counts, and extracts the selected indices without seeking. It records
the source-file SHA-256, sequential frame index, nominal-FPS time estimate,
decoded BGR pixel digest and JPEG digest. Source hashes are checked before and
after extraction. Failed preparation does not publish a partial review set.
JPEG images are research derivatives, not original evidence frames.

## What these labels support

- Explicit reviewed vehicle counts support per-frame count-error measurements
  against predictions on the exact same frames. This is not a passage count.
- Frames with complete class-labeled vehicle boxes can support detector
  precision/recall and IoU matching once corresponding predictions exist.
- Readable plate boxes and text can support region-matched OCR comparisons;
  unreadable/uncertain plates must be reported separately.
- Sparse still frames do not establish tracking ID-switch rates, cross-camera
  identity, physical speed, road density or unique vehicles across the dataset.

This set is exploratory. These source clips have already been inspected during
development, different frames can repeat the same vehicles, source sessions
are not independently verified and CAM-01–06 sources are playback copies. It is not
an independent held-out dataset or a ready train/validation/test manifest.
Report these limitations and frame/clip denominators with later results.

Raw frames, plate labels and generated review files stay under git-ignored
`backend/data/`. The generator, interface and synthetic tests can be versioned
without publishing footage or human plate transcriptions.
