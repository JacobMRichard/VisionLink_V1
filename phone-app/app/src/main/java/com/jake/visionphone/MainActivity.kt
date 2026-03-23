package com.jake.visionphone

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.jake.visionphone.camera.CameraController
import com.jake.visionphone.camera.CameraFrame
import com.jake.visionphone.camera.FrameSendStats
import com.jake.visionphone.databinding.ActivityMainBinding
import com.jake.visionphone.network.ConnectionState
import com.jake.visionphone.network.MetadataWebSocketClient
import com.jake.visionphone.network.VideoStreamClient
import com.jake.visionphone.overlay.OverlaySettings
import com.jake.visionphone.ui.DebugPanel
import com.jake.visionphone.ui.HealthState
import com.jake.visionphone.util.Constants
import com.jake.visionphone.util.EventLog
import com.jake.visionphone.util.ExportManager
import com.jake.visionphone.util.RecentStore
import com.jake.visionphone.util.SessionManager
import com.jake.visionphone.util.SnapshotManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.File

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var debugPanel: DebugPanel
    private lateinit var videoClient: VideoStreamClient
    private lateinit var wsClient: MetadataWebSocketClient
    private lateinit var cameraController: CameraController
    private lateinit var sendStatsStore: RecentStore
    private lateinit var metadataStatsStore: RecentStore

    // Last captured frame — saved for snapshot POSTs to laptop
    @Volatile private var lastFrame: CameraFrame? = null

    // Latest stats — written from background threads, read on UI thread
    @Volatile private var lastFps: Float = 0f
    @Volatile private var lastLatencyMs: Float = 0f
    @Volatile private var lastSendStats: FrameSendStats? = null
    @Volatile private var reconnectAttempts: Int = 0
    @Volatile private var lastMode: String = "unknown"
    @Volatile private var lastMetaFrameId: Long = 0L
    @Volatile private var lastMetadataReceivedMs: Long = 0L
    @Volatile private var currentConnectionState: ConnectionState = ConnectionState.DISCONNECTED
    @Volatile private var isMetadataStale: Boolean = false

    // Stale detection
    private val staleHandler = Handler(Looper.getMainLooper())
    private val staleRunnable = object : Runnable {
        override fun run() {
            val now = System.currentTimeMillis()
            val age = if (lastMetadataReceivedMs > 0) now - lastMetadataReceivedMs else 0L
            val shouldBeStale = lastMetadataReceivedMs > 0 && age > STALE_THRESHOLD_MS
            if (shouldBeStale && !isMetadataStale) {
                isMetadataStale = true
                EventLog.log("main", "WARN", "metadata_stale", "age_ms" to age)
                Log.w(TAG, "Metadata stale  age=${age}ms")
                binding.overlayView.clear()
                refreshDebugPanel()
                saveAppState()
            } else if (!shouldBeStale && isMetadataStale) {
                isMetadataStale = false
                refreshDebugPanel()
            }
            staleHandler.postDelayed(this, STALE_CHECK_INTERVAL_MS)
        }
    }

    // ── Permission launcher ───────────────────────────────────────────────────
    private val requestCameraPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startStreaming()
        else Toast.makeText(this, "Camera permission required", Toast.LENGTH_LONG).show()
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────────
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Init session and diagnostics before anything else
        SessionManager.init(this)
        EventLog.init(SessionManager.sessionDir)
        sendStatsStore    = RecentStore(File(SessionManager.sessionDir, "recent_send_stats.json"),     "send_stats",     50)
        metadataStatsStore = RecentStore(File(SessionManager.sessionDir, "recent_metadata_stats.json"), "metadata_stats", 20)

        EventLog.log("main", "INFO", "app_start",
            "session_id" to SessionManager.sessionId,
            "laptop_ip"  to com.jake.visionphone.util.Constants.LAPTOP_IP)

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        debugPanel = DebugPanel(
            tvMode     = binding.tvMode,
            tvFps      = binding.tvFps,
            tvLatency  = binding.tvLatency,
            tvFrameIds = binding.tvFrameIds,
            tvStatus   = binding.tvStatus,
        )

        staleHandler.post(staleRunnable)

        binding.btnSnapshot.setOnClickListener {
            // Local diagnostics snapshot (unchanged from V1)
            val stateJson = buildAppStateJson()
            val snapDir = SnapshotManager.capture(
                appStateJson   = stateJson,
                metadataStore  = if (::metadataStatsStore.isInitialized) metadataStatsStore else null,
                sendStatsStore = if (::sendStatsStore.isInitialized) sendStatsStore else null,
                reason         = "manual_button",
            )
            Toast.makeText(this, "Snapshot saved: ${snapDir.name}", Toast.LENGTH_SHORT).show()

            // V2: send full frame to laptop memory pipeline
            lastFrame?.let { frame -> sendSnapshotToLaptop(frame) }
        }

        binding.btnDebugToggle.setOnClickListener {
            binding.debugPanel.visibility =
                if (binding.debugPanel.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        }

        binding.btnSettings.setOnClickListener {
            binding.settingsPanel.visibility =
                if (binding.settingsPanel.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        }

        binding.cbPolygon.setOnCheckedChangeListener  { _, _ -> applyOverlaySettings() }
        binding.cbLabels.setOnCheckedChangeListener   { _, _ -> applyOverlaySettings() }
        binding.cbCentroid.setOnCheckedChangeListener { _, _ -> applyOverlaySettings() }

        if (cameraPermissionGranted()) startStreaming()
        else requestCameraPermission.launch(Manifest.permission.CAMERA)
    }

    override fun onDestroy() {
        super.onDestroy()
        staleHandler.removeCallbacksAndMessages(null)
        if (::wsClient.isInitialized) wsClient.disconnect()
        if (::videoClient.isInitialized) videoClient.shutdown()
        saveAppState()
        EventLog.log("main", "INFO", "app_stop")
        val bundle = ExportManager.export()
        Log.i(TAG, "Export bundle: ${bundle.absolutePath}")
        EventLog.log("main", "INFO", "export_bundle_created", "path" to bundle.absolutePath)
    }

    // ── Setup ─────────────────────────────────────────────────────────────────
    private fun startStreaming() {
        videoClient = VideoStreamClient(
            onStats = { stats ->
                lastSendStats = stats
                runOnUiThread { refreshDebugPanel() }
            },
            sendStatsStore = sendStatsStore,
        )

        wsClient = MetadataWebSocketClient(
            onMetadata = { metadata ->
                lastFps = metadata.fps
                lastLatencyMs = metadata.latencyMs
                lastMode = metadata.mode
                lastMetaFrameId = metadata.frameId
                lastMetadataReceivedMs = System.currentTimeMillis()
                isMetadataStale = false
                runOnUiThread {
                    binding.overlayView.updateOverlay(metadata)
                    EventLog.log("main", "DEBUG", "overlay_updated",
                        "frame_id" to metadata.frameId, "objects" to metadata.objects.size)
                    refreshDebugPanel()
                }
            },
            onStateChange = { state ->
                currentConnectionState = state
                runOnUiThread {
                    debugPanel.setState(state, reconnectAttempts)
                    if (state == ConnectionState.DISCONNECTED) binding.overlayView.clear()
                }
                saveAppState()
            },
            onReconnect = { attempt ->
                reconnectAttempts = attempt
                runOnUiThread { debugPanel.setState(ConnectionState.DISCONNECTED, attempt) }
            },
            metadataStatsStore = metadataStatsStore,
        )
        wsClient.connect()

        cameraController = CameraController(
            context        = this,
            lifecycleOwner = this,
            previewView    = binding.previewView,
            onFrame        = { frame ->
                lastFrame = frame
                videoClient.sendFrame(frame)
            }
        )
        cameraController.start()
    }

    // ── Debug panel ───────────────────────────────────────────────────────────
    private fun refreshDebugPanel() {
        val stats = lastSendStats
        val now = System.currentTimeMillis()
        val metaAge = if (lastMetadataReceivedMs > 0) now - lastMetadataReceivedMs else 0L
        val health = when {
            currentConnectionState == ConnectionState.DISCONNECTED -> HealthState.DISCONNECTED
            isMetadataStale -> HealthState.STALE
            else -> HealthState.HEALTHY
        }
        debugPanel.update(
            fps                = lastFps,
            latencyMs          = lastLatencyMs,
            sendMs             = stats?.sendDurationMs   ?: 0,
            jpegKb             = stats?.jpegKb           ?: 0,
            encodeDurationMs   = stats?.encodeDurationMs ?: 0,
            totalSent          = stats?.totalSent        ?: 0,
            totalFailed        = stats?.totalFailed      ?: 0,
            mode               = lastMode,
            latestFrameIdSent  = stats?.frameId          ?: 0,
            latestMetaFrameId  = lastMetaFrameId,
            metadataAgeMs      = metaAge,
            healthState        = health,
        )
    }

    // ── App state snapshot ────────────────────────────────────────────────────
    private fun buildAppStateJson(): JSONObject {
        val stats = lastSendStats
        val now = System.currentTimeMillis()
        val metaAge = if (lastMetadataReceivedMs > 0) now - lastMetadataReceivedMs else 0L
        return JSONObject().apply {
            put("session_id",           SessionManager.sessionId)
            put("updated_at",           now)
            put("mode",                 lastMode)
            put("target_ip",            com.jake.visionphone.util.Constants.LAPTOP_IP)
            put("connection_state",     currentConnectionState.name)
            put("latest_frame_sent",    stats?.frameId     ?: 0)
            put("latest_meta_frame",    lastMetaFrameId)
            put("total_sent",           stats?.totalSent   ?: 0)
            put("total_failed",         stats?.totalFailed ?: 0)
            put("reconnect_count",      reconnectAttempts)
            put("metadata_age_ms",      metaAge)
            put("stale",                isMetadataStale)
            put("health_state",         if (isMetadataStale) "STALE"
                                        else if (currentConnectionState == ConnectionState.DISCONNECTED) "DISCONNECTED"
                                        else "HEALTHY")
        }
    }

    private fun saveAppState() {
        try {
            File(SessionManager.sessionDir, "app_state.json").writeText(buildAppStateJson().toString(2))
        } catch (e: Exception) {
            Log.w(TAG, "saveAppState failed: ${e.message}")
        }
    }

    // ── Overlay settings ──────────────────────────────────────────────────────
    private fun applyOverlaySettings() {
        binding.overlayView.updateSettings(
            OverlaySettings(
                showPolygon  = binding.cbPolygon.isChecked,
                showLabels   = binding.cbLabels.isChecked,
                showCentroid = binding.cbCentroid.isChecked,
            )
        )
    }

    // ── V2 snapshot ───────────────────────────────────────────────────────────
    private fun sendSnapshotToLaptop(frame: CameraFrame) {
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val body = frame.jpegBytes.toRequestBody("image/jpeg".toMediaType())
                val request = Request.Builder()
                    .url(Constants.SNAPSHOT_POST_URL)
                    .post(body)
                    .addHeader("X-Frame-Id",        frame.frameId.toString())
                    .addHeader("X-Timestamp-Ms",    frame.timestampMs.toString())
                    .addHeader("X-Width",           frame.width.toString())
                    .addHeader("X-Height",          frame.height.toString())
                    .addHeader("X-Rotation-Degrees", frame.rotationDegrees.toString())
                    .addHeader("X-Session-Id",       SessionManager.sessionId)
                    .build()
                val response = OkHttpClient().newCall(request).execute()
                val snapId   = response.body?.string() ?: "?"
                response.close()
                Log.i(TAG, "snapshot sent to laptop  snap_id=$snapId")
                EventLog.log("main", "INFO", "snapshot_sent_to_laptop", "snap_id" to snapId)
            } catch (e: Exception) {
                Log.w(TAG, "snapshot POST failed: ${e.message}")
            }
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────
    private fun cameraPermissionGranted(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED

    companion object {
        private const val TAG = "MainActivity"
        private const val STALE_THRESHOLD_MS     = 500L
        private const val STALE_CHECK_INTERVAL_MS = 100L
    }
}
