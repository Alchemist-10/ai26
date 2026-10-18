"""Bounded cold/warm ALPR runtime sample. Never writes OCR text or image crops."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import tempfile
import time


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return None
    return {
        'samples': len(ordered),
        'median_ms': round(statistics.median(ordered), 3),
        'p95_ms': round(ordered[math.ceil(len(ordered) * .95) - 1], 3),
        'max_ms': round(ordered[-1], 3),
    }


def run(video, max_frames, stride_seconds, cpu_threads):
    imports_started = time.perf_counter()
    import cv2
    import numpy as np
    import onnxruntime as ort
    import torch
    from model_provenance import load_plate_model
    dependency_import_ms = (time.perf_counter() - imports_started) * 1000

    if not video.is_file():
        raise ValueError('Input video is not a regular file')
    source_digest = digest(video)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        cap.release()
        raise ValueError('OpenCV could not open the input video')
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not math.isfinite(fps) or fps <= 0 or frame_count <= 0:
        cap.release()
        raise ValueError('Input video has invalid FPS or frame count')
    duration = frame_count / fps
    indices = []
    current = 0.0
    while current < duration and len(indices) < max_frames:
        indices.append(min(frame_count - 1, round(current * fps)))
        current += stride_seconds
    indices = sorted(set(indices))
    if not indices:
        cap.release()
        raise ValueError('Input video contains no sampleable frames')

    torch.set_num_threads(cpu_threads)
    with tempfile.TemporaryDirectory(prefix='ai26-alpr-runtime-') as temporary_data:
        os.environ['AI26_DATA_ROOT'] = temporary_data
        load_started = time.perf_counter()
        model, metadata = load_plate_model(Path(temporary_data) / 'models', cpu_threads=cpu_threads, device='cpu')
        model_load_ms = (time.perf_counter() - load_started) * 1000

        samples = []
        detection_count = 0
        first_predict_ms = None
        for index in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            decode_started = time.perf_counter()
            ok, frame = cap.read()
            decode_ms = (time.perf_counter() - decode_started) * 1000
            if not ok or frame is None or not isinstance(frame, np.ndarray):
                continue
            started = time.perf_counter()
            predictions = model.predict(frame)
            predict_ms = (time.perf_counter() - started) * 1000
            if first_predict_ms is None:
                first_predict_ms = predict_ms
            detection_count += len(predictions)
            ocr_result_count = sum(prediction.ocr is not None for prediction in predictions)
            samples.append({
                'frame_index': index,
                'source_time_seconds': round(index / fps, 4),
                'decode_ms': round(decode_ms, 3),
                'alpr_predict_ms': round(predict_ms, 3),
                'plate_detections': len(predictions),
                'ocr_results': ocr_result_count,
            })
        cap.release()

        # Exercise the installed character recognizer with synthetic pixels so its
        # runtime can be measured even if the video contains no detected plates.
        synthetic_crop = np.full((72, 320, 3), 255, dtype=np.uint8)
        cv2.rectangle(synthetic_crop, (2, 2), (317, 69), (0, 0, 0), 2)
        cv2.putText(synthetic_crop, 'KL 07 AB 1234', (12, 48), cv2.FONT_HERSHEY_SIMPLEX,
                    1.05, (0, 0, 0), 2, cv2.LINE_AA)
        synthetic_ocr_samples = []
        synthetic_first_ocr_ms = None
        for _ in range(min(max_frames, 24)):
            started = time.perf_counter()
            model.ocr.predict(synthetic_crop)
            elapsed_ms = (time.perf_counter() - started) * 1000
            if synthetic_first_ocr_ms is None:
                synthetic_first_ocr_ms = elapsed_ms
            else:
                synthetic_ocr_samples.append(elapsed_ms)

    if not samples:
        raise ValueError('No frames could be decoded for the requested sample')
    warm_samples = samples[1:]
    return {
        'version': 1,
        'scope': 'Single-process CPU ALPR latency on sampled frames; not OCR accuracy, a live six-camera test, or a browser measurement.',
        'source': {
            'filename': video.name,
            'sha256': source_digest,
            'width': width,
            'height': height,
            'reported_fps': round(fps, 6),
            'frame_count': frame_count,
            'duration_seconds': round(duration, 4),
        },
        'conditions': {
            'python': platform.python_version(),
            'platform': platform.platform(),
            'logical_cpus': os.cpu_count(),
            'device': 'CPUExecutionProvider',
            'cpu_threads': cpu_threads,
            'onnxruntime_version': ort.__version__,
            'model_metadata': metadata,
            'requested_max_frames': max_frames,
            'requested_stride_seconds': stride_seconds,
            'sampled_frames': len(samples),
        },
        'timing': {
            'base_runtime_import_ms': round(dependency_import_ms, 3),
            'alpr_import_session_and_preflight_ms': round(model_load_ms, 3),
            'first_prediction_ms': round(first_predict_ms, 3),
            'decode': distribution([sample['decode_ms'] for sample in samples]),
            'prediction_all': distribution([sample['alpr_predict_ms'] for sample in samples]),
            'prediction_after_first': distribution([sample['alpr_predict_ms'] for sample in warm_samples]),
            'synthetic_ocr_first_prediction_ms': round(synthetic_first_ocr_ms, 3),
            'synthetic_ocr_after_first': distribution(synthetic_ocr_samples),
        },
        'aggregate': {
            'decoded_samples': len(samples),
            'plate_detection_count': detection_count,
            'detected_plate_ocr_result_count': sum(sample['ocr_results'] for sample in samples),
            'synthetic_ocr_calls': len(synthetic_ocr_samples) + (1 if synthetic_first_ocr_ms is not None else 0),
            'ocr_text_recorded': False,
        },
        'samples': samples,
        'limitations': [
            'No OCR strings, boxes, crops, or images are recorded.',
            'The input clip may not contain readable plates; detection count is not a quality metric.',
            'Synthetic OCR timings use one in-memory generated crop and do not measure accuracy or real plate image quality.',
            'The first predictions include provider warm-up and are reported separately.',
            'This isolated benchmark does not measure the shared six-camera scheduler, browser playback, or target hardware.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--max-frames', type=int, default=24)
    parser.add_argument('--stride-seconds', type=float, default=1.0)
    parser.add_argument('--cpu-threads', type=int, default=2)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.max_frames <= 120:
        parser.error('--max-frames must be 1–120')
    if not math.isfinite(args.stride_seconds) or not .1 <= args.stride_seconds <= 60:
        parser.error('--stride-seconds must be .1–60')
    if not 1 <= args.cpu_threads <= 8:
        parser.error('--cpu-threads must be 1–8')
    try:
        result = run(args.video.resolve(), args.max_frames, args.stride_seconds, args.cpu_threads)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f'ALPR profile failed: {error}\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(f"{result['aggregate']['decoded_samples']} frames; ALPR init/preflight={result['timing']['alpr_import_session_and_preflight_ms']} ms; output={args.output}")


if __name__ == '__main__':
    main()
