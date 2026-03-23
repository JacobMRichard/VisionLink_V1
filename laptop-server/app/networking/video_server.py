import logging
import time
from typing import Optional, TYPE_CHECKING

from aiohttp import web

from app.networking.models import FrameMetadata
from app.networking.frame_buffer import LatestFrameBuffer

if TYPE_CHECKING:
    from app.diagnostics import DiagnosticsBundle

log = logging.getLogger(__name__)


class VideoServer:
    """
    Receives JPEG frames via HTTP POST and drops them into a LatestFrameBuffer.
    Returns 200 immediately — the phone is never blocked waiting for processing.
    """

    def __init__(self, buffer: LatestFrameBuffer, diag: Optional["DiagnosticsBundle"] = None) -> None:
        self._buffer = buffer
        self._diag = diag

    async def handle_frame(self, request: web.Request) -> web.Response:
        try:
            frame_id         = int(request.headers.get("X-Frame-Id", 0))
            timestamp_ms     = int(request.headers.get("X-Timestamp-Ms", 0))
            width            = int(request.headers.get("X-Width", 0))
            height           = int(request.headers.get("X-Height", 0))
            rotation_degrees = int(request.headers.get("X-Rotation-Degrees", 0))
        except ValueError as exc:
            log.warning(
                "Bad frame headers from %s: %s  headers=%s",
                request.remote, exc, dict(request.headers),
            )
            return web.Response(status=400, text="Bad frame headers")

        jpeg_bytes = await request.read()
        if not jpeg_bytes:
            log.warning("Empty frame body from %s  frame_id=%d", request.remote, frame_id)
            return web.Response(status=400, text="Empty body")

        arrival_latency_ms = max(0.0, time.time() * 1000 - timestamp_ms)
        log.debug(
            "rx  frame=%d  size=%d B  arrival_latency=%.0f ms  %dx%d  rot=%d",
            frame_id, len(jpeg_bytes), arrival_latency_ms, width, height, rotation_degrees,
        )
        if self._diag:
            self._diag.events.log(
                "video_server", "INFO", "frame_received",
                frame_id=frame_id,
                size_bytes=len(jpeg_bytes),
                arrival_latency_ms=round(arrival_latency_ms, 1),
                width=width,
                height=height,
            )

        meta = FrameMetadata(
            frame_id=frame_id,
            timestamp_ms=timestamp_ms,
            width=width,
            height=height,
            rotation_degrees=rotation_degrees,
        )
        await self._buffer.put(jpeg_bytes, meta)
        return web.Response(status=200)
