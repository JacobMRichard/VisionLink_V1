import logging
import time
from typing import List

import numpy as np

import app.config as config
from app.processing.tracked_object import RawDetection
from app.runtime_config import RuntimeConfig

log = logging.getLogger(__name__)

_model = None


def load_model():
    """
    Load YOLOv8 model. Blocking — call once at startup before server accepts frames.
    ultralytics auto-downloads yolov8n.pt (~6 MB) to ~/.cache/ultralytics/ on first run.
    """
    global _model
    log.info("Loading YOLO model: %s  (first run downloads ~6 MB)", config.MODEL_PATH)
    from ultralytics import YOLO
    _model = YOLO(config.MODEL_PATH)
    log.info("YOLO model ready")
    return _model


def detect_yolo(frame: np.ndarray) -> List[RawDetection]:
    """
    Run YOLOv8 inference on a BGR frame.
    Applies live confidence threshold and class filter from RuntimeConfig.
    Returns RawDetections sorted by confidence descending.
    """
    if _model is None:
        log.warning("detect_yolo called but model is not loaded")
        return []

    frame_h, frame_w = frame.shape[:2]
    confidence = RuntimeConfig.get_confidence()
    class_filter = RuntimeConfig.get_class_filter()

    log.debug("yolo  start  frame=%dx%d  conf=%.2f  filter=%s",
              frame_w, frame_h, confidence,
              sorted(class_filter) if class_filter else "all")

    t0 = time.monotonic()
    results = _model(frame, conf=confidence, verbose=False)
    elapsed_ms = (time.monotonic() - t0) * 1000

    detections: List[RawDetection] = []
    for result in results:
        for box in result.boxes:
            label = result.names[int(box.cls[0])]

            # Apply live class filter
            if class_filter and label.lower() not in class_filter:
                continue

            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            w = max(x2 - x1, 1)
            h = max(y2 - y1, 1)
            cx, cy = x1 + w // 2, y1 + h // 2
            conf = float(box.conf[0])

            detections.append(RawDetection(
                label=label,
                confidence=conf,
                bbox_x=x1,
                bbox_y=y1,
                bbox_w=w,
                bbox_h=h,
                centroid_x=cx,
                centroid_y=cy,
                floor_score=cy / frame_h,
            ))

    sorted_dets = sorted(detections, key=lambda d: d.confidence, reverse=True)
    log.debug("yolo  done  inference=%.0f ms  detections=%d  labels=%s",
              elapsed_ms, len(sorted_dets),
              [f"{d.label}({d.confidence:.2f})" for d in sorted_dets])
    return sorted_dets
