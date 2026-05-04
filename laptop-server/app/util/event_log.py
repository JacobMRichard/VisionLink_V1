import json
import queue
import threading
import time
from pathlib import Path
from typing import Any


class EventLog:
    """
    Thread-safe, non-blocking JSONL event log.
    All callers return instantly — a daemon thread handles disk writes.
    Batches multiple entries into a single file open when writes back up.
    """

    _SENTINEL = object()

    def __init__(self, path: Path, session_id: str) -> None:
        self._path = path
        self._session_id = session_id
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._thread = threading.Thread(target=self._writer, daemon=True, name="event-log-writer")
        self._thread.start()

    def log(self, component: str, level: str, event: str, **kwargs: Any) -> None:
        entry = {
            "ts":         round(time.time() * 1000),
            "session_id": self._session_id,
            "component":  component,
            "level":      level,
            "event":      event,
            **kwargs,
        }
        self._queue.put(json.dumps(entry) + "\n")

    def close(self) -> None:
        """Flush remaining entries and stop the writer thread. Call once at shutdown."""
        self._queue.put(self._SENTINEL)
        self._thread.join(timeout=3.0)

    def _writer(self) -> None:
        while True:
            item = self._queue.get()
            if item is self._SENTINEL:
                break
            try:
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(item)
                    # Drain any additional entries that arrived while we had the file open.
                    while True:
                        try:
                            next_item = self._queue.get_nowait()
                            if next_item is self._SENTINEL:
                                return
                            f.write(next_item)
                        except queue.Empty:
                            break
            except Exception:
                pass
