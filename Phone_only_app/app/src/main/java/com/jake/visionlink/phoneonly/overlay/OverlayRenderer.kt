package com.jake.visionlink.phoneonly.overlay

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import com.jake.visionlink.phoneonly.detector.Detection

/** Stateless renderer — paints bounding boxes, centroids, and labels onto a Canvas. */
class OverlayRenderer {

    private val boxPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.GREEN
        style = Paint.Style.STROKE
        strokeWidth = 3f
    }

    private val centroidPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.RED
        style = Paint.Style.FILL
    }

    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textSize = 36f
        typeface = Typeface.MONOSPACE
        setShadowLayer(4f, 1f, 1f, Color.BLACK)
    }

    fun draw(
        canvas: Canvas,
        detections: List<Detection>,
        sourceW: Int,
        sourceH: Int,
        showLabels: Boolean,
        showCentroid: Boolean,
        showConfidence: Boolean,
        viewW: Int,
        viewH: Int,
    ) {
        if (detections.isEmpty()) return

        val sx = viewW.toFloat() / sourceW
        val sy = viewH.toFloat() / sourceH

        for (det in detections) {
            val left   = det.x1 * sx
            val top    = det.y1 * sy
            val right  = det.x2 * sx
            val bottom = det.y2 * sy

            canvas.drawRect(left, top, right, bottom, boxPaint)

            val cx = det.centerX * sx
            val cy = det.centerY * sy

            if (showCentroid) {
                canvas.drawCircle(cx, cy, 8f, centroidPaint)
            }

            if (showLabels) {
                val text = if (showConfidence)
                    "${det.label} ${"%.0f".format(det.confidence * 100)}%"
                else
                    det.label
                canvas.drawText(text, left + 4f, top - 6f, labelPaint)
            }
        }
    }
}
