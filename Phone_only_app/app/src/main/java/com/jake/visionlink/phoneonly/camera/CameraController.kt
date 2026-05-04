package com.jake.visionlink.phoneonly.camera

import android.content.Context
import android.graphics.Bitmap
import android.util.Log
import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import java.util.concurrent.Executors

/**
 * Binds CameraX preview + analysis. Delivers each frame as a [Bitmap]
 * (RGBA_8888) to [onBitmap]. The bitmap is recycled after [onBitmap] returns,
 * so callers must not hold a reference beyond that call.
 */
class CameraController(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val previewView: PreviewView,
    private val onBitmap: (Bitmap, Int) -> Unit,  // bitmap + rotation degrees applied
) {
    private val analysisExecutor = Executors.newSingleThreadExecutor()

    fun start() {
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            val provider = future.get()

            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }

            val analysis = ImageAnalysis.Builder()
                .setTargetResolution(Size(1280, 720))
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                .build()

            analysis.setAnalyzer(analysisExecutor) { imageProxy ->
                try {
                    val raw = imageProxy.toBitmap()
                    val rotation = imageProxy.imageInfo.rotationDegrees
                    val bitmap = if (rotation != 0) {
                        val matrix = android.graphics.Matrix().apply { postRotate(rotation.toFloat()) }
                        val rotated = android.graphics.Bitmap.createBitmap(raw, 0, 0, raw.width, raw.height, matrix, true)
                        raw.recycle()
                        rotated
                    } else raw
                    onBitmap(bitmap, rotation)
                    bitmap.recycle()
                } catch (e: Exception) {
                    Log.e(TAG, "Frame error: ${e.message}")
                } finally {
                    imageProxy.close()
                }
            }

            provider.unbindAll()
            provider.bindToLifecycle(
                lifecycleOwner,
                CameraSelector.DEFAULT_BACK_CAMERA,
                preview,
                analysis,
            )
            Log.i(TAG, "Camera started")
        }, ContextCompat.getMainExecutor(context))
    }

    companion object {
        private const val TAG = "CameraController"
    }
}
