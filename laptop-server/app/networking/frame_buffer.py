import asyncio
import logging
from typing import Optional, TYPE_CHECKING

from app.networking.models import FrameMetadata

if TYPE_CHECKING:
    from app.diagnostics import DiagnosticsBundle

log = logging.getLogger(__name__)


class LatestFrameBuffer:
    """
    Drop-all-but-latest buffer. Keeps newest frame, discards unread older frame.
    Counts and logs buffer-overwrite drops for diagnostics.
    """

    def __init__(self, diag: Optional["DiagnosticsBundle"] = None) -> None:
        self._frame: Optional[tuple[bytes, FrameMetadata]] = None
        self._event: asyncio.Event = asyncio.Event()
        self._drop_count: int = 0
        self._diag = diag

    @property
    def drop_count(self) -> int:
        return self._drop_count

    async def put(self, jpeg: bytes, meta: FrameMetadata) -> None:
        if self._event.is_set():
            self._drop_count += 1
            log.debug(
                "frame=%d overwritten (processor lagging)  total_drops=%d",
                meta.frame_id, self._drop_count,
            )
            if self._diag:
                self._diag.events.log(
                    "frame_buffer", "DEBUG", "frame_buffer_overwrite",
                    frame_id=meta.frame_id, total_drops=self._drop_count,
                )
        self._frame = (jpeg, meta)
        self._event.set()

    async def get(self) -> tuple[bytes, FrameMetadata]:
        await self._event.wait()
        self._event.clear()
        frame = self._frame
        if frame is None:
            raise RuntimeError("LatestFrameBuffer.get() returned None — should never happen")
        return frame
