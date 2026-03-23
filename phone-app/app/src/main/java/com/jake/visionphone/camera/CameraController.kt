package com.jake.visionphone.camera

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
import com.jake.visionphone.util.Constants
import com.jake.visionphone.util.EventLog
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicLong

class CameraController(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val previewView: PreviewView,
    private val onFrame: (CameraFrame) -> Unit
) {
    private val analysisExecutor = Executors.newSingleThreadExecutor()
    private val frameId = AtomicLong(0L)

    fun start() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }

            val imageAnalysis = ImageAnalysis.Builder()
                .setTargetResolution(Size(Constants.FRAME_WIDTH, Constants.FRAME_HEIGHT))
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                .build()

            imageAnalysis.setAnalyzer(analysisExecutor) { imageProxy ->
                val encodeStart = System.currentTimeMillis()

                val bitmap = try {
                    imageProxy.toBitmap()
                } catch (e: Exception) {
                    Log.e(TAG, "toBitmap() failed  frame=${frameId.get()}: ${e.message}")
                    EventLog.log("camera", "ERROR", "camera_encode_error",
                        "frame_id" to frameId.get(), "stage" to "toBitmap", "error" to e.message)
                    imageProxy.close()
                    return@setAnalyzer
                }

                val jpegBytes = try {
                    bitmapToJpeg(bitmap)
                } catch (e: Exception) {
                    Log.e(TAG, "JPEG encode failed  frame=${frameId.get()}: ${e.message}")
                    EventLog.log("camera", "ERROR", "camera_encode_error",
                        "frame_id" to frameId.get(), "stage" to "jpeg_compress", "error" to e.message)
                    bitmap.recycle()
                    imageProxy.close()
                    return@setAnalyzer
                }
                bitmap.recycle()

                val encodeDurationMs = System.currentTimeMillis() - encodeStart

                val frame = CameraFrame(
                    frameId          = frameId.getAndIncrement(),
                    timestampMs      = System.currentTimeMillis(),
                    width            = imageProxy.width,
                    height           = imageProxy.height,
                    rotationDegrees  = imageProxy.imageInfo.rotationDegrees,
                    jpegBytes        = jpegBytes,
                    encodeDurationMs = encodeDurationMs,
                )
                onFrame(frame)
                imageProxy.close()
            }

            cameraProvider.unbindAll()
            cameraProvider.bindToLifecycle(
                lifecycleOwner,
                CameraSelector.DEFAULT_BACK_CAMERA,
                preview,
                imageAnalysis
            )

            EventLog.log("camera", "INFO", "camera_started",
                "width" to Constants.FRAME_WIDTH,
                "height" to Constants.FRAME_HEIGHT,
                "jpeg_quality" to Constants.JPEG_QUALITY)
            Log.i(TAG, "Camera started  ${Constants.FRAME_WIDTH}x${Constants.FRAME_HEIGHT}")

        }, ContextCompat.getMainExecutor(context))
    }

    private fun bitmapToJpeg(bitmap: Bitmap): ByteArray {
        val out = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, Constants.JPEG_QUALITY, out)
        return out.toByteArray()
    }

    companion object {
        private const val TAG = "CameraController"
    }
}
