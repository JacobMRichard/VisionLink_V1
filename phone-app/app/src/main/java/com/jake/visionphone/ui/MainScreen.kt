package com.jake.visionphone.ui

enum class HealthState { HEALTHY, STALE, DISCONNECTED }

data class MainScreenState(
    val streaming: Boolean      = false,
    val connected: Boolean      = false,
    val fps: Float              = 0f,
    val latencyMs: Float        = 0f,
    val sendMs: Long            = 0L,
    val jpegKb: Int             = 0,
    val encodeDurationMs: Long  = 0L,
    val totalSent: Long         = 0L,
    val totalFailed: Long       = 0L,
    val reconnectAttempts: Int  = 0,
    val mode: String            = "unknown",
    val latestFrameIdSent: Long = 0L,
    val latestMetaFrameId: Long = 0L,
    val metadataAgeMs: Long     = 0L,
    val healthState: HealthState = HealthState.DISCONNECTED,
)
