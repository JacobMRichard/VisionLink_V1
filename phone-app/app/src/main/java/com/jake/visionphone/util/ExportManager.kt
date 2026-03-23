package com.jake.visionphone.util

import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

object ExportManager {

    private const val TAG = "ExportManager"

    private val EXPORT_FILES = listOf(
        "config_snapshot.json",
        "events.jsonl",
        "recent_send_stats.json",
        "recent_metadata_stats.json",
        "app_state.json",
        "exceptions.txt",
    )

    fun export(): File {
        val exportDir = File(SessionManager.sessionDir, "export_bundle").also { it.mkdirs() }

        EXPORT_FILES.forEach { name ->
            val src = File(SessionManager.sessionDir, name)
            if (src.exists()) src.copyTo(File(exportDir, name), overwrite = true)
        }

        val files = JSONArray()
        exportDir.listFiles()?.sortedBy { it.name }?.forEach { files.put(it.name) }
        val manifest = JSONObject().apply {
            put("exported_at", System.currentTimeMillis())
            put("session_id", SessionManager.sessionId)
            put("files", files)
        }
        File(exportDir, "manifest.json").writeText(manifest.toString(2))

        Log.i(TAG, "Bundle: ${exportDir.absolutePath}")
        return exportDir
    }
}
