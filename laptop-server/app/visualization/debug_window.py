import cv2
import numpy as np
from typing import List

from app.networking.models import DetectedObject


class DebugWindow:
    """Optional laptop-side OpenCV window showing detections in real time."""

    def __init__(self, name: str = "VisionLink Debug"):
        self.name = name

    def show(self, frame: np.ndarray, objects: List[DetectedObject]) -> None:
        display = frame.copy()
        for obj in objects:
            x, y, w, h = obj.bbox.x, obj.bbox.y, obj.bbox.w, obj.bbox.h
            cx, cy = obj.centroid
            cv2.rectangle(display, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.circle(display, (cx, cy), 6, (0, 0, 255), -1)
            cv2.putText(
                display,
                f"{obj.label} {obj.confidence:.2f}",
                (x, max(y - 10, 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
            )
        cv2.imshow(self.name, display)
        cv2.waitKey(1)

    def close(self) -> None:
        cv2.destroyWindow(self.name)
