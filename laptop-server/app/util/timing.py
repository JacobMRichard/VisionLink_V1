from collections import deque
import time


class FpsCounter:
    """Rolling-window FPS counter."""

    def __init__(self, window: int = 30):
        self._times: deque = deque(maxlen=window)
        self._last: float | None = None

    def tick(self) -> float:
        now = time.monotonic()
        if self._last is not None:
            self._times.append(now - self._last)
        self._last = now
        if not self._times:
            return 0.0
        return round(len(self._times) / sum(self._times), 1)
