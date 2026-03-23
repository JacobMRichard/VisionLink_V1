import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


class Exporter:
    _FILES = [
        "config_snapshot.json",
        "events.jsonl",
        "recent_timings.json",
        "recent_metadata.json",
        "exceptions.txt",
    ]

    def __init__(self, session_folder: Path) -> None:
        self._folder = session_folder

    def export(self) -> Path:
        bundle = self._folder / "export_bundle"
        bundle.mkdir(exist_ok=True)

        for name in self._FILES:
            src = self._folder / name
            if src.exists():
                shutil.copy2(src, bundle / name)

        manifest = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "session_folder": str(self._folder),
            "files": sorted(f.name for f in bundle.iterdir()),
        }
        (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return bundle
