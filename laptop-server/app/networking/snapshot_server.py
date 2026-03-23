"""
SnapshotServer — handles POST /snapshot from the Android phone.

When SNAP is pressed on the phone, it POSTs the current JPEG frame here.
The server runs the full V2 memory pipeline:

  receive → save → detect → crop → quality → descriptors → match → update → report

The pipeline runs in a ThreadPoolExecutor (max_workers=1) so it never
blocks the async event loop used by the live frame/metadata servers.
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import cv2
import numpy as np
from aiohttp import web

import app.config as config
from app.memory.audit_reporter import AuditReporter
from app.memory.crop_extractor import extract as extract_crops
from app.memory.crop_quality import score_all as score_crops
from app.memory.descriptor_extractor import extract as extract_descriptor
from app.memory.embedding_index import EmbeddingIndex
from app.memory.identity_matcher import IdentityMatcher
from app.memory.memory_updater import MemoryUpdater
from app.memory.object_memory_store import ObjectMemoryStore
from app.memory.snapshot_detector import run as run_detector
from app.memory.snapshot_manager import SnapshotManager

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="snapshot")


class SnapshotServer:
    def __init__(self, diag=None) -> None:
        self._diag     = diag
        self._snap_mgr = SnapshotManager()
        self._store    = ObjectMemoryStore()
        self._index    = EmbeddingIndex()
        self._matcher  = IdentityMatcher(self._store, self._index)
        self._updater  = MemoryUpdater(self._store, self._index)
        self._reporter = AuditReporter()
        log.info("SnapshotServer ready  memory_dir=%s", config.MEMORY_DATA_DIR)

    async def handle_snapshot(self, request: web.Request) -> web.Response:
        jpeg_bytes = await request.read()
        if not jpeg_bytes:
            return web.Response(status=400, text="empty body")

        frame_id     = int(request.headers.get("X-Frame-Id", 0))
        timestamp_ms = int(request.headers.get("X-Timestamp-Ms", 0))
        width        = int(request.headers.get("X-Width", config.FRAME_WIDTH))
        height       = int(request.headers.get("X-Height", config.FRAME_HEIGHT))
        rotation     = int(request.headers.get("X-Rotation-Degrees", 0))
        session_id   = request.headers.get("X-Session-Id", "")

        loop = asyncio.get_event_loop()
        snap_id = await loop.run_in_executor(
            _executor,
            self._process_snapshot,
            jpeg_bytes, frame_id, timestamp_ms, width, height, rotation, session_id,
        )
        return web.Response(status=200, text=snap_id)

    # ── Pipeline (runs in thread) ─────────────────────────────────────────────

    def _process_snapshot(
        self,
        jpeg_bytes: bytes,
        frame_id: int,
        timestamp_ms: int,
        width: int,
        height: int,
        rotation: int,
        session_id: str,
    ) -> str:
        try:
            # 1. Save full frame
            snap_id, snap_dir = self._snap_mgr.save(
                jpeg_bytes, frame_id, timestamp_ms, width, height, rotation, session_id
            )

            # 2. Decode for in-memory use
            arr   = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if image is None:
                log.error("snapshot_server: failed to decode JPEG  snap=%s", snap_id)
                return snap_id

            # 3. Detect objects in frozen snapshot
            detections = run_detector(snap_dir, snap_dir / "full.jpg")

            # 4. Extract crops
            crop_records = extract_crops(snap_dir, snap_id, image, detections)

            # 5. Score crop quality
            quality_results = score_crops(crop_records)

            # 6. Extract descriptors for accepted crops only
            frame_area  = width * height
            descriptors = []
            for rec, q in zip(crop_records, quality_results):
                if q.accept_for_memory:
                    crop_img = cv2.imread(rec.image_path)
                    desc = extract_descriptor(
                        crop_id=rec.crop_id,
                        snapshot_id=snap_id,
                        label=rec.label,
                        confidence=rec.confidence,
                        quality_score=q.quality_score,
                        image=crop_img,
                        frame_area=frame_area,
                    )
                else:
                    desc = None
                descriptors.append(desc)

            # 7 + 8. Match and update memory for accepted crops
            match_results   = []
            uid_assignments = []
            for rec, q, desc in zip(crop_records, quality_results, descriptors):
                if not q.accept_for_memory or desc is None:
                    match_results.append(None)
                    uid_assignments.append(None)
                    continue
                match = self._matcher.match(desc)
                uid   = self._updater.apply(match, desc, rec, q)
                match_results.append(match)
                uid_assignments.append(uid)

            # 9. Write audit reports
            self._reporter.write_snapshot_report(
                snap_dir, snap_id,
                crop_records, quality_results,
                descriptors, match_results, uid_assignments,
            )
            return snap_id

        except Exception as exc:
            log.exception("snapshot_server: pipeline error: %s", exc)
            return "error"
