package com.jake.visionphone.util

import android.util.Log
import org.json.JSONObject
import java.io.File
import java.util.concurrent.atomic.AtomicInteger

object SnapshotManager {

    private const val TAG = "SnapshotManager"
    private val counter = AtomicInteger(0)

    /**
     * Capture a point-in-time snapshot of all live diagnostic data into
     * sessions/<id>/snapshots/snapshot_NNN/.
     *
     * @param appStateJson   Current JSONObject from saveAppState()
     * @param metadataStore  Rolling metadata window (may be null)
     * @param sendStatsStore Rolling send-stats window (may be null)
     * @param reason         Short label for why this snapshot was triggered
     */
    fun capture(
        appStateJson: JSONObject,
        metadataStore: RecentStore?,
        sendStatsStore: RecentStore?,
        reason: String = "manual",
    ): File {
        val index = counter.incrementAndGet()
        val label = "snapshot_%03d".format(index)
        val snapDir = File(SessionManager.sessionDir, "snapshots/$label").also { it.mkdirs() }

        // app state
        try {
            File(snapDir, "app_state.json").writeText(appStateJson.toString(2))
        } catch (e: Exception) {
            Log.w(TAG, "Failed to write app_state: ${e.message}")
        }

        // copy rolling stores if they exist on disk
        listOf(
            "recent_metadata_stats.json",
            "recent_send_stats.json",
        ).forEach { name ->
            val src = File(SessionManager.sessionDir, name)
            if (src.exists()) {
                try { src.copyTo(File(snapDir, name), overwrite = true) }
                catch (e: Exception) { Log.w(TAG, "Failed to copy $name: ${e.message}") }
            }
        }

        // snapshot metadata
        val meta = JSONObject().apply {
            put("snapshot_index", index)
            put("label",          label)
            put("reason",         reason)
            put("captured_at",    System.currentTimeMillis())
            put("session_id",     SessionManager.sessionId)
        }
        try {
            File(snapDir, "snapshot_meta.json").writeText(meta.toString(2))
        } catch (e: Exception) {
            Log.w(TAG, "Failed to write snapshot_meta: ${e.message}")
        }

        EventLog.log("snapshot", "INFO", "snapshot_captured",
            "label"  to label,
            "reason" to reason,
            "path"   to snapDir.absolutePath)
        Log.i(TAG, "Snapshot captured → ${snapDir.absolutePath}")

        return snapDir
    }
}
