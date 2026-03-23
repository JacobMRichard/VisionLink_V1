"""
ObjectMemoryStore — durable per-object JSON records on disk.

Layout:
  memory_data/objects/obj_000001/
    object_memory.json
    exemplars/      (jpg copies of best crops)
    evidence/       (per-crop evidence JSON)
"""
import json
import logging
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

import app.config as config

log = logging.getLogger(__name__)


@dataclass
class ObjectRecord:
    object_uid: str
    status: str = "provisional"        # provisional | stable | named | ambiguous
    category: str = "unknown"          # rigid | soft | flat | unknown
    detector_labels_seen: List[str] = field(default_factory=list)
    semantic_label: str = ""
    user_label: str = ""
    aliases: List[str] = field(default_factory=list)
    exemplar_paths: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    color_summary: List[float] = field(default_factory=list)
    times_seen: int = 0
    first_seen_ms: int = 0
    last_seen_ms: int = 0
    confidence_score: float = 0.0
    notes: str = ""


class ObjectMemoryStore:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base = Path(base_dir or config.MEMORY_DATA_DIR) / "objects"
        self._counter_path = Path(base_dir or config.MEMORY_DATA_DIR) / "object_counter.json"
        self._base.mkdir(parents=True, exist_ok=True)
        self._counter = self._load_counter()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(
        self,
        label: str,
        confidence: float,
        color_summary: Optional[List[float]] = None,
    ) -> ObjectRecord:
        self._counter += 1
        uid = f"obj_{self._counter:06d}"
        obj_dir = self._base / uid
        obj_dir.mkdir(parents=True, exist_ok=True)
        (obj_dir / "exemplars").mkdir(exist_ok=True)
        (obj_dir / "evidence").mkdir(exist_ok=True)

        now = int(time.time() * 1000)
        rec = ObjectRecord(
            object_uid=uid,
            detector_labels_seen=[label],
            confidence_score=round(confidence, 4),
            color_summary=color_summary or [],
            times_seen=1,
            first_seen_ms=now,
            last_seen_ms=now,
        )
        self._save_counter()
        self.save(rec)
        log.info("object_memory: created %s  label=%s", uid, label)
        return rec

    def load(self, uid: str) -> Optional[ObjectRecord]:
        path = self._base / uid / "object_memory.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return ObjectRecord(**data)
        except Exception as exc:
            log.warning("object_memory: load failed %s: %s", uid, exc)
            return None

    def save(self, rec: ObjectRecord) -> None:
        obj_dir = self._base / rec.object_uid
        obj_dir.mkdir(parents=True, exist_ok=True)
        (obj_dir / "object_memory.json").write_text(
            json.dumps(asdict(rec), indent=2)
        )

    def list_uids(self) -> List[str]:
        return sorted(p.name for p in self._base.iterdir() if p.is_dir())

    # ── Exemplar management ───────────────────────────────────────────────────

    def add_exemplar(self, uid: str, crop_path: str, quality_score: float) -> None:
        """Copy crop into exemplars/ and prune to MAX_EXEMPLARS (keep newest)."""
        rec = self.load(uid)
        if rec is None:
            return
        dst = self._base / uid / "exemplars" / Path(crop_path).name
        shutil.copy2(crop_path, dst)
        existing = rec.exemplar_paths + [str(dst)]
        rec.exemplar_paths = existing[-config.MAX_EXEMPLARS:]
        self.save(rec)

    # ── Evidence ──────────────────────────────────────────────────────────────

    def add_evidence(self, uid: str, evidence: dict) -> None:
        ev_id = evidence.get("crop_id", f"ev_{int(time.time() * 1000)}")
        path  = self._base / uid / "evidence" / f"{ev_id}.json"
        path.write_text(json.dumps(evidence, indent=2))
        rec = self.load(uid)
        if rec and ev_id not in rec.evidence_ids:
            rec.evidence_ids.append(ev_id)
            self.save(rec)

    # ── Counter helpers ───────────────────────────────────────────────────────

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
