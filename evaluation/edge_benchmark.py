"""Export and benchmark Sakshi's YOLO detector on the current CPU host.

This measures model-forward latency and raw tensor agreement only. It is not a
target-device claim and does not measure detection accuracy.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import tempfile
import time

import cv2
import numpy as np
import onnxruntime as ort
import torch
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / "backend" / "yolov8n.pt"
DEFAULT_SOURCES = [ROOT / "backend" / "static" / "playback" / f"CAM-{index:02}.mp4" for index in range(1, 7)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def letterbox_bgr(frame: np.ndarray, size: int = 640) -> np.ndarray:
    """Match Ultralytics' square letterbox layout and return normalized RGB BCHW."""
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame must be a uint8 BGR image")
    if type(size) is not int or size < 32 or size > 2048:
        raise ValueError("size must be an integer from 32 to 2048")
    height, width = frame.shape[:2]
    ratio = min(size / width, size / height)
    new_width, new_height = round(width * ratio), round(height * ratio)
    resized = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
    dw, dh = size - new_width, size - new_height
    left, top = round(dw / 2 - 0.1), round(dh / 2 - 0.1)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    canvas[top:top + new_height, left:left + new_width] = resized
    return np.ascontiguousarray(canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0)


def sample_videos(paths: Sequence[Path], frames_per_source: int, size: int = 640) -> tuple[list[np.ndarray], list[dict]]:
    if not paths or type(frames_per_source) is not int or not 1 <= frames_per_source <= 32:
        raise ValueError("provide video paths and 1 to 32 samples per source")
    arrays, sources = [], []
    for path in paths:
        source = path.resolve(strict=True)
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"cannot open calibration video: {source}")
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if count < 1:
            capture.release()
            raise ValueError(f"video has no frames: {source}")
        indices = sorted(set(np.linspace(0, count - 1, min(frames_per_source, count), dtype=int).tolist()))
        read_indices, dims = [], []
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if ok and frame is not None:
                arrays.append(letterbox_bgr(frame, size))
                read_indices.append(index)
                dims.append([int(frame.shape[1]), int(frame.shape[0])])
        capture.release()
        if not read_indices:
            raise ValueError(f"no sample frames could be decoded: {source}")
        sources.append({"name": source.name, "sha256": sha256_file(source),
                        "frame_count": count, "sampled_frame_indices": read_indices,
                        "sampled_frame_dimensions_wh": dims})
    return arrays, sources


def _primary_tensor(output) -> np.ndarray:
    while isinstance(output, (tuple, list)):
        if not output:
            raise ValueError("model returned no outputs")
        output = output[0]
    if isinstance(output, torch.Tensor):
        output = output.detach().cpu().numpy()
    value = np.asarray(output)
    if not np.issubdtype(value.dtype, np.number) or not np.isfinite(value).all():
        raise ValueError("model output must contain finite numeric values")
    return value


def _latency(run_once, samples: Sequence[np.ndarray], warmup: int, runs: int) -> dict:
    for index in range(warmup):
        run_once(samples[index % len(samples)])
    values = []
    for index in range(runs):
        began = time.perf_counter()
        run_once(samples[index % len(samples)])
        values.append((time.perf_counter() - began) * 1000)
    return {"warmup_runs": warmup, "measured_runs": runs,
            "median_ms": round(statistics.median(values), 3),
            "p95_ms": round(float(np.percentile(values, 95)), 3),
            "mean_ms": round(statistics.mean(values), 3),
            "images_per_second": round(1000 / statistics.median(values), 3)}


def _drift(reference: np.ndarray, candidate: np.ndarray) -> dict:
    if reference.shape != candidate.shape:
        return {"same_shape": False, "reference_shape": list(reference.shape),
                "candidate_shape": list(candidate.shape)}
    difference = np.abs(reference.astype(np.float32) - candidate.astype(np.float32))
    return {"same_shape": True, "shape": list(reference.shape),
            "mean_absolute_difference": round(float(np.mean(difference)), 6),
            "p99_absolute_difference": round(float(np.percentile(difference, 99)), 6),
            "max_absolute_difference": round(float(np.max(difference)), 6)}


def _box_iou(first: Sequence[float], second: Sequence[float]) -> float:
    x1, y1 = max(first[0], second[0]), max(first[1], second[1])
    x2, y2 = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    area_b = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _match_detection_lists(reference: Sequence[dict], candidate: Sequence[dict], iou_threshold: float = 0.5) -> dict:
    pairs = []
    for ref_index, ref in enumerate(reference):
        for cand_index, cand in enumerate(candidate):
            if ref["class_id"] == cand["class_id"]:
                pairs.append((_box_iou(ref["xyxy"], cand["xyxy"]), ref_index, cand_index))
    used_ref, used_cand, matched_ious = set(), set(), []
    for iou, ref_index, cand_index in sorted(pairs, reverse=True):
        if iou >= iou_threshold and ref_index not in used_ref and cand_index not in used_cand:
            used_ref.add(ref_index)
            used_cand.add(cand_index)
            matched_ious.append(iou)
    return {"reference_count": len(reference), "candidate_count": len(candidate),
            "matched_count": len(matched_ious), "reference_match_fraction": len(used_ref) / len(reference) if reference else None,
            "candidate_match_fraction": len(used_cand) / len(candidate) if candidate else None,
            "unmatched_reference_count": len(reference) - len(used_ref),
            "unmatched_candidate_count": len(candidate) - len(used_cand),
            "median_matched_iou": round(float(np.median(matched_ious)), 6) if matched_ious else None,
            "iou_threshold": iou_threshold, "class_aware": True}


def _detection_agreement(fp32_path: Path, int8_path: Path, samples: Sequence[np.ndarray], image_size: int) -> dict:
    fp_model, int8_model = YOLO(str(fp32_path)), YOLO(str(int8_path))
    ref_total, candidate_total, matched_total = [], [], []
    per_frame = []
    for sample in samples:
        # Inputs are the exact normalized RGB tensors used for calibration. Undo
        # that transform so both Ultralytics predictors receive the same image.
        frame = np.clip(sample[0].transpose(1, 2, 0)[:, :, ::-1] * 255.0, 0, 255).astype(np.uint8)
        detections = []
        for model in (fp_model, int8_model):
            result = model.predict(frame, imgsz=image_size, device="cpu", classes=[2, 3, 5, 7],
                                   conf=0.4, iou=0.7, verbose=False)[0]
            rows = [{"class_id": int(box.cls[0]), "xyxy": [float(value) for value in box.xyxy[0]]}
                    for box in result.boxes]
            detections.append(rows)
        agreement = _match_detection_lists(detections[0], detections[1])
        ref_total.append(agreement["reference_count"])
        candidate_total.append(agreement["candidate_count"])
        matched_total.append(agreement["matched_count"])
        per_frame.append(agreement)
    return {
        "scope": "FP32 ONNX versus INT8 ONNX output agreement on calibration inputs; no ground-truth labels",
        "confidence_threshold": 0.4,
        "class_filter": [2, 3, 5, 7],
        "iou_match_threshold": 0.5,
        "frame_count": len(samples),
        "reference_detection_count": sum(ref_total),
        "candidate_detection_count": sum(candidate_total),
        "matched_detection_count": sum(matched_total),
        "unmatched_reference_count": sum(ref_total) - sum(matched_total),
        "unmatched_candidate_count": sum(candidate_total) - sum(matched_total),
        "per_frame": per_frame,
        "accuracy_measured": False,
    }


def run_benchmark(model_path: Path, sources: Sequence[Path], output: Path, *,
                  frames_per_source: int = 3, warmup: int = 5, runs: int = 30,
                  cpu_threads: int = 2, image_size: int = 640) -> dict:
    model_path = model_path.resolve(strict=True)
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"report already exists: {output}")
    for name, value, low, high in (("warmup", warmup, 0, 100), ("runs", runs, 1, 1000),
                                   ("cpu_threads", cpu_threads, 1, 8)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{name} must be an integer from {low} to {high}")
    samples, source_records = sample_videos(sources, frames_per_source, image_size)
    try:
        import onnx
        from onnxruntime.quantization import (
            CalibrationDataReader, CalibrationMethod, QuantFormat, QuantType, quantize_static,
        )
    except ImportError as error:
        raise RuntimeError("install the optional edge dependencies with `uv sync --frozen --group edge`") from error

    class ArrayCalibrationReader(CalibrationDataReader):
        def __init__(self, input_name: str, values: Sequence[np.ndarray]):
            self.input_name, self.values, self.index = input_name, list(values), 0

        def get_next(self):
            if self.index >= len(self.values):
                return None
            value = self.values[self.index]
            self.index += 1
            return {self.input_name: value}

        def rewind(self):
            self.index = 0

    torch.set_num_threads(cpu_threads)
    cv2.setNumThreads(1)
    providers = ["CPUExecutionProvider"]
    torch_model = YOLO(str(model_path)).model.to("cpu").float().eval()
    if hasattr(torch_model, "fuse"):
        torch_model.fuse()
    torch_inputs = [torch.from_numpy(item) for item in samples]

    with tempfile.TemporaryDirectory(prefix="ai26-edge-export-") as temporary:
        work = Path(temporary)
        export_checkpoint = work / model_path.name
        export_checkpoint.write_bytes(model_path.read_bytes())
        export_result = YOLO(str(export_checkpoint)).export(
            format="onnx", imgsz=image_size, dynamic=False, simplify=False,
            device="cpu", opset=18,
        )
        fp32_path = Path(export_result).resolve()
        fp32 = ort.InferenceSession(str(fp32_path), providers=providers,
                                    sess_options=_session_options(cpu_threads))
        input_name = fp32.get_inputs()[0].name
        if len(fp32.get_inputs()) != 1 or list(fp32.get_inputs()[0].shape) != [1, 3, image_size, image_size]:
            raise RuntimeError(f"unexpected ONNX input contract: {fp32.get_inputs()[0].shape}")
        int8_path = work / f"{model_path.stem}_int8.onnx"
        graph_nodes = onnx.load(str(fp32_path)).graph.node
        quantizable = [node for node in graph_nodes if node.op_type in {"Conv", "Gemm", "MatMul"}]
        excluded_node_names = [node.name for node in graph_nodes if node.op_type not in {"Conv", "Gemm", "MatMul"}]
        if not quantizable:
            raise RuntimeError("exported graph contains no supported weighted nodes to quantize")
        quantize_static(
            str(fp32_path), str(int8_path),
            ArrayCalibrationReader(input_name, samples),
            quant_format=QuantFormat.QDQ,
            activation_type=QuantType.QUInt8,
            weight_type=QuantType.QInt8,
            per_channel=True,
            calibrate_method=CalibrationMethod.MinMax,
            nodes_to_exclude=excluded_node_names,
        )
        int8 = ort.InferenceSession(str(int8_path), providers=providers,
                                    sess_options=_session_options(cpu_threads))

        def torch_once(sample):
            with torch.inference_mode():
                return _primary_tensor(torch_model(torch.from_numpy(sample)))

        def ort_once(session, sample):
            return _primary_tensor(session.run(None, {input_name: sample}))

        reference_output = torch_once(samples[0])
        fp_output = ort_once(fp32, samples[0])
        int8_output = ort_once(int8, samples[0])
        report = {
            "schema_version": 1,
            "type": "edge_model_export_and_quantization_host_benchmark",
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scope": "Current CPU host only; model-forward latency excludes video decode, letterboxing, NMS, rendering, persistence and OCR.",
            "target_hardware_confirmed": False,
            "detection_accuracy_measured": False,
            "identity_accuracy_claim": False,
            "host": {"platform": platform.platform(), "machine": platform.machine(),
                     "cpu": _cpu_model(), "logical_cpu_count": os.cpu_count(),
                     "torch_threads": cpu_threads, "opencv_threads": 1,
                     "torch_version": torch.__version__,
                     "ultralytics_version": __import__("ultralytics").__version__,
                     "onnxruntime_version": ort.__version__, "onnxruntime_providers": providers},
            "source_model": {"name": model_path.name, "sha256": sha256_file(model_path),
                             "bytes": model_path.stat().st_size},
            "input": {"shape": [1, 3, image_size, image_size], "layout": "RGB BCHW float32 [0,1]",
                      "sample_count": len(samples), "sources": source_records},
            "artifacts": {
                "fp32_onnx": {"sha256": sha256_file(fp32_path), "bytes": fp32_path.stat().st_size,
                              "quantization": "none", "opset": 18},
                "int8_onnx": {"sha256": sha256_file(int8_path), "bytes": int8_path.stat().st_size,
                              "quantization": "static QDQ on weighted Conv/Gemm/MatMul nodes only; output decode remains FP32",
                              "quantized_weighted_node_count": len(quantizable),
                              "excluded_non_weighted_node_count": len(excluded_node_names),
                              "activation_type": "QUInt8", "weight_type": "QInt8 per-channel",
                              "calibration_method": "MinMax",
                              "calibration_frame_count": len(samples),
                              "onnxruntime_recommended_preprocessing_applied": False},
            },
            "latency": {
                "pytorch_fp32": _latency(torch_once, samples, warmup, runs),
                "onnxruntime_fp32": _latency(lambda sample: ort_once(fp32, sample), samples, warmup, runs),
                "onnxruntime_int8": _latency(lambda sample: ort_once(int8, sample), samples, warmup, runs),
            },
            "raw_output_agreement": {
                "pytorch_vs_fp32_onnx": _drift(reference_output, fp_output),
                "fp32_vs_int8_onnx": _drift(fp_output, int8_output),
                "note": "Raw tensor drift is not detection precision/recall, OCR accuracy, or proof of equivalent decisions.",
            },
            "detection_output_agreement": _detection_agreement(fp32_path, int8_path, samples, image_size),
            "limitations": [
                "The six bundled camera clips are calibration inputs only, not held-out labeled accuracy data.",
                "This development workstation is not confirmed as the deployed edge target.",
                "The measured detector output is not integrated into the live Sakshi processor.",
                "No plate detector/OCR model export, full-pipeline latency, power, thermals, sustained-load, or dropped-frame measurement is included.",
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        _write_no_replace(output, encoded)
        return report


def _session_options(cpu_threads: int) -> ort.SessionOptions:
    options = ort.SessionOptions()
    options.intra_op_num_threads = cpu_threads
    options.inter_op_num_threads = 1
    return options


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def _write_no_replace(path: Path, data: bytes) -> None:
    import tempfile

    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--source", type=Path, action="append", default=None,
                        help="calibration video; repeat per source (default: bundled CAM-01–06 clips)")
    parser.add_argument("--output", type=Path, required=True, help="new JSON report path; never overwrites")
    parser.add_argument("--frames-per-source", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--cpu-threads", type=int, default=2)
    parser.add_argument("--image-size", type=int, default=640)
    args = parser.parse_args()
    try:
        report = run_benchmark(args.model, args.source or DEFAULT_SOURCES, args.output,
                               frames_per_source=args.frames_per_source, warmup=args.warmup,
                               runs=args.runs, cpu_threads=args.cpu_threads, image_size=args.image_size)
        print(json.dumps({"output": str(args.output), "sample_count": report["input"]["sample_count"],
                          "host": report["host"]["cpu"], "latency": report["latency"],
                          "artifacts": report["artifacts"]}, indent=2))
    except (OSError, ValueError, RuntimeError, FileExistsError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
