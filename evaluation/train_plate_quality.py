"""Train/evaluate an offline plate-crop quality classifier from labeled crops."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import cv2
import numpy as np

try:
    from quality_router import inspect
except ImportError:
    from evaluation.quality_router import inspect

CLASSES = ("readable", "marginal", "unreadable")
FEATURES = ("mean_luminance", "luminance_stddev", "laplacian_variance",
            "mean_saturation", "clipped_dark_fraction", "clipped_bright_fraction",
            "blue_mean", "green_mean", "red_mean")
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 20_000
MAX_CROP_PIXELS = 1_048_576
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REGULARIZATION = (0.0001, 0.001, 0.01, 0.1)


class QualityDatasetError(ValueError):
    """Invalid crop labels, provenance or split separation."""


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 256:
        raise QualityDatasetError(f"{field} must be a non-empty string of at most 256 characters")
    return value.strip()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_dataset(manifest_path: Path) -> tuple[dict, str]:
    """Verify crop bytes and prohibit camera/session/source-clip split leakage."""
    manifest_path = Path(manifest_path).resolve(strict=True)
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise QualityDatasetError("manifest exceeds the 8 MiB limit")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QualityDatasetError("manifest is unavailable or invalid JSON") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise QualityDatasetError("manifest must be a schema_version 1 object")
    _text(manifest.get("dataset_id"), "dataset_id")
    records = manifest.get("records")
    if not isinstance(records, list) or not 12 <= len(records) <= MAX_RECORDS:
        raise QualityDatasetError(f"records must contain 12 to {MAX_RECORDS} labeled crop images")
    definitions = manifest.get("label_definitions")
    if not isinstance(definitions, dict) or any(not isinstance(definitions.get(label),str) or not definitions[label].strip()
                                                for label in CLASSES):
        raise QualityDatasetError(f"label_definitions must describe all classes: {CLASSES}")

    root = manifest_path.parent.resolve()
    seen_ids, seen_paths = set(), set()
    group_split = {key: {} for key in ("camera_id", "session_id", "source_clip_sha256")}
    source_hash_cache = {}
    verified = []
    for index, record in enumerate(records):
        where = f"records[{index}]"
        if not isinstance(record, dict):
            raise QualityDatasetError(f"{where} must be an object")
        record_id = _text(record.get("record_id"), f"{where}.record_id")
        camera = _text(record.get("camera_id"), f"{where}.camera_id")
        session = _text(record.get("session_id"), f"{where}.session_id")
        clip_hash = record.get("source_clip_sha256")
        crop_hash = record.get("sha256")
        for value, field in ((clip_hash, "source_clip_sha256"), (crop_hash, "sha256")):
            if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
                raise QualityDatasetError(f"{where}.{field} must be a lowercase SHA-256")
        label = record.get("label")
        if label not in CLASSES:
            raise QualityDatasetError(f"{where}.label must be one of {CLASSES}")
        split = record.get("split")
        if split not in ("train", "validation", "test"):
            raise QualityDatasetError(f"{where}.split must be train, validation or test")
        relative = Path(_text(record.get("crop_path"), f"{where}.crop_path"))
        if relative.is_absolute():
            raise QualityDatasetError(f"{where}.crop_path must be relative to the manifest")
        path = (root / relative).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise QualityDatasetError(f"{where}.crop_path must resolve to a file inside the manifest directory")
        if path in seen_paths or record_id in seen_ids:
            raise QualityDatasetError(f"{where} repeats a record ID or crop path")
        if _hash_file(path) != crop_hash:
            raise QualityDatasetError(f"{where} crop SHA-256 does not match its bytes")
        clip_relative = Path(_text(record.get("source_clip_path"), f"{where}.source_clip_path"))
        if clip_relative.is_absolute():
            raise QualityDatasetError(f"{where}.source_clip_path must be relative to the manifest")
        clip_path = (root / clip_relative).resolve(strict=True)
        if not clip_path.is_relative_to(root) or not clip_path.is_file():
            raise QualityDatasetError(f"{where}.source_clip_path must resolve inside the manifest directory")
        if clip_path not in source_hash_cache:
            source_hash_cache[clip_path] = _hash_file(clip_path)
        if source_hash_cache[clip_path] != clip_hash:
            raise QualityDatasetError(f"{where} source clip SHA-256 does not match its bytes")
        for dimension, value in (("camera_id", camera), ("session_id", session),
                                 ("source_clip_sha256", clip_hash)):
            previous = group_split[dimension].setdefault(value, split)
            if previous != split:
                raise QualityDatasetError(f"split leakage: {dimension} {value!r} appears in {previous!r} and {split!r}")
        seen_ids.add(record_id); seen_paths.add(path)
        verified.append({**record, "path": path, "split": split, "label": label})

    for split in ("train", "validation", "test"):
        counts = Counter(row["label"] for row in verified if row["split"] == split)
        missing = [label for label in CLASSES if counts[label] < (2 if split == "train" else 1)]
        if missing:
            raise QualityDatasetError(f"{split} split lacks required labeled examples for: {', '.join(missing)}")
    return {"dataset_id": manifest["dataset_id"], "label_definitions": definitions,
            "records": verified}, _hash_file(manifest_path)


def _features(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None or image.shape[0] * image.shape[1] > MAX_CROP_PIXELS:
        raise QualityDatasetError("a crop is undecodable or exceeds the one-megapixel feature bound")
    values = inspect(image)["features"]
    return np.asarray([
        values["mean_luminance"], values["luminance_stddev"], values["laplacian_variance"],
        values["mean_saturation"], values["clipped_dark_fraction"], values["clipped_bright_fraction"],
        *values["bgr_channel_means"],
    ], dtype=np.float64)


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exponential = np.exp(np.clip(shifted, -60, 60))
    return exponential / exponential.sum(axis=1, keepdims=True)


def _fit(x: np.ndarray, y: np.ndarray, regularization: float, iterations: int = 500) -> tuple[np.ndarray, np.ndarray]:
    weights = np.zeros((len(CLASSES), x.shape[1]), dtype=np.float64)
    bias = np.zeros(len(CLASSES), dtype=np.float64)
    targets = np.eye(len(CLASSES), dtype=np.float64)[y]
    step = 0.05
    for _ in range(iterations):
        probabilities = _softmax(x @ weights.T + bias)
        error = probabilities - targets
        weights -= step * ((error.T @ x) / len(x) + regularization * weights)
        bias -= step * error.mean(axis=0)
    return weights, bias


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    matrix = np.zeros((len(CLASSES), len(CLASSES)), dtype=np.int64)
    for truth, prediction in zip(y_true, y_pred):
        matrix[int(truth), int(prediction)] += 1
    per_class = {}
    f1_values = []
    for index, label in enumerate(CLASSES):
        tp = int(matrix[index, index]); actual = int(matrix[index].sum()); predicted = int(matrix[:, index].sum())
        precision = tp / predicted if predicted else 0.0
        recall = tp / actual if actual else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {"support": actual, "precision": round(precision, 6),
                            "recall": round(recall, 6), "f1": round(f1, 6)}
        f1_values.append(f1)
    return {"samples": int(len(y_true)),
            "accuracy": round(float(np.mean(y_true == y_pred)), 6),
            "macro_f1": round(float(np.mean(f1_values)), 6),
            "classes": list(CLASSES), "confusion_matrix_rows_true_cols_pred": matrix.tolist(),
            "per_class": per_class}


def train_evaluate(manifest_path: Path) -> dict:
    """Train using train/validation only, evaluate the selected model once on test."""
    dataset, manifest_sha = load_dataset(manifest_path)
    records = dataset["records"]
    x = np.stack([_features(row["path"]) for row in records])
    y = np.asarray([CLASSES.index(row["label"]) for row in records], dtype=np.int64)
    split = np.asarray([row["split"] for row in records])
    train_mask = split == "train"; validation_mask = split == "validation"; test_mask = split == "test"
    mean = x[train_mask].mean(axis=0)
    scale = x[train_mask].std(axis=0)
    scale[scale < 1e-8] = 1.0
    normalized = (x - mean) / scale
    best = None
    for regularization in REGULARIZATION:
        weights, bias = _fit(normalized[train_mask], y[train_mask], regularization)
        prediction = _softmax(normalized[validation_mask] @ weights.T + bias).argmax(axis=1)
        score = _metrics(y[validation_mask], prediction)["macro_f1"]
        if best is None or score > best["validation_macro_f1"]:
            best = {"regularization": regularization, "validation_macro_f1": score,
                    "weights": weights, "bias": bias}
    test_prediction = _softmax(normalized[test_mask] @ best["weights"].T + best["bias"]).argmax(axis=1)
    return {
        "schema_version": 1,
        "type": "offline_plate_crop_quality_classifier",
        "status": "trained_from_labeled_crops",
        "dataset_id": dataset["dataset_id"],
        "label_definitions": dataset["label_definitions"],
        "manifest_sha256": manifest_sha,
        "records_sha256": hashlib.sha256("".join(row["sha256"] for row in records).encode()).hexdigest(),
        "split_dimensions": ["camera_id", "session_id", "source_clip_sha256"],
        "split_counts": {name: int(np.sum(split == name)) for name in ("train", "validation", "test")},
        "feature_names": list(FEATURES),
        "classes": list(CLASSES),
        "normalization_mean": mean.tolist(), "normalization_scale": scale.tolist(),
        "weights": best["weights"].tolist(), "bias": best["bias"].tolist(),
        "selected_l2": best["regularization"],
        "validation": {"macro_f1": best["validation_macro_f1"], "l2_grid": list(REGULARIZATION)},
        "test": _metrics(y[test_mask], test_prediction),
        "probabilities_calibrated": False,
        "live_routing_enabled": False,
        "limitations": ["handcrafted image statistics only", "test set must represent intended cameras and conditions",
                        "a classifier score is not OCR accuracy or plate identity confidence"],
    }


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("output already exists; choose a new path")
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def run(manifest_path: Path, output_path: Path) -> Path:
    manifest_path = Path(manifest_path).resolve(strict=True)
    output_path = Path(output_path).resolve()
    if output_path == manifest_path or output_path.suffix.lower() != ".json":
        raise ValueError("output must be a separate .json file")
    model = train_evaluate(manifest_path)
    _write_new(output_path, (json.dumps(model, indent=2, sort_keys=True) + "\n").encode())
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="labeled plate-crop JSON manifest")
    parser.add_argument("--output", type=Path, required=True, help="new model-and-evaluation JSON path")
    args = parser.parse_args()
    try:
        print(run(args.manifest, args.output))
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
