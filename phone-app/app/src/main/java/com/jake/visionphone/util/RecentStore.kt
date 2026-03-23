package com.jake.visionphone.util

import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.ArrayDeque

class RecentStore(
    private val file: File,
    private val key: String,
    private val window: Int = 50,
) {
    private val records = ArrayDeque<JSONObject>()
    private val lock = Any()

    fun push(record: JSONObject) {
        synchronized(lock) {
            records.addLast(record)
            while (records.size > window) records.removeFirst()
            flush()
        }
    }

    private fun flush() {
        try {
            val arr = JSONArray()
            records.forEach { arr.put(it) }
            val data = JSONObject().apply {
                put("updated_at", System.currentTimeMillis())
                put("window", window)
                put(key, arr)
            }
            file.writeText(data.toString(2))
        } catch (e: Exception) {
            Log.w("RecentStore", "Flush failed for ${file.name}: ${e.message}")
        }
    }
}
