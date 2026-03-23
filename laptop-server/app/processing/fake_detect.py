"""
Fake detector for Step 1 of bringup: verify overlay scaling and WebSocket
return path independently of real computer vision.

Usage: set FAKE_DETECTION_MODE = True in config.py.
The laptop will generate a slowly oscillating bounding box and send it back
to the phone without doing any OpenCV work.
"""
import math
import time

from app.networking.models import DetectedObject, BBox


class FakeDetector:
    """Produces a single animated bbox that bounces horizontally."""

    def detect(self, width: int, height: int) -> list[DetectedObject]:
        t = time.time()
        # Oscillate between 20% and 70% of the frame width
        cx = int(width * (0.45 + 0.25 * math.sin(t * 1.2)))
        cy = int(height * 0.5)
        w = int(width * 0.22)
        h = int(height * 0.35)
        x = cx - w // 2
        y = cy - h // 2

        return [
            DetectedObject(
                id=1,
                label="fake",
                confidence=1.0,
                bbox=BBox(x=max(x, 0), y=max(y, 0), w=w, h=h),
                centroid=(cx, cy),
            )
        ]
