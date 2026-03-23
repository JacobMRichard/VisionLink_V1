package com.jake.visionphone.util

import android.util.Log
import org.json.JSONObject
import java.io.File

object EventLog {

    private var logFile: File? = null
    private val lock = Any()
    private const val TAG = "EventLog"

    fun init(sessionDir: File) {
        logFile = File(sessionDir, "events.jsonl")
    }

    fun log(component: String, level: String, event: String, vararg extras: Pair<String, Any?>) {
        val entry = JSONObject().apply {
            put("ts", System.currentTimeMillis())
            put("session_id", SessionManager.sessionId)
            put("component", component)
            put("level", level)
            put("event", event)
            extras.forEach { (k, v) -> put(k, v ?: JSONObject.NULL) }
        }
        synchronized(lock) {
            try {
                logFile?.appendText(entry.toString() + "\n")
            } catch (e: Exception) {
                Log.w(TAG, "Write failed: ${e.message}")
            }
        }
    }

    fun appendException(component: String, message: String, stackTrace: String) {
        val ts = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.US)
            .format(java.util.Date())
        val text = "[$ts] [$component] $message\n$stackTrace\n" + "-".repeat(60) + "\n"
        synchronized(lock) {
            try {
                val f = logFile?.parentFile?.let { File(it, "exceptions.txt") }
                f?.appendText(text)
            } catch (e: Exception) {
                Log.w(TAG, "Exception write failed: ${e.message}")
            }
        }
    }
}
