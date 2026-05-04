import logging
import sys
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
from pathlib import Path
from queue import Queue

# Loggers that belong to the phone side (frame RX, WebSocket connect/disconnect/broadcast).
# Everything else is laptop-side (YOLO, tracker, pipeline, buffer, main).
_PHONE_LOGGERS = frozenset({
    "app.networking.video_server",
    "app.networking.metadata_server",
})

_listener: QueueListener | None = None


class _PhoneFilter(logging.Filter):
    """Only pass phone-side records."""
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name in _PHONE_LOGGERS


class _LaptopFilter(logging.Filter):
    """Only pass laptop-side records (everything that is NOT phone-only)."""
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name not in _PHONE_LOGGERS


class _ConsoleFilter(logging.Filter):
    """
    Console shows:
      - DEBUG+ for our own app.* / main / processing_loop loggers
      - INFO+  for third-party libs (torch, ultralytics, aiohttp, etc.)
    """
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith("app") or record.name in ("main", "processing_loop"):
            return True
        return record.levelno >= logging.INFO


def setup_logging() -> None:
    global _listener

    fmt = "%(asctime)s.%(msecs)03d  %(levelname)-8s  %(name)s  %(message)s"
    datefmt = "%H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # ── Console ───────────────────────────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG)
    console.addFilter(_ConsoleFilter())
    console.setFormatter(formatter)

    # ── laptop.log  (YOLO, pipeline, tracker, frame buffer, main) ────────────
    laptop_fh = RotatingFileHandler(
        log_dir / "laptop.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    laptop_fh.setLevel(logging.DEBUG)
    laptop_fh.addFilter(_LaptopFilter())
    laptop_fh.setFormatter(formatter)

    # ── phone.log  (frame RX, WebSocket connections, broadcasts) ─────────────
    phone_fh = RotatingFileHandler(
        log_dir / "phone.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    phone_fh.setLevel(logging.DEBUG)
    phone_fh.addFilter(_PhoneFilter())
    phone_fh.setFormatter(formatter)

    # ── Async queue — loggers push here instantly, background thread writes ───
    # This means YOLO inference / pipeline code never waits on disk I/O.
    log_queue: Queue = Queue()
    _listener = QueueListener(
        log_queue,
        console,
        laptop_fh,
        phone_fh,
        respect_handler_level=True,
    )
    _listener.start()

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(QueueHandler(log_queue))


def stop_logging() -> None:
    """Flush and close the background log writer. Call during shutdown."""
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None
