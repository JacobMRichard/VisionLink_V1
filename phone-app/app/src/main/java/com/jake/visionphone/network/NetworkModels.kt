package com.jake.visionphone.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class BBox(
    val x: Int,
    val y: Int,
    val w: Int,
    val h: Int
)

@Serializable
data class DetectedObject(
    val id: Int,
    val label: String,
    val confidence: Float,
    val bbox: List<Int>,                          // [x, y, w, h]
    val centroid: List<Int>,                      // [cx, cy]
    val contour: List<List<Float>> = emptyList(), // normalized [[x,y], ...] 0.0-1.0
    val state: String = "confirmed",              // "candidate" | "confirmed" | "lost"
)

@Serializable
data class MetadataResponse(
    @SerialName("frame_id")      val frameId: Long,
    val fps: Float,
    @SerialName("latency_ms")    val latencyMs: Float,
    @SerialName("source_width")  val sourceWidth: Int = 1280,
    @SerialName("source_height") val sourceHeight: Int = 720,
    val mode: String = "real",
    val objects: List<DetectedObject> = emptyList(),
)
