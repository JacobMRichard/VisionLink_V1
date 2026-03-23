import logging
import threading
from typing import List

import numpy as np

import app.config as config
from app.processing.tracked_object import RawDetection

log = logging.getLogger(__name__)

_model = None
# Serialise YOLO calls across threads (live pipeline + snapshot pipeline share one model).
# ultralytics/PyTorch inference is not thread-safe on a single model instance.
_model_lock = threading.Lock()


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
    Returns RawDetections sorted by confidence descending.
    Returns [] if model not loaded or no detections above threshold.
    """
    if _model is None:
        return []

    frame_h, frame_w = frame.shape[:2]
    with _model_lock:
        results = _model(frame, conf=config.CONFIDENCE_THRESHOLD, verbose=False)

    detections: List[RawDetection] = []
    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            w = max(x2 - x1, 1)
            h = max(y2 - y1, 1)
            cx, cy = x1 + w // 2, y1 + h // 2
            conf = float(box.conf[0])
            label = result.names[int(box.cls[0])]

            detections.append(RawDetection(
                label=label,
                confidence=conf,
                bbox_x=x1,
                bbox_y=y1,
                bbox_w=w,
                bbox_h=h,
                centroid_x=cx,
                centroid_y=cy,
                floor_score=cy / frame_h,  # 0.0 = top, 1.0 = bottom
            ))

    return sorted(detections, key=lambda d: d.confidence, reverse=True)
