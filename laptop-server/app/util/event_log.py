import json
import threading
import time
from pathlib import Path
from typing import Any


class EventLog:
    """Thread-safe JSONL event log. One JSON object per line."""

    def __init__(self, path: Path, session_id: str) -> None:
        self._path = path
        self._session_id = session_id
        self._lock = threading.Lock()

    def log(self, component: str, level: str, event: str, **kwargs: Any) -> None:
        entry = {
            "ts": round(time.time() * 1000),
            "session_id": self._session_id,
            "component": component,
            "level": level,
            "event": event,
            **kwargs,
        }
        line = json.dumps(entry) + "\n"
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)
