import time
import os
import hashlib
from importlib.metadata import version
from pathlib import Path
from collections import defaultdict

import cv2
import torch
from ultralytics import YOLO

from plate_format import normalize_plate
from tracking import CentroidTracker, TRACKER_VERSION
from model_provenance import load_plate_model, pipeline_components

VEHICLE_CLASS_IDS = {2, 3, 5, 7}  # car, motorcycle, bus, truck (COCO)
DEVICE = 0 if torch.cuda.is_available() else "cpu"
CPU_THREADS = max(1,min(8,int(os.environ.get('AI26_CPU_THREADS','2'))))
if DEVICE == 'cpu': torch.set_num_threads(CPU_THREADS)
cv2.setNumThreads(1)

# Canonical reads are retained independently of per-track identity consensus.
from fusion import PlateConsensus
PLATE_MIN_CONF = 0.35
_consensus = PlateConsensus()
_vehicle_trackers: dict[str, CentroidTracker] = defaultdict(CentroidTracker)
_plate_trackers: dict[str, CentroidTracker] = defaultdict(lambda: CentroidTracker(max_distance=90))

_checkpoint = Path(__file__).parent / "yolov8n.pt"
_yolo = YOLO(str(_checkpoint))
with _checkpoint.open('rb') as _model_file:
    _checkpoint_hash = hashlib.file_digest(_model_file, 'sha256').hexdigest()
_pipeline_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_pipeline_components = pipeline_components(Path(__file__).parent)
_model_metadata = {"checkpoint_sha256": _checkpoint_hash, "torch_version": str(torch.__version__), "cpu_threads": CPU_THREADS, "tracker_version": TRACKER_VERSION,
                   "ultralytics_version": version("ultralytics"), "pipeline_sha256": _pipeline_hash,
                   "pipeline_components_sha256":_pipeline_components}
_alpr = None
_alpr_metadata = None
_fast_alpr_version = version('fast-alpr')

def _plate_model():
    global _alpr, _alpr_metadata
    if _alpr is None:
        model,metadata = load_plate_model(cpu_threads=CPU_THREADS,device=DEVICE)
        _alpr, _alpr_metadata = model,metadata
    return _alpr

def _plate_metadata():
    return {**(_alpr_metadata or {'weight_provenance_status':'unavailable'}),
            'fast_alpr_version':_fast_alpr_version, 'pipeline_sha256':_pipeline_hash,
            'pipeline_components_sha256':_pipeline_components, 'tracker_version':TRACKER_VERSION}

def reset_camera(camera_id):
    _vehicle_trackers.pop(camera_id, None)
    _plate_trackers.pop(camera_id, None)
    _consensus.reset(camera_id)

ACCENT = (200, 211, 34)  # BGR, matches the detection overlay accent
CRIT = (114, 92, 255)


def annotate_vehicle_frame(frame, camera_id: str):
    """Runs real YOLO vehicle detection, draws boxes, returns (frame, detections)."""
    results = _yolo.predict(frame, device=DEVICE, verbose=False, classes=list(VEHICLE_CLASS_IDS), conf=0.4)
    # Ultralytics resets the thread count during its first predictor setup. Restore
    # the desktop budget for subsequent inference; no global library patch needed.
    if DEVICE == 'cpu' and torch.get_num_threads()!=CPU_THREADS: torch.set_num_threads(CPU_THREADS)
    detections = []
    r = results[0]
    raw_detections = []
    for box in r.boxes:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0]]
        label = _yolo.names[cls_id]
        raw_detections.append({"label": label, "bbox": [x1, y1, x2, y2], "confidence": conf})

    for detection in _vehicle_trackers[camera_id].update(raw_detections, timestamp=time.monotonic()):
        label = detection["label"]
        x1, y1, x2, y2 = detection["bbox"]
        conf = detection["confidence"]
        history = detection["track_history"]
        for start, end in zip(history, history[1:]):
            cv2.line(frame, start, end, ACCENT, 2, cv2.LINE_AA)
        cv2.rectangle(frame, (x1, y1), (x2, y2), ACCENT, 2)
        tag = f"#{detection['track_id']} {label} {conf * 100:.0f}%"
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), ACCENT, -1)
        cv2.putText(frame, tag, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (10, 10, 10), 1, cv2.LINE_AA)
        detections.append({
            "camera_id": camera_id,
            "kind": "vehicle",
            "model_metadata": _model_metadata,
            "label": label,
            "confidence": round(conf, 3),
            "track_id": detection["track_id"],
            "association_status": detection["association_status"],
            "association_cost": detection["association_cost"],
            "bbox": [x1, y1, x2, y2],
            "ts": time.time(),
        })
    return frame, detections


def annotate_plate_frame(frame, camera_id: str):
    """Runs real Fast-ALPR plate detection+OCR, draws boxes, returns (frame, detections)."""
    results = _plate_model().predict(frame)
    model_metadata = _plate_metadata()
    detections = []
    raw_detections = []
    for res in results:
        bb = res.detection.bounding_box
        x1, y1, x2, y2 = int(bb.x1), int(bb.y1), int(bb.x2), int(bb.y2)
        plate_text = res.ocr.text if res.ocr else "?"
        ocr_conf = res.ocr.confidence if res.ocr else 0.0
        if isinstance(ocr_conf, list):
            ocr_conf = sum(ocr_conf) / len(ocr_conf) if ocr_conf else 0.0
        ocr_conf = float(ocr_conf)

        normalized = normalize_plate(plate_text)
        raw_detections.append({
            "label": "plate",
            "bbox": [x1, y1, x2, y2],
            "plate_text": plate_text,
            "ocr_conf": ocr_conf,
            "normalized": normalized,
        })

    for detection in _plate_trackers[camera_id].update(raw_detections, timestamp=time.monotonic()):
        x1, y1, x2, y2 = detection["bbox"]
        plate_text = detection["plate_text"]
        ocr_conf = detection["ocr_conf"]
        normalized = detection["normalized"]
        for start, end in zip(detection["track_history"], detection["track_history"][1:]):
            cv2.line(frame, start, end, CRIT, 2, cv2.LINE_AA)
        cv2.rectangle(frame, (x1, y1), (x2, y2), CRIT, 2)
        if ocr_conf < PLATE_MIN_CONF or not normalized["format_valid"] or detection["association_status"] == "ambiguous":
            tag = f"PLATE DETECTED #{detection['track_id']} {ocr_conf * 100:.0f}%"
            (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), CRIT, -1)
            cv2.putText(frame, tag, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
            # Keep failed reads for review/evaluation; they never enter identity queries.
            detections.append({"camera_id": camera_id, "kind": "plate", "plate_raw": plate_text,
                               "plate_norm": str(normalized["plate_norm"]) if normalized["format_valid"] else None,
                               "format_valid": normalized["format_valid"], "repairs": normalized["repairs"],
                               "identity_status": "tracking_ambiguous" if detection["association_status"] == "ambiguous" else "low_confidence" if ocr_conf < PLATE_MIN_CONF else "invalid",
                               "confidence": round(ocr_conf, 3), "bbox": [x1,y1,x2,y2],
                               "track_id": detection["track_id"], "association_status": detection["association_status"],
                               "association_cost": detection["association_cost"], "ts": time.time(),
                               "model_metadata": model_metadata})
            continue

        plate_norm = str(normalized["plate_norm"])
        consensus = _consensus.read(camera_id, detection["track_id"], plate_norm, detection["association_status"])
        fused_text = plate_norm

        tag = f"PLATE #{detection['track_id']} {fused_text} {ocr_conf * 100:.0f}%"
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), CRIT, -1)
        cv2.putText(frame, tag, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        detections.append({
            "camera_id": camera_id,
            "kind": "plate",
            **consensus,
            "model_metadata": model_metadata,
            "plate": plate_norm,
            "plate_norm": plate_norm,
            "plate_raw": plate_text,
            "format_valid": True,
            "repairs": normalized["repairs"],
            "track_id": detection["track_id"],
            "association_status": detection["association_status"],
            "association_cost": detection["association_cost"],
            "confidence": round(ocr_conf, 3),
            "bbox": [x1, y1, x2, y2],
            "ts": time.time(),
        })
    _consensus.retain(camera_id, _plate_trackers[camera_id].active_ids)
    return frame, detections
