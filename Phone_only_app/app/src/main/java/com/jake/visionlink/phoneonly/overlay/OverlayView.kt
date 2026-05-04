package com.jake.visionlink.phoneonly.overlay

import android.content.Context
import android.graphics.Canvas
import android.util.AttributeSet
import android.view.View
import com.jake.visionlink.phoneonly.detector.Detection

/**
 * Transparent view placed over the camera preview.
 * Call [update] from the main thread to push a new detection result.
 */
class OverlayView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    private val renderer = OverlayRenderer()
    private var detections: List<Detection> = emptyList()
    private var sourceW = 1280
    private var sourceH = 720
    var showLabels:     Boolean = true
    var showCentroid:   Boolean = true
    var showConfidence: Boolean = true

    fun update(dets: List<Detection>, imgW: Int, imgH: Int) {
        detections = dets
        sourceW    = imgW
        sourceH    = imgH
        invalidate()
    }

    fun clear() {
        detections = emptyList()
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        renderer.draw(
            canvas        = canvas,
            detections    = detections,
            sourceW       = sourceW,
            sourceH       = sourceH,
            showLabels    = showLabels,
            showCentroid  = showCentroid,
            showConfidence = showConfidence,
            viewW         = width,
            viewH         = height,
        )
    }
}
