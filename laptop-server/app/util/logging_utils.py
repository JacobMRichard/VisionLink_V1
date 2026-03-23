import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(level: int = logging.DEBUG) -> None:
    fmt = "%(asctime)s.%(msecs)03d  %(levelname)-8s  %(name)s  %(message)s"
    datefmt = "%H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Console: INFO and above
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root.addHandler(console)

    # File: DEBUG and above, rotating 5 MB × 3 files
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "visionlink.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
