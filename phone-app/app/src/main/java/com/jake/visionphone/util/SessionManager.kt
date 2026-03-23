package com.jake.visionphone.util

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

object SessionManager {

    lateinit var sessionId: String
        private set
    lateinit var sessionDir: File
        private set

    fun init(context: Context) {
        val ts = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val suffix = UUID.randomUUID().toString().take(6)
        sessionId = "${ts}_${suffix}"
        sessionDir = File(context.filesDir, "sessions/$sessionId").also { it.mkdirs() }
        saveConfigSnapshot()
    }

    private fun saveConfigSnapshot() {
        val snapshot = JSONObject().apply {
            put("session_id", sessionId)
            put("started_at", System.currentTimeMillis())
            put("laptop_ip", Constants.LAPTOP_IP)
            put("frame_port", Constants.FRAME_PORT)
            put("metadata_ws_port", Constants.METADATA_WS_PORT)
            put("frame_width", Constants.FRAME_WIDTH)
            put("frame_height", Constants.FRAME_HEIGHT)
            put("jpeg_quality", Constants.JPEG_QUALITY)
        }
        File(sessionDir, "config_snapshot.json").writeText(snapshot.toString(2))
    }
}
