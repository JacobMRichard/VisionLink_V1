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
import java.util.concurrent.atomic.AtomicLong

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
    private val executor = Executors.newSingleThreadExecutor()
    private val totalSent = AtomicLong(0)
    private val totalFailed = AtomicLong(0)
    private var consecutiveFails = 0

    fun sendFrame(frame: CameraFrame) {
        executor.execute {
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
                consecutiveFails = 0

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
                    "frame_id"  to frame.frameId,
                    "jpeg_kb"   to stats.jpegKb,
                    "encode_ms" to frame.encodeDurationMs,
                    "send_ms"   to sendMs,
                    "total_sent" to sent,
                )
                sendStatsStore?.push(JSONObject().apply {
                    put("frame_id",   frame.frameId)
                    put("jpeg_kb",    stats.jpegKb)
                    put("encode_ms",  frame.encodeDurationMs)
                    put("send_ms",    sendMs)
                    put("total_sent", sent)
                    put("total_failed", totalFailed.get())
                    put("ts",         System.currentTimeMillis())
                })

                if (sent % 30 == 0L) {
                    Log.d(TAG, "STATS  sent=$sent  failed=${totalFailed.get()}  " +
                          "send=${sendMs}ms  encode=${frame.encodeDurationMs}ms  " +
                          "size=${frame.jpegBytes.size / 1024}KB")
                }
            } catch (e: Exception) {
                val failed = totalFailed.incrementAndGet()
                consecutiveFails++
                Log.w(TAG, "Frame ${frame.frameId} send failed  " +
                      "total=$failed  consecutive=$consecutiveFails: ${e.message}")
                EventLog.log(
                    "frame_sender", "WARN", "frame_send_failed",
                    "frame_id"         to frame.frameId,
                    "error"            to e.message,
                    "consecutive_fails" to consecutiveFails,
                    "total_failed"     to failed,
                )
                if (consecutiveFails >= 5) {
                    Log.e(TAG, "ERROR  $consecutiveFails consecutive send failures — " +
                          "check laptop IP (${Constants.LAPTOP_IP}) and server")
                }
            }
        }
    }

    fun shutdown() {
        executor.shutdown()
        executor.awaitTermination(2, TimeUnit.SECONDS)
        Log.i(TAG, "Shutdown  total_sent=${totalSent.get()}  total_failed=${totalFailed.get()}")
    }

    companion object {
        private const val TAG = "FrameSender"
    }
}
