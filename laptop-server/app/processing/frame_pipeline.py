import asyncio
import logging
import time
import traceback as tb
from typing import List, Optional, TYPE_CHECKING

import cv2
import numpy as np

import app.config as config
from app.networking.models import BBox, DetectedObject, FrameMetadata, MetadataResponse
from app.processing.detect import detect_yolo, load_model
from app.processing.tracker import CentroidIoUTracker
from app.processing.tracked_object import TrackedObject
from app.processing.metrics import MetricsTracker

if TYPE_CHECKING:
    from app.diagnostics import DiagnosticsBundle

log = logging.getLogger(__name__)


def _to_wire(tracks: List[TrackedObject]) -> List[DetectedObject]:
    """Convert internal TrackedObjects to wire-format DetectedObjects."""
    return [
        DetectedObject(
            id=t.id,
            label=t.label,
            confidence=t.confidence,
            bbox=BBox(t.bbox_x, t.bbox_y, t.bbox_w, t.bbox_h),
            centroid=(t.centroid_x, t.centroid_y),
            contour=t.contour,
            state=t.state.value,
        )
        for t in tracks
    ]


class FramePipeline:
    """
    Orchestrates: decode → YOLO detect → track → metrics.

    Detection runs at whatever rate YOLO can manage (~10-15 FPS on CPU).
    The LatestFrameBuffer drops frames when the pipeline is busy, keeping
    latency low at the cost of frame completeness.

    Known Phase 1 limitation: fast camera panning drops IoU to zero,
    resetting track IDs. This is inherent to image-space tracking, not a bug.
    """

    def __init__(self, debug_window=None, diag: Optional["DiagnosticsBundle"] = None) -> None:
        self._tracker = CentroidIoUTracker()
        self._metrics = MetricsTracker()
        self._debug_window = debug_window
        self._diag = diag
        self._mode = "fake" if config.FAKE_DETECTION_MODE else "real"

        if config.FAKE_DETECTION_MODE:
            from app.processing.fake_detect import FakeDetector
            self._fake: Optional[FakeDetector] = FakeDetector()
            log.info("FAKE_DETECTION_MODE on — animated bbox, no YOLO")
        else:
            self._fake = None
            load_model()   # blocking — completes before server starts accepting frames

    async def process(
        self, jpeg_bytes: bytes, meta: FrameMetadata
    ) -> Optional[MetadataResponse]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._process_sync, jpeg_bytes, meta)

    def _process_sync(
        self, jpeg_bytes: bytes, meta: FrameMetadata
    ) -> Optional[MetadataResponse]:
        t0 = time.monotonic()
        fps, latency_ms = self._metrics.update(meta.timestamp_ms)

        # ── Fake path ────────────────────────────────────────────────────────
        if self._fake is not None:
            objects = self._fake.detect(meta.width, meta.height)
            t1 = time.monotonic()
            timing = {
                "frame_id":       meta.frame_id,
                "ts":             round(time.time() * 1000),
                "fps":            round(fps, 1),
                "latency_ms":     round(latency_ms, 1),
                "fake_detect_ms": round((t1 - t0) * 1000, 1),
                "total_ms":       round((t1 - t0) * 1000, 1),
                "objects":        len(objects),
            }
            log.debug(
                "pipeline  frame=%d  fps=%.1f  latency=%.0f ms  fake=%.1f ms  objects=%d",
                meta.frame_id, fps, latency_ms, timing["fake_detect_ms"], len(objects),
            )
            if self._diag:
                self._diag.timings.push(timing)
            return MetadataResponse(
                frame_id=meta.frame_id, fps=fps, latency_ms=latency_ms,
                source_width=meta.width, source_height=meta.height,
                objects=objects, mode=self._mode,
            )

        # ── Real path ────────────────────────────────────────────────────────

        # Decode
        try:
            nparr = np.frombuffer(jpeg_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception as exc:
            log.error("JPEG decode error  frame=%d: %s", meta.frame_id, exc, exc_info=True)
            self._record_exception("decode", meta.frame_id, exc)
            return None
        if frame is None:
            log.warning("JPEG decode returned None  frame=%d", meta.frame_id)
            return None
        t_decode = time.monotonic()

        # Detect
        try:
            raw_detections = detect_yolo(frame)
        except Exception as exc:
            log.error("Detect error  frame=%d: %s", meta.frame_id, exc, exc_info=True)
            self._record_exception("detect", meta.frame_id, exc)
            return None
        t_detect = time.monotonic()

        # Track
        try:
            tracked = self._tracker.update(raw_detections, meta.frame_id)
        except Exception as exc:
            log.error("Track error  frame=%d: %s", meta.frame_id, exc, exc_info=True)
            self._record_exception("track", meta.frame_id, exc)
            return None
        t_track = time.monotonic()

        wire_objects = _to_wire(tracked)

        if self._debug_window is not None:
            self._debug_window.show(frame, wire_objects)

        timing = {
            "frame_id":   meta.frame_id,
            "ts":         round(time.time() * 1000),
            "fps":        round(fps, 1),
            "latency_ms": round(latency_ms, 1),
            "decode_ms":  round((t_decode - t0) * 1000, 1),
            "detect_ms":  round((t_detect - t_decode) * 1000, 1),
            "track_ms":   round((t_track - t_detect) * 1000, 1),
            "total_ms":   round((t_track - t0) * 1000, 1),
            "objects":    len(wire_objects),
        }
        log.debug(
            "pipeline  frame=%d  fps=%.1f  latency=%.0f ms  "
            "decode=%.1f ms  detect=%.1f ms  track=%.1f ms  total=%.1f ms  objects=%d",
            meta.frame_id, fps, latency_ms,
            timing["decode_ms"], timing["detect_ms"],
            timing["track_ms"], timing["total_ms"], len(wire_objects),
        )
        if self._diag:
            self._diag.timings.push(timing)
            self._diag.events.log(
                "frame_pipeline", "DEBUG", "frame_processed",
                frame_id=meta.frame_id, fps=fps, latency_ms=latency_ms,
                total_ms=timing["total_ms"], objects=len(wire_objects),
            )

        return MetadataResponse(
            frame_id=meta.frame_id,
            fps=fps,
            latency_ms=latency_ms,
            source_width=meta.width,
            source_height=meta.height,
            objects=wire_objects,
            mode=self._mode,
        )

    def _record_exception(self, stage: str, frame_id: int, exc: Exception) -> None:
        if self._diag:
            self._diag.exceptions.record(
                f"frame_pipeline.{stage}",
                f"frame={frame_id}  {exc}",
                tb.format_exc(),
            )
            self._diag.events.log(
                "frame_pipeline", "ERROR", "pipeline_exception",
                frame_id=frame_id, stage=stage, error=str(exc),
            )
