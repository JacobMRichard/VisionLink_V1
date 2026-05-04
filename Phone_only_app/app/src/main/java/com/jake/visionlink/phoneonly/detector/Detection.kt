package com.jake.visionlink.phoneonly.detector

/** A single YOLO detection result in original image pixel coordinates. */
data class Detection(
    val label: String,
    val confidence: Float,
    /** Bounding box in original image pixel space. */
    val x1: Int,
    val y1: Int,
    val x2: Int,
    val y2: Int,
) {
    val centerX: Int get() = (x1 + x2) / 2
    val centerY: Int get() = (y1 + y2) / 2
    val width:   Int get() = x2 - x1
    val height:  Int get() = y2 - y1
}
