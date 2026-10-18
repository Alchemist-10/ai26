# Plate-crop quality classifier

`train_plate_quality.py` fits a small multinomial logistic classifier over
read-only image-statistic features for three manually labeled crop classes:
`readable`, `marginal`, and `unreadable`. The dataset manifest records crop and
source-clip paths/hashes, camera, recording session, labels and split. Crop
bytes and source-clip hashes are checked before feature extraction. Camera,
session and source-clip groups must be disjoint across train, validation and
test. Regularization is selected on validation macro-F1; the held-out test set
is scored once and reports class support, confusion matrix, precision, recall
and macro-F1.

Start from [`plate-quality-manifest.template.json`](plate-quality-manifest.template.json)
and run:

```sh
uv run --frozen --directory backend python ../evaluation/train_plate_quality.py \
  ../plate-quality-manifest.json \
  --output ../evaluation/results/plate-quality-model.json
```

The output JSON contains normalization parameters, weights, selected
regularization, dataset/manifest hashes and held-out metrics. Outputs are
no-clobber. The classifier is offline and is not integrated with live inference;
its softmax scores are not calibrated probabilities and are not OCR confidence.
Use reviewed physical plate crops with independently assigned labels and
camera/session-held-out splits. Unit fixtures test training and validation code
only; they are synthetic and are not field accuracy evidence. No reviewed
quality dataset was present in this workspace at implementation time.

Classical dark-channel dehazing and unsharp sharpening remain separate offline
derivative tools. Learned dehazing/deblurring, paired restoration datasets and
Indian-plate OCR adaptation still require labeled field images and corresponding
ground truth; no restoration/OCR benefit is claimed here.
