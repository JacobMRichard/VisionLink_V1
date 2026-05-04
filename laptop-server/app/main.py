"""
VisionLink V1 — Laptop Server
Start with:  python -m app.main
"""
import os
# Suppress Conda + PyTorch OpenMP runtime conflict (libomp vs libiomp5md).
# Safe for single-process CPU inference.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import asyncio
import logging

import aiohttp
from aiohttp import web

import app.config as config
from app.diagnostics import make_diagnostics
from app.networking.frame_buffer import LatestFrameBuffer
from app.networking.video_server import VideoServer
from app.networking.metadata_server import MetadataServer
from app.notification_manager import NotificationManager
from app.processing.frame_pipeline import FramePipeline
from app.runtime_config import RuntimeConfig
from app.util.logging_utils import setup_logging, stop_logging


async def processing_loop(
    buffer: LatestFrameBuffer,
    pipeline: FramePipeline,
    metadata_server: MetadataServer,
    notifier: NotificationManager | None,
) -> None:
    log = logging.getLogger("processing_loop")
    frames_processed = 0
    frames_failed = 0

    while True:
        jpeg, meta = await buffer.get()
        result = await pipeline.process(jpeg, meta)
        if result is not None:
            await metadata_server.broadcast(result.to_dict())
            if notifier:
                await notifier.check_and_notify(result.objects)
            frames_processed += 1
            if frames_processed % 100 == 0:
                log.info(
                    "STATS  processed=%d  failed=%d  buf_drops=%d  "
                    "fps=%.1f  latency=%.0f ms  ws_clients=%d",
                    frames_processed, frames_failed, buffer.drop_count,
                    result.fps, result.latency_ms, metadata_server.client_count,
                )
        else:
            frames_failed += 1
            log.warning(
                "pipeline returned None  frame=%d  total_failed=%d",
                meta.frame_id, frames_failed,
            )


async def main() -> None:
    setup_logging()
    log = logging.getLogger("main")

    diag = make_diagnostics()
    diag.events.log("main", "INFO", "app_start", session_id=diag.session.session_id)

    debug_window = None
    if config.DEBUG_WINDOW and not config.FAKE_DETECTION_MODE:
        from app.visualization.debug_window import DebugWindow
        debug_window = DebugWindow()

    # Shared aiohttp session for outbound requests (Discord webhooks, etc.)
    http_session = aiohttp.ClientSession()

    notifier: NotificationManager | None = None
    if config.DISCORD_WEBHOOK_URL:
        notifier = NotificationManager(config.DISCORD_WEBHOOK_URL, http_session)
        log.info("Discord notifications enabled  cooldown=%.0fs", config.NOTIFICATION_COOLDOWN_S)
    else:
        log.info("Discord notifications disabled  (set DISCORD_WEBHOOK_URL in config.py)")

    buffer = LatestFrameBuffer(diag=diag)
    pipeline = FramePipeline(debug_window=debug_window, diag=diag)
    metadata_server = MetadataServer(diag=diag)
    video_server = VideoServer(buffer, diag=diag)

    # ── Routes ─────────────────────────────────────────────────────────────────

    async def handle_health(request: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def handle_control(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        changed = []

        if "class_filter" in data:
            RuntimeConfig.set_class_filter(data["class_filter"])
            changed.append("class_filter")

        if "confidence" in data:
            RuntimeConfig.set_confidence(float(data["confidence"]))
            changed.append("confidence")

        if "max_objects" in data:
            RuntimeConfig.set_max_objects(int(data["max_objects"]))
            changed.append("max_objects")

        if "notifications" in data:
            n = data["notifications"]
            RuntimeConfig.set_notifications(
                enabled=bool(n.get("enabled", True)),
                cooldown_s=n.get("cooldown_s"),
                min_count=n.get("min_count"),
            )
            changed.append("notifications")

        cfg = RuntimeConfig.to_dict()
        log.info("control  changed=%s  config=%s", changed, cfg)
        return web.json_response({"status": "ok", "changed": changed, "config": cfg})

    frame_app = web.Application()
    frame_app.router.add_post("/frame", video_server.handle_frame)
    frame_app.router.add_get("/health", handle_health)
    frame_app.router.add_post("/control", handle_control)

    meta_app = web.Application()
    meta_app.router.add_get("/metadata", metadata_server.handle_ws)

    runner1 = web.AppRunner(frame_app)
    runner2 = web.AppRunner(meta_app)
    await runner1.setup()
    await runner2.setup()

    site1 = web.TCPSite(runner1, config.HOST, config.FRAME_PORT)
    site2 = web.TCPSite(runner2, config.HOST, config.METADATA_PORT)
    await site1.start()
    await site2.start()

    log.info("=" * 60)
    log.info("VisionLink V1 — Laptop Server started")
    log.info("  Session         →  %s", diag.session.session_id)
    log.info("  Session folder  →  %s", diag.session.folder)
    log.info("  Frame receiver  →  http://%s:%d/frame",  config.HOST, config.FRAME_PORT)
    log.info("  Control API     →  http://%s:%d/control", config.HOST, config.FRAME_PORT)
    log.info("  Health check    →  http://%s:%d/health",  config.HOST, config.FRAME_PORT)
    log.info("  Metadata WS     →  ws://%s:%d/metadata", config.HOST, config.METADATA_PORT)
    log.info("  Resolution      →  %dx%d", config.FRAME_WIDTH, config.FRAME_HEIGHT)
    log.info("  Detection mode  →  %s", "FAKE" if config.FAKE_DETECTION_MODE else "REAL (YOLO)")
    log.info("  Notifications   →  %s", "Discord enabled" if config.DISCORD_WEBHOOK_URL else "disabled")
    log.info("  Logs            →  logs/laptop.log  |  logs/phone.log")
    log.info("=" * 60)
    log.info("Press Ctrl+C to stop.")

    proc_task = asyncio.create_task(
        processing_loop(buffer, pipeline, metadata_server, notifier)
    )

    try:
        await asyncio.Event().wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        proc_task.cancel()
        try:
            await asyncio.wait_for(proc_task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        if debug_window:
            debug_window.close()
        await http_session.close()
        await runner1.cleanup()
        await runner2.cleanup()
        diag.events.log("main", "INFO", "app_stop")
        diag.close()
        bundle = diag.exporter.export()
        log.info("Export bundle: %s", bundle)
        log.info("Server stopped cleanly.")
        stop_logging()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
