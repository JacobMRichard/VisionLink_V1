package com.jake.visionphone.util

object Constants {
    // ── Network ────────────────────────────────────────────────────────────────
    // Change LAPTOP_IP to your laptop's local Wi-Fi address before running.
    const val LAPTOP_IP = "10.0.0.74"
    const val FRAME_PORT = 8080
    const val METADATA_WS_PORT = 8081

    val FRAME_POST_URL    get() = "http://$LAPTOP_IP:$FRAME_PORT/frame"
    val SNAPSHOT_POST_URL get() = "http://$LAPTOP_IP:$FRAME_PORT/snapshot"
    val METADATA_WS_URL   get() = "ws://$LAPTOP_IP:$METADATA_WS_PORT/metadata"

    // ── Camera ─────────────────────────────────────────────────────────────────
    const val FRAME_WIDTH = 1280
    const val FRAME_HEIGHT = 720
    const val JPEG_QUALITY = 80           // 0-100; lower = smaller payload
}
