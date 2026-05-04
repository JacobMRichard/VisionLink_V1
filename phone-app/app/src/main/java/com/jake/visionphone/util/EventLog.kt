package com.jake.visionphone.util

import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import org.json.JSONObject
import java.io.File

/**
 * Non-blocking JSONL event log.
 * All callers return instantly — a dedicated HandlerThread handles disk writes.
 * Multiple rapid log() calls are serialized by the handler queue with no caller blocking.
 */
object EventLog {

    private const val TAG = "EventLog"

    private var logFile: File? = null
    private var exceptionsFile: File? = null

    private val handlerThread = HandlerThread("event-log-writer").also { it.start() }
    private val handler = Handler(handlerThread.looper)

    fun init(sessionDir: File) {
        logFile = File(sessionDir, "events.jsonl")
        exceptionsFile = File(sessionDir, "exceptions.txt")
    }

    fun log(component: String, level: String, event: String, vararg extras: Pair<String, Any?>) {
        val ts = System.currentTimeMillis()
        val sessionId = runCatching { SessionManager.sessionId }.getOrDefault("unknown")
        handler.post {
            val entry = JSONObject().apply {
                put("ts",         ts)
                put("session_id", sessionId)
                put("component",  component)
                put("level",      level)
                put("event",      event)
                extras.forEach { (k, v) -> put(k, v ?: JSONObject.NULL) }
            }
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
        handler.post {
            try {
                exceptionsFile?.appendText(text)
            } catch (e: Exception) {
                Log.w(TAG, "Exception write failed: ${e.message}")
            }
        }
    }
}
