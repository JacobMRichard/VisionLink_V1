package com.jake.visionphone.overlay

import android.content.Context
import android.graphics.Canvas
import android.util.AttributeSet
import android.view.View
import com.jake.visionphone.network.MetadataResponse

/**
 * Transparent view placed over the camera preview.
 * Call [updateOverlay] from the main thread to refresh detections.
 * Call [updateSettings] to change rendering options live.
 */
class OverlayView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val renderer = OverlayRenderer()
    private var state: OverlayState = OverlayState()
    private var settings: OverlaySettings = OverlaySettings()

    fun updateOverlay(metadata: MetadataResponse) {
        state = OverlayState(
            objects = metadata.objects.map { obj ->
                OverlayObject(
                    id = obj.id,
                    label = obj.label,
                    confidence = obj.confidence,
                    bboxX = obj.bbox.getOrElse(0) { 0 },
                    bboxY = obj.bbox.getOrElse(1) { 0 },
                    bboxW = obj.bbox.getOrElse(2) { 0 },
                    bboxH = obj.bbox.getOrElse(3) { 0 },
                    centroidX = obj.centroid.getOrElse(0) { 0 },
                    centroidY = obj.centroid.getOrElse(1) { 0 },
                    contour = obj.contour.map { pt ->
                        Pair(pt.getOrElse(0) { 0f }, pt.getOrElse(1) { 0f })
                    },
                    state = obj.state,
                )
            },
            sourceWidth = metadata.sourceWidth,
            sourceHeight = metadata.sourceHeight
        )
        invalidate()
    }

    fun updateSettings(newSettings: OverlaySettings) {
        settings = newSettings
        invalidate()
    }

    fun clear() {
        state = OverlayState()
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        renderer.draw(canvas, state, settings, width, height)
    }
}
