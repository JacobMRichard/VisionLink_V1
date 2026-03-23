"""
SnapshotDetector — runs YOLO detection on a frozen snapshot image.

Reuses detect_yolo() from the live pipeline but runs it on a saved
still frame rather than a live stream frame.

Saves:  snap_dir/detections.json
"""
import json
import logging
from pathlib import Path
from typing import List

import cv2

from app.processing.detect import detect_yolo
from app.processing.tracked_object import RawDetection

log = logging.getLogger(__name__)


def run(snap_dir: Path, full_image_path: Path) -> List[RawDetection]:
    """
    Decode the saved full image, run YOLO, persist detections.json.
    Returns a list of RawDetection objects.
    """
    img = cv2.imread(str(full_image_path))
    if img is None:
        log.error("snapshot_detector: failed to read image %s", full_image_path)
        return []

    detections = detect_yolo(img)

    det_records = [
        {
            "label":       d.label,
            "confidence":  round(d.confidence, 4),
            "bbox_x":      d.bbox_x,
            "bbox_y":      d.bbox_y,
            "bbox_w":      d.bbox_w,
            "bbox_h":      d.bbox_h,
            "centroid_x":  d.centroid_x,
            "centroid_y":  d.centroid_y,
            "floor_score": round(d.floor_score, 4),
        }
        for d in detections
    ]
    (snap_dir / "detections.json").write_text(json.dumps(det_records, indent=2))
    log.info("snapshot_detector: %d detections  snap=%s", len(detections), snap_dir.name)
    return detections
