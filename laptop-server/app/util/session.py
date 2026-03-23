import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import app.config as config


class Session:
    """Creates a unique per-run folder and saves a config snapshot at startup."""

    def __init__(self) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:6]
        self.session_id = f"{ts}_{uid}"
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.folder = Path("sessions") / self.session_id
        self.folder.mkdir(parents=True, exist_ok=True)
        self._save_config_snapshot()

    def _save_config_snapshot(self) -> None:
        snapshot = {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "host": config.HOST,
            "frame_port": config.FRAME_PORT,
            "metadata_port": config.METADATA_PORT,
            "target_fps": config.TARGET_FPS,
            "frame_width": config.FRAME_WIDTH,
            "frame_height": config.FRAME_HEIGHT,
            "jpeg_quality": config.JPEG_QUALITY,
            "debug_window": config.DEBUG_WINDOW,
            "fake_detection_mode": config.FAKE_DETECTION_MODE,
        }
        (self.folder / "config_snapshot.json").write_text(json.dumps(snapshot, indent=2))

    @property
    def events_path(self) -> Path:
        return self.folder / "events.jsonl"

    @property
    def recent_timings_path(self) -> Path:
        return self.folder / "recent_timings.json"

    @property
    def recent_metadata_path(self) -> Path:
        return self.folder / "recent_metadata.json"

    @property
    def exceptions_path(self) -> Path:
        return self.folder / "exceptions.txt"
