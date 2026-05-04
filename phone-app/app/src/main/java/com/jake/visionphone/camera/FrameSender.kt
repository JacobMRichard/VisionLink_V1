package com.jake.visionphone.camera

import android.util.Log
import com.jake.visionphone.util.Constants
import com.jake.visionphone.util.EventLog
import com.jake.visionphone.util.RecentStore
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference

data class FrameSendStats(
    val frameId: Long,
    val jpegKb: Int,
    val encodeDurationMs: Long,
    val sendDurationMs: Long,
    val totalSent: Long,
    val totalFailed: Long,
)

class FrameSender(
    private val client: OkHttpClient,
    private val onStats: ((FrameSendStats) -> Unit)? = null,
    private val sendStatsStore: RecentStore? = null,
) {
    // Single-slot latest-frame buffer — new frame always overwrites pending one.
    // This mirrors the laptop's LatestFrameBuffer and prevents stale frame queuing.
    private val slot = AtomicReference<CameraFrame?>(null)
    private val senderRunning = AtomicBoolean(false)
    private val executor = Executors.newSingleThreadExecutor()

    private val totalSent = AtomicLong(0)
    private val totalFailed = AtomicLong(0)
    private val totalDropped = AtomicLong(0)

    fun sendFrame(frame: CameraFrame) {
        val displaced = slot.getAndSet(frame)
        if (displaced != null) {
            // A frame was already pending — we just replaced it with a newer one.
            totalDropped.incrementAndGet()
        }
        // Only schedule the sender if it isn't already running.
        if (senderRunning.compareAndSet(false, true)) {
            executor.execute(::runSender)
        }
    }

    private fun runSender() {
        try {
            var frame = slot.getAndSet(null)
            while (frame != null) {
                doSend(frame)
                frame = slot.getAndSet(null)
            }
        } finally {
            senderRunning.set(false)
            // Race guard: a frame may have arrived between our last slot read and
            // setting senderRunning=false. Reschedule if so.
            if (slot.get() != null && senderRunning.compareAndSet(false, true)) {
                executor.execute(::runSender)
            }
        }
    }

    private fun doSend(frame: CameraFrame) {
        val sendStart = System.currentTimeMillis()
        try {
            val body = frame.jpegBytes.toRequestBody("image/jpeg".toMediaType())
            val request = Request.Builder()
                .url(Constants.FRAME_POST_URL)
                .addHeader("X-Frame-Id",         frame.frameId.toString())
                .addHeader("X-Timestamp-Ms",     frame.timestampMs.toString())
                .addHeader("X-Width",            frame.width.toString())
                .addHeader("X-Height",           frame.height.toString())
                .addHeader("X-Rotation-Degrees", frame.rotationDegrees.toString())
                .post(body)
                .build()
            client.newCall(request).execute().close()

            val sendMs = System.currentTimeMillis() - sendStart
            val sent = totalSent.incrementAndGet()

            val stats = FrameSendStats(
                frameId          = frame.frameId,
                jpegKb           = frame.jpegBytes.size / 1024,
                encodeDurationMs = frame.encodeDurationMs,
                sendDurationMs   = sendMs,
                totalSent        = sent,
                totalFailed      = totalFailed.get(),
            )
            onStats?.invoke(stats)

            EventLog.log(
                "frame_sender", "DEBUG", "frame_sent",
                "frame_id"    to frame.frameId,
                "jpeg_kb"     to stats.jpegKb,
                "encode_ms"   to frame.encodeDurationMs,
                "send_ms"     to sendMs,
                "total_sent"  to sent,
                "total_dropped" to totalDropped.get(),
            )
            sendStatsStore?.push(JSONObject().apply {
                put("frame_id",      frame.frameId)
                put("jpeg_kb",       stats.jpegKb)
                put("encode_ms",     frame.encodeDurationMs)
                put("send_ms",       sendMs)
                put("total_sent",    sent)
                put("total_failed",  totalFailed.get())
                put("total_dropped", totalDropped.get())
                put("ts",            System.currentTimeMillis())
            })

            if (sent % 30 == 0L) {
                Log.d(TAG, "STATS  sent=$sent  failed=${totalFailed.get()}  " +
                      "dropped=${totalDropped.get()}  send=${sendMs}ms  " +
                      "encode=${frame.encodeDurationMs}ms  size=${frame.jpegBytes.size / 1024}KB")
            }
        } catch (e: Exception) {
            val failed = totalFailed.incrementAndGet()
            Log.w(TAG, "Frame ${frame.frameId} send failed  total=$failed: ${e.message}")
            EventLog.log(
                "frame_sender", "WARN", "frame_send_failed",
                "frame_id"    to frame.frameId,
                "error"       to e.message,
                "total_failed" to failed,
            )
        }
    }

    fun shutdown() {
        executor.shutdown()
        executor.awaitTermination(2, TimeUnit.SECONDS)
        Log.i(TAG, "Shutdown  sent=${totalSent.get()}  failed=${totalFailed.get()}  dropped=${totalDropped.get()}")
    }

    companion object {
        private const val TAG = "FrameSender"
    }
}
