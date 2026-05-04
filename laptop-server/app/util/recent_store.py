import json
import threading
import time
from collections import deque
from pathlib import Path


class RecentStore:
    """
    Thread-safe rolling JSON store. Keeps the latest N records.
    Writes are non-blocking — a daemon thread coalesces and flushes to disk.
    Multiple rapid pushes are batched into a single disk write.
    """

    def __init__(self, path: Path, key: str, window: int = 50) -> None:
        self._path = path
        self._key = key
        self._window = window
        self._records: deque = deque(maxlen=window)
        self._lock = threading.Lock()
        self._dirty = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._flusher, daemon=True, name=f"recent-store-{key}")
        self._thread.start()

    def push(self, record: dict) -> None:
        with self._lock:
            self._records.append(record)
        self._dirty.set()

    def flush_now(self) -> None:
        """Synchronous flush — call at shutdown to ensure final data is written."""
        self._stop.set()
        self._thread.join(timeout=3.0)
        self._write()

    def _flusher(self) -> None:
        while not self._stop.is_set():
            self._dirty.wait(timeout=1.0)
            if not self._dirty.is_set():
                continue
            self._dirty.clear()
            # Brief coalesce: let rapid successive pushes batch into one write.
            time.sleep(0.05)
            self._write()

    def _write(self) -> None:
        with self._lock:
            records = list(self._records)
        data = {
            "updated_at": round(time.time() * 1000),
            "window":     self._window,
            self._key:    records,
        }
        try:
            self._path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass


class ExceptionsLog:
    """Appends exception text and tracebacks to a plain text file. Synchronous — exceptions are rare."""

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
