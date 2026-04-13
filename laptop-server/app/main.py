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

from aiohttp import web

import app.config as config
from app.diagnostics import make_diagnostics
from app.networking.frame_buffer import LatestFrameBuffer
from app.networking.video_server import VideoServer
from app.networking.metadata_server import MetadataServer
from app.processing.frame_pipeline import FramePipeline
from app.util.logging_utils import setup_logging


async def processing_loop(
    buffer: LatestFrameBuffer,
    pipeline: FramePipeline,
    metadata_server: MetadataServer,
) -> None:
    log = logging.getLogger("processing_loop")
    frames_processed = 0
    frames_failed = 0

    while True:
        jpeg, meta = await buffer.get()
        result = await pipeline.process(jpeg, meta)
        if result is not None:
            await metadata_server.broadcast(result.to_dict())
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
    diag.events.log(
        "main", "INFO", "config_loaded",
        frame_port=config.FRAME_PORT,
        metadata_port=config.METADATA_PORT,
        target_fps=config.TARGET_FPS,
        frame_width=config.FRAME_WIDTH,
        frame_height=config.FRAME_HEIGHT,
        jpeg_quality=config.JPEG_QUALITY,
        debug_window=config.DEBUG_WINDOW,
        fake_detection_mode=config.FAKE_DETECTION_MODE,
    )

    debug_window = None
    if config.DEBUG_WINDOW and not config.FAKE_DETECTION_MODE:
        from app.visualization.debug_window import DebugWindow
        debug_window = DebugWindow()

    buffer = LatestFrameBuffer(diag=diag)
    pipeline = FramePipeline(debug_window=debug_window, diag=diag)
    metadata_server = MetadataServer(diag=diag)
    video_server = VideoServer(buffer, diag=diag)

    frame_app = web.Application()
    frame_app.router.add_post("/frame", video_server.handle_frame)

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
    log.info("  Metadata WS     →  ws://%s:%d/metadata", config.HOST, config.METADATA_PORT)
    log.info("  Target FPS      →  %d",    config.TARGET_FPS)
    log.info("  Resolution      →  %dx%d", config.FRAME_WIDTH, config.FRAME_HEIGHT)
    log.info("  JPEG quality    →  %d",    config.JPEG_QUALITY)
    log.info("  Debug window    →  %s",    config.DEBUG_WINDOW)
    log.info("  Detection mode  →  %s",    "FAKE" if config.FAKE_DETECTION_MODE else "REAL")
    log.info("  Log file        →  logs/visionlink.log")
    log.info("=" * 60)
    log.info("Press Ctrl+C to stop.")

    proc_task = asyncio.create_task(
        processing_loop(buffer, pipeline, metadata_server)
    )

    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        proc_task.cancel()
        if debug_window:
            debug_window.close()
        await runner1.cleanup()
        await runner2.cleanup()
        diag.events.log("main", "INFO", "app_stop")
        bundle = diag.exporter.export()
        log.info("Export bundle created: %s", bundle)
        log.info("Server stopped cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
