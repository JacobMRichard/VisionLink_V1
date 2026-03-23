import json
import logging
from typing import Optional, TYPE_CHECKING

from aiohttp import web, WSMsgType

if TYPE_CHECKING:
    from app.diagnostics import DiagnosticsBundle

log = logging.getLogger(__name__)


class MetadataServer:
    """Pushes overlay metadata JSON to all connected phone WebSocket clients."""

    def __init__(self, diag: Optional["DiagnosticsBundle"] = None) -> None:
        self._clients: set[web.WebSocketResponse] = set()
        self._broadcast_count: int = 0
        self._broadcast_fail_count: int = 0
        self._diag = diag

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.add(ws)
        log.info("Phone connected from %s  total_clients=%d", request.remote, len(self._clients))
        if self._diag:
            self._diag.events.log(
                "metadata_server", "INFO", "client_connected",
                remote=str(request.remote), total_clients=len(self._clients),
            )

        try:
            async for msg in ws:
                if msg.type == WSMsgType.ERROR:
                    log.warning(
                        "WebSocket protocol error from %s: %s",
                        request.remote, ws.exception(),
                    )
        finally:
            self._clients.discard(ws)
            log.info(
                "Phone disconnected from %s  total_clients=%d",
                request.remote, len(self._clients),
            )
            if self._diag:
                self._diag.events.log(
                    "metadata_server", "INFO", "client_disconnected",
                    remote=str(request.remote), total_clients=len(self._clients),
                )

        return ws

    async def broadcast(self, data: dict) -> None:
        if not self._clients:
            return
        text = json.dumps(data)
        payload_bytes = len(text.encode())
        dead: set[web.WebSocketResponse] = set()
        for ws in self._clients:
            try:
                await ws.send_str(text)
                self._broadcast_count += 1
            except Exception as exc:
                self._broadcast_fail_count += 1
                log.warning(
                    "Broadcast failed  frame_id=%s  total_fails=%d  error=%s",
                    data.get("frame_id"), self._broadcast_fail_count, exc,
                )
                dead.add(ws)
        self._clients -= dead

        log.debug(
            "tx  frame=%d  payload=%d B  clients=%d",
            data.get("frame_id", 0), payload_bytes, len(self._clients),
        )
        if self._diag:
            self._diag.events.log(
                "metadata_server", "DEBUG", "metadata_broadcast",
                frame_id=data.get("frame_id"),
                payload_bytes=payload_bytes,
                clients=len(self._clients),
            )
            self._diag.metadata.push(data)
