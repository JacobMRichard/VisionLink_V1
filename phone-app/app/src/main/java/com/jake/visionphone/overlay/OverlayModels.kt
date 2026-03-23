package com.jake.visionphone.overlay

/** Local overlay data converted from the network MetadataResponse. */
data class OverlayObject(
    val id: Int,
    val label: String,
    val confidence: Float,
    val bboxX: Int,
    val bboxY: Int,
    val bboxW: Int,
    val bboxH: Int,
    val centroidX: Int,
    val centroidY: Int,
    val contour: List<Pair<Float, Float>> = emptyList(), // normalized (x,y) 0.0-1.0
    val state: String = "confirmed",                     // "candidate" | "confirmed" | "lost"
)

data class OverlayState(
    val objects: List<OverlayObject> = emptyList(),
    val sourceWidth: Int = 1280,
    val sourceHeight: Int = 720
)
