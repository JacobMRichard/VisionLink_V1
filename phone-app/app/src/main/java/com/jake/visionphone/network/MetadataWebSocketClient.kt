package com.jake.visionphone.network

import android.os.Handler
import android.os.Looper
import android.util.Log
import com.jake.visionphone.util.Constants
import com.jake.visionphone.util.EventLog
import com.jake.visionphone.util.RecentStore
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

enum class ConnectionState {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,
    RECEIVING,
}

class MetadataWebSocketClient(
    private val onMetadata: (MetadataResponse) -> Unit,
    private val onStateChange: (ConnectionState) -> Unit,
    private val onReconnect: ((attempt: Int) -> Unit)? = null,
    private val metadataStatsStore: RecentStore? = null,
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.SECONDS)
        .build()

    private val json = Json { ignoreUnknownKeys = true }
    private var webSocket: WebSocket? = null
    private val reconnectHandler = Handler(Looper.getMainLooper())
    private val reconnectAttempts = AtomicInteger(0)
    private val packetsReceived = AtomicInteger(0)
    private var isShuttingDown = false
    private var reconnectDelayMs = BASE_DELAY_MS

    fun connect() {
        isShuttingDown = false
        reconnectDelayMs = BASE_DELAY_MS
        doConnect()
    }

    private fun doConnect() {
        onStateChange(ConnectionState.CONNECTING)
        val request = Request.Builder().url(Constants.METADATA_WS_URL).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                Log.i(TAG, "WebSocket connected  url=${Constants.METADATA_WS_URL}  " +
                      "reconnect_attempts=${reconnectAttempts.get()}")
                reconnectDelayMs = BASE_DELAY_MS
                EventLog.log("ws_client", "INFO", "websocket_connect",
                    "url" to Constants.METADATA_WS_URL,
                    "reconnect_attempts" to reconnectAttempts.get())
                onStateChange(ConnectionState.CONNECTED)
            }

            override fun onMessage(ws: WebSocket, text: String) {
                val count = packetsReceived.incrementAndGet()
                try {
                    val metadata = json.decodeFromString<MetadataResponse>(text)
                    onStateChange(ConnectionState.RECEIVING)
                    EventLog.log("ws_client", "DEBUG", "metadata_received",
                        "frame_id" to metadata.frameId,
                        "fps"      to metadata.fps,
                        "objects"  to metadata.objects.size)
                    metadataStatsStore?.push(JSONObject().apply {
                        put("frame_id",   metadata.frameId)
                        put("fps",        metadata.fps)
                        put("latency_ms", metadata.latencyMs)
                        put("mode",       metadata.mode)
                        put("objects",    metadata.objects.size)
                        put("ts",         System.currentTimeMillis())
                    })
                    onMetadata(metadata)
                } catch (e: Exception) {
                    Log.w(TAG, "Parse failed  packet=#$count: ${e.message}  raw=${text.take(120)}")
                    EventLog.log("ws_client", "WARN", "metadata_parse_failed",
                        "packet_num" to count, "error" to e.message, "raw_preview" to text.take(80))
                }
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "WebSocket closed  code=$code  reason='$reason'  " +
                      "packets_received=${packetsReceived.get()}")
                EventLog.log("ws_client", "INFO", "websocket_disconnect",
                    "code" to code, "reason" to reason,
                    "packets_received" to packetsReceived.get())
                onStateChange(ConnectionState.DISCONNECTED)
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                Log.w(TAG, "WebSocket failure: ${t.message}  " +
                      "packets_received=${packetsReceived.get()}")
                EventLog.log("ws_client", "WARN", "websocket_disconnect",
                    "error" to t.message, "packets_received" to packetsReceived.get())
                onStateChange(ConnectionState.DISCONNECTED)
                scheduleReconnect()
            }
        })
    }

    private fun scheduleReconnect() {
        if (isShuttingDown) return
        val attempt = reconnectAttempts.incrementAndGet()
        val delay = reconnectDelayMs
        reconnectDelayMs = (reconnectDelayMs * 2).coerceAtMost(MAX_DELAY_MS)
        Log.i(TAG, "Reconnecting in ${delay}ms  attempt=$attempt")
        onReconnect?.invoke(attempt)
        reconnectHandler.postDelayed({ doConnect() }, delay)
    }

    fun disconnect() {
        isShuttingDown = true
        reconnectHandler.removeCallbacksAndMessages(null)
        webSocket?.close(1000, "Activity stopped")
        client.dispatcher.executorService.shutdown()
        client.connectionPool.evictAll()
        Log.i(TAG, "Disconnected  total_packets=${packetsReceived.get()}  " +
              "reconnect_attempts=${reconnectAttempts.get()}")
    }

    companion object {
        private const val TAG = "MetadataWSClient"
        private const val BASE_DELAY_MS = 1_000L
        private const val MAX_DELAY_MS  = 30_000L
    }
}
