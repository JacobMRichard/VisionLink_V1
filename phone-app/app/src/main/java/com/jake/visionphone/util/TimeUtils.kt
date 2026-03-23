package com.jake.visionphone.util

object TimeUtils {
    fun nowMs(): Long = System.currentTimeMillis()
    fun elapsedMs(startMs: Long): Long = nowMs() - startMs
}
