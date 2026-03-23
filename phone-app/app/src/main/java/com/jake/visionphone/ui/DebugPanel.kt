package com.jake.visionphone.ui

import android.graphics.Color
import android.widget.TextView
import com.jake.visionphone.network.ConnectionState

class DebugPanel(
    private val tvMode: TextView,
    private val tvFps: TextView,
    private val tvLatency: TextView,
    private val tvFrameIds: TextView,
    private val tvStatus: TextView,
) {
    fun update(
        fps: Float,
        latencyMs: Float,
        sendMs: Long = 0,
        jpegKb: Int = 0,
        encodeDurationMs: Long = 0,
        totalSent: Long = 0,
        totalFailed: Long = 0,
        mode: String = "unknown",
        latestFrameIdSent: Long = 0,
        latestMetaFrameId: Long = 0,
        metadataAgeMs: Long = 0,
        healthState: HealthState = HealthState.DISCONNECTED,
    ) {
        tvMode.text = "mode: $mode  |  IP: ${com.jake.visionphone.util.Constants.LAPTOP_IP}"
        tvFps.text  = "FPS: ${"%.1f".format(fps)}  |  sent: $totalSent  fail: $totalFailed"
        tvLatency.text = "pipeline: ${"%.0f".format(latencyMs)}ms est  |  " +
                         "send: ${sendMs}ms  size: ${jpegKb}KB  enc: ${encodeDurationMs}ms"
        tvFrameIds.text = "sent: #$latestFrameIdSent  |  meta: #$latestMetaFrameId  " +
                          "|  age: ${metadataAgeMs}ms"

        val (healthText, healthColor) = when (healthState) {
            HealthState.HEALTHY      -> "HEALTHY"      to Color.GREEN
            HealthState.STALE        -> "STALE"        to Color.YELLOW
            HealthState.DISCONNECTED -> "DISCONNECTED" to Color.RED
        }
        tvFrameIds.setTextColor(healthColor)
        tvFrameIds.text = tvFrameIds.text.toString() + "  |  $healthText"
    }

    fun setState(state: ConnectionState, reconnectAttempts: Int = 0) {
        val reconnectSuffix = if (reconnectAttempts > 0) "  (reconnects: $reconnectAttempts)" else ""
        val (text, color) = when (state) {
            ConnectionState.DISCONNECTED -> "Disconnected$reconnectSuffix" to Color.RED
            ConnectionState.CONNECTING   -> "Connecting…$reconnectSuffix"  to Color.YELLOW
            ConnectionState.CONNECTED    -> "Connected"                     to Color.GREEN
            ConnectionState.RECEIVING    -> "Receiving"                     to Color.GREEN
        }
        tvStatus.text = text
        tvStatus.setTextColor(color)
    }
}
