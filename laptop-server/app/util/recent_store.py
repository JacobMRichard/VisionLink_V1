import json
import threading
import time
from collections import deque
from pathlib import Path


class RecentStore:
    """Thread-safe rolling JSON store. Keeps the latest N records, flushes to disk on each push."""

    def __init__(self, path: Path, key: str, window: int = 50) -> None:
        self._path = path
        self._key = key
        self._window = window
        self._records: deque = deque(maxlen=window)
        self._lock = threading.Lock()

    def push(self, record: dict) -> None:
        with self._lock:
            self._records.append(record)
            self._flush()

    def _flush(self) -> None:
        data = {
            "updated_at": round(time.time() * 1000),
            "window": self._window,
            self._key: list(self._records),
        }
        self._path.write_text(json.dumps(data, indent=2))


class ExceptionsLog:
    """Appends exception text and tracebacks to a plain text file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def record(self, component: str, message: str, traceback_str: str = "") -> None:
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        lines = [f"[{ts}] [{component}] {message}\n"]
        if traceback_str:
            lines.append(traceback_str.rstrip() + "\n")
        lines.append("-" * 60 + "\n")
        text = "".join(lines)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(text)
