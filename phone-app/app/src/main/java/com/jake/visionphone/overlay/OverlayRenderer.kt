package com.jake.visionphone.overlay

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Typeface

/**
 * Stateless renderer — converts [OverlayState] coords (camera pixel space)
 * to view coords and paints outlines, centroids, and labels per [OverlaySettings].
 *
 * Rendering varies by track state:
 *   confirmed  → full opacity, solid outline
 *   candidate  → 60% opacity, solid outline  (tentative, may disappear)
 *   lost       → 40% opacity, dashed outline (held briefly before expiry)
 */
class OverlayRenderer {

    private val outlinePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
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

    private val dashEffect = DashPathEffect(floatArrayOf(20f, 10f), 0f)

    fun draw(canvas: Canvas, state: OverlayState, settings: OverlaySettings, viewW: Int, viewH: Int) {
        if (state.objects.isEmpty()) return

        val scaleX = viewW.toFloat() / state.sourceWidth
        val scaleY = viewH.toFloat() / state.sourceHeight

        for (obj in state.objects) {
            val alpha = when (obj.state) {
                "confirmed" -> 255
                "candidate" -> 153   // ~60%
                "lost"      -> 102   // ~40%
                else        -> 255
            }
            outlinePaint.alpha = alpha
            outlinePaint.pathEffect = if (obj.state == "lost") dashEffect else null
            centroidPaint.alpha = alpha
            labelPaint.alpha = alpha

            // Outline
            if (settings.showPolygon && obj.contour.size >= 3) {
                val path = Path()
                val first = obj.contour[0]
                path.moveTo(first.first * viewW, first.second * viewH)
                for (i in 1 until obj.contour.size) {
                    val pt = obj.contour[i]
                    path.lineTo(pt.first * viewW, pt.second * viewH)
                }
                path.close()
                canvas.drawPath(path, outlinePaint)
            } else {
                val left   = obj.bboxX * scaleX
                val top    = obj.bboxY * scaleY
                val right  = (obj.bboxX + obj.bboxW) * scaleX
                val bottom = (obj.bboxY + obj.bboxH) * scaleY
                canvas.drawRect(left, top, right, bottom, outlinePaint)
            }

            val cx = obj.centroidX * scaleX
            val cy = obj.centroidY * scaleY

            if (settings.showCentroid) {
                canvas.drawCircle(cx, cy, 8f, centroidPaint)
            }

            if (settings.showLabels) {
                val text = if (settings.showPolygon) "#${obj.id}" else "#${obj.id} ${obj.label}"
                canvas.drawText(text, cx + 10f, cy - 10f, labelPaint)
            }
        }
    }
}
