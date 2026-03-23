import time
from app.util.timing import FpsCounter


class MetricsTracker:
    """Tracks per-frame FPS and round-trip latency."""

    def __init__(self):
        self._fps_counter = FpsCounter(window=30)

    def update(self, frame_timestamp_ms: int) -> tuple[float, float]:
        """
        Returns (fps, latency_ms).
        latency_ms is the time from when the phone captured the frame to now.
        """
        fps = self._fps_counter.tick()
        latency_ms = max(0.0, time.time() * 1000 - frame_timestamp_ms)
        return fps, round(latency_ms, 1)
