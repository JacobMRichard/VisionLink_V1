package com.jake.visionlink.phoneonly

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.jake.visionlink.phoneonly.camera.CameraController
import com.jake.visionlink.phoneonly.databinding.ActivityMainBinding
import com.jake.visionlink.phoneonly.detector.YoloDetector
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.asCoroutineDispatcher

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var detector: YoloDetector
    private lateinit var camera: CameraController

    // Single-threaded — YoloDetector shares a ByteBuffer that can't be accessed concurrently
    private val inferenceExecutor = Executors.newSingleThreadExecutor()
    private val inferenceScope = CoroutineScope(inferenceExecutor.asCoroutineDispatcher() + SupervisorJob())

    // FPS tracking
    private val fpsFrameCount = AtomicLong(0)
    @Volatile private var fpsWindowStart = System.currentTimeMillis()
    @Volatile private var currentFps = 0f
    @Volatile private var lastInferenceMs = 0L
    @Volatile private var lastDetectionCount = 0

    // ── Permission launcher ───────────────────────────────────────────────────
    private val requestCameraPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startCamera()
        else Toast.makeText(this, "Camera permission required", Toast.LENGTH_LONG).show()
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────────
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        detector = YoloDetector(this)

        binding.btnDebugToggle.setOnClickListener {
            binding.debugPanel.visibility =
                if (binding.debugPanel.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        }

        binding.btnSettings.setOnClickListener {
            binding.settingsPanel.visibility =
                if (binding.settingsPanel.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        }

        binding.cbLabels.setOnCheckedChangeListener     { _, c -> binding.overlayView.showLabels = c }
        binding.cbCentroid.setOnCheckedChangeListener   { _, c -> binding.overlayView.showCentroid = c }
        binding.cbConfidence.setOnCheckedChangeListener { _, c -> binding.overlayView.showConfidence = c }

        if (cameraPermissionGranted()) startCamera()
        else requestCameraPermission.launch(Manifest.permission.CAMERA)
    }

    override fun onDestroy() {
        super.onDestroy()
        detector.close()
        inferenceExecutor.shutdown()
    }

    // ── Camera setup ──────────────────────────────────────────────────────────
    private fun startCamera() {
        camera = CameraController(
            context        = this,
            lifecycleOwner = this,
            previewView    = binding.previewView,
            onBitmap       = { bitmap, appliedRotation ->
                // Copy before returning — CameraController recycles the original after onBitmap returns
                val bitmapCopy = bitmap.copy(bitmap.config ?: android.graphics.Bitmap.Config.ARGB_8888, false)
                val rotatedW = bitmap.width
                val rotatedH = bitmap.height
                inferenceScope.launch {
                    val t0 = System.currentTimeMillis()
                    val detections = detector.detect(bitmapCopy)
                    val inferMs = System.currentTimeMillis() - t0
                    bitmapCopy.recycle()

                    // Map detections back to the original (pre-rotation) landscape coordinate space
                    // so they align with what PreviewView displays on screen.
                    val (sourceW, sourceH, overlayDets) = when (appliedRotation) {
                        90 -> {
                            val origW = rotatedH  // e.g. 1280
                            val origH = rotatedW  // e.g. 720
                            Triple(origW, origH,
                                detections.map { d ->
                                    com.jake.visionlink.phoneonly.detector.Detection(
                                        label      = d.label,
                                        confidence = d.confidence,
                                        x1 = d.y1,
                                        y1 = origH - d.x2,
                                        x2 = d.y2,
                                        y2 = origH - d.x1,
                                    )
                                }
                            )
                        }
                        270 -> {
                            val origW = rotatedH
                            val origH = rotatedW
                            Triple(origW, origH,
                                detections.map { d ->
                                    com.jake.visionlink.phoneonly.detector.Detection(
                                        label      = d.label,
                                        confidence = d.confidence,
                                        x1 = origW - d.y2,
                                        y1 = d.x1,
                                        x2 = origW - d.y1,
                                        y2 = d.x2,
                                    )
                                }
                            )
                        }
                        else -> Triple(rotatedW, rotatedH, detections)
                    }

                    android.util.Log.d("VisionLink", "inference=${inferMs}ms  dets=${detections.size}  frame=${sourceW}x${sourceH}  rot=${appliedRotation}")

                    // Update FPS counter
                    val count = fpsFrameCount.incrementAndGet()
                    val now = System.currentTimeMillis()
                    val elapsed = now - fpsWindowStart
                    if (elapsed >= 1000L) {
                        currentFps = count * 1000f / elapsed
                        fpsFrameCount.set(0)
                        fpsWindowStart = now
                    }
                    lastInferenceMs    = inferMs
                    lastDetectionCount = detections.size

                    runOnUiThread {
                        binding.overlayView.update(overlayDets, sourceW, sourceH)
                        binding.tvFps.text         = "FPS: ${"%.1f".format(currentFps)}"
                        binding.tvDetections.text  = "detections: ${detections.size}"
                        binding.tvInferenceMs.text = "inference: ${inferMs} ms"
                    }
                }
            }
        )
        camera.start()
    }

    // ── Helpers ───────────────────────────────────────────────────────────────
    private fun cameraPermissionGranted() =
        ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED
}
