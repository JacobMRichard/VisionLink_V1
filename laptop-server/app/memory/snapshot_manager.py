"""
SnapshotManager — saves a full JPEG frame to disk and assigns a snapshot_id.

Storage layout:
  memory_data/snapshots/snap_000001/
    full.jpg
    snapshot_meta.json
"""
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import app.config as config

log = logging.getLogger(__name__)


@dataclass
class SnapshotMeta:
    snapshot_id: str
    timestamp_ms: int
    frame_id: int
    width: int
    height: int
    rotation_degrees: int
    full_image_path: str
    session_id: str = ""


class SnapshotManager:
    def __init__(self, base_dir: str | None = None) -> None:
        self._base = Path(base_dir or config.MEMORY_DATA_DIR) / "snapshots"
        self._counter_path = Path(base_dir or config.MEMORY_DATA_DIR) / "snapshot_counter.json"
        self._base.mkdir(parents=True, exist_ok=True)
        self._counter = self._load_counter()

    def save(
        self,
        jpeg_bytes: bytes,
        frame_id: int,
        timestamp_ms: int,
        width: int,
        height: int,
        rotation_degrees: int = 0,
        session_id: str = "",
    ) -> tuple[str, Path]:
        """Save full-frame JPEG, return (snapshot_id, snap_dir)."""
        self._counter += 1
        snap_id = f"snap_{self._counter:06d}"
        snap_dir = self._base / snap_id
        snap_dir.mkdir(parents=True, exist_ok=True)

        img_path = snap_dir / "full.jpg"
        img_path.write_bytes(jpeg_bytes)

        meta = SnapshotMeta(
            snapshot_id=snap_id,
            timestamp_ms=timestamp_ms or int(time.time() * 1000),
            frame_id=frame_id,
            width=width,
            height=height,
            rotation_degrees=rotation_degrees,
            full_image_path=str(img_path),
            session_id=session_id,
        )
        (snap_dir / "snapshot_meta.json").write_text(
            json.dumps(asdict(meta), indent=2)
        )
        self._save_counter()
        log.info("snapshot saved  id=%s  path=%s", snap_id, snap_dir)
        return snap_id, snap_dir

    def _load_counter(self) -> int:
        if self._counter_path.exists():
            try:
                return json.loads(self._counter_path.read_text()).get("count", 0)
            except Exception:
                pass
        return 0

    def _save_counter(self) -> None:
        self._counter_path.parent.mkdir(parents=True, exist_ok=True)
        self._counter_path.write_text(json.dumps({"count": self._counter}))
