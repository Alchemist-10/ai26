"""Prepare private, prediction-blind frame labels from the current recorded sources.

Run with the backend environment. No inference, ingestion, or existing review edits.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile

import cv2

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def sample_indices(frame_count: int, count: int) -> list[int]:
    if type(frame_count) is not int or type(count) is not int or not 1 <= count <= 20 or frame_count < count:
        raise ValueError("Each source needs at least the requested 1–20 samples.")
    return [(2 * index + 1) * frame_count // (2 * count) for index in range(count)]


def capture(path: Path):
    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    if not cap.isOpened():
        cap.release()
        raise ValueError("Recorded source cannot be opened.")
    return cap


def extract(path: Path, camera: str, count: int, destination: Path) -> tuple[dict, list[dict]]:
    before = digest(path)
    cap = capture(path)
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    total = 0
    try:
        while cap.grab():
            total += 1
            if total > 200_000:
                raise ValueError("Source exceeds the bounded 200,000-frame review limit.")
    finally:
        cap.release()
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("Source has no usable nominal frame rate.")
    selected = sample_indices(total, count)
    cap = capture(path)
    samples = []
    try:
        for index in range(selected[-1] + 1):
            if not cap.grab():
                raise ValueError("Source ended before a selected frame.")
            if index not in selected:
                continue
            ok, frame = cap.retrieve()
            if not ok or frame is None:
                raise ValueError("A selected frame could not be decoded.")
            sample_id = f"{camera}-{len(samples) + 1:02d}"
            relative = f"frames/{sample_id}.jpg"
            target = destination / relative
            if not cv2.imwrite(str(target), frame, [cv2.IMWRITE_JPEG_QUALITY, 98]):
                raise ValueError("Review image could not be written.")
            samples.append({
                "sample_id": sample_id, "camera_id": camera, "source_sha256": before,
                "frame_index": index, "frame_index_basis": "zero_based_sequential_decode",
                "source_time_seconds": round(index / fps, 6),
                "source_time_basis": "frame_index_over_nominal_fps; not verified capture time",
                "width": frame.shape[1], "height": frame.shape[0],
                "image": relative, "image_sha256": digest(target),
                "decoded_bgr_sha256": hashlib.sha256(frame.tobytes()).hexdigest(),
            })
    finally:
        cap.release()
    if digest(path) != before:
        raise ValueError("Source changed during review extraction; no set published.")
    return {"source_sha256": before, "sequentially_counted_frames": total, "nominal_fps": fps}, samples


def prior_reviews(root: Path) -> list[dict]:
    reports = []
    for path in (root / "cam07-09-groundtruth-template.json", root / "followup/groundtruth-template.json"):
        if not path.is_file():
            continue
        data = json.loads(path.read_text())
        samples = data.get("samples", [])
        reports.append({"file": str(path.relative_to(ROOT)), "sha256": digest(path),
                        "samples": len(samples),
                        "review_status_counts": dict(Counter(s.get("ground_truth_status", "pending") for s in samples)),
                        "readability_counts": dict(Counter(s.get("plate_readability", "pending") for s in samples))})
    return reports


def prepare(sources: list[dict], output: Path, count: int = 5, previous: list[dict] | None = None) -> dict:
    output = output.resolve()
    if output.exists():
        raise ValueError("Output already exists. Choose a new directory; existing review work is preserved.")
    ids = [source.get("camera_id") for source in sources]
    if not sources or len(sources) > 50 or any(not isinstance(value, str) or not re.fullmatch(r"CAM-[0-9]{2}", value) for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("Provide 1–50 unique camera sources with CAM-XX identifiers.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".review-prepare-", dir=output.parent) as directory:
        staging = Path(directory)
        (staging / "frames").mkdir()
        clips, samples = [], []
        for source in sources:
            metadata, frames = extract(source["path"], source["camera_id"], count, staging)
            clips.append({**{k: v for k, v in source.items() if k != "path"}, **metadata})
            samples.extend(frames)
            print(f"Prepared {source['camera_id']}: {len(frames)} frames", flush=True)
        identity = {"sources": clips, "sample_ids": [s["sample_id"] for s in samples],
                    "frame_indices": [s["frame_index"] for s in samples]}
        set_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        manifest = {"schema_version": 1, "review_set_id": set_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "selection": "Equal-duration strata: midpoint of each of five strata per camera (or CLI count). No model predictions used.",
                    "scope": "Exploratory manual frame review. Sources may repeat vehicles; frames are correlated. No train/test independence or held-out accuracy is established.",
                    "source_clips": clips, "samples": samples, "prior_plate_reviews": previous or []}
        blank = {"schema_version": 1, "review_set_id": set_id, "reviewer": "",
                 "annotations": {s["sample_id"]: {"status": "pending", "vehicle_count": None,
                                  "vehicle_boxes_complete": False, "vehicles": [], "plates": [], "notes": ""}
                                 for s in samples}}
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (staging / "labels-template.json").write_text(json.dumps(blank, indent=2) + "\n")
        template = Path(__file__).with_name("frame-review.html").read_text()
        template = template.replace('src="frames/CAM-01-01.jpg"', f'src="{samples[0]["image"]}"')
        payload = json.dumps({"manifest": manifest, "labels": blank}).replace("<", "\\u003c")
        (staging / "index.html").write_text(template.replace("/* REVIEW_PAYLOAD */ null", payload))
        (staging / "README.md").write_text(
            "# AI26 manual frame review\n\nOpen index.html using a local HTTP server.\n"
            "1. Enter your reviewer name.\n2. Count visible cars, buses, trucks, motorcycles and bicycles. Include partial vehicles when identifiable; exclude parked-image signs/reflections.\n"
            "3. Optionally draw every vehicle box for detector scoring and tick the complete-boxes checkbox.\n"
            "4. Optionally draw plate regions, mark readability, and transcribe only readable plates.\n"
            "5. Save each frame as reviewed, or mark an unusable frame with a reason.\n"
            "6. Export labels JSON as a backup. Local browser saving is tied to this URL/browser profile.\n\n"
            "No model predictions or vehicle counts have been prefilled. These clips have already been inspected during development, so this set is exploratory, not an independent held-out test.\n"
            "Previous plate labels remain in their original private files and are not overwritten.\n")
        shutil.move(str(staging), str(output))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-camera", type=int, default=5, choices=range(1, 21))
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "backend"))
    from cameras import CAMERAS, MANAGED_SOURCES, camera_source
    sources = []
    for camera in CAMERAS:
        camera_id = camera["id"]
        path = camera_source(camera_id).resolve()
        if not path.is_file():
            raise ValueError(f"{camera_id}: recorded source is missing.")
        sources.append({"camera_id": camera_id, "path": path,
                        "source_file": str(path.relative_to(ROOT)),
                        "role": "managed_original" if camera_id in MANAGED_SOURCES else
                                "original" if path == Path(camera["path"]).resolve() else "playback_fallback",
                        "location_label_status": "overlay/catalog label; exact site not independently verified"})
    manifest = prepare(sources, args.output, args.per_camera, prior_reviews(ROOT / "backend/data/review"))
    print(f"Ready: {len(manifest['samples'])} frames in {args.output.resolve()}")


if __name__ == "__main__":
    main()
