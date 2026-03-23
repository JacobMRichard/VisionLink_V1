# VisionLink V1 — Engineering Specification

**Version:** 1.1
**Date:** 2026-03-17
**Scope:** V1 only — phone camera → laptop OpenCV → phone overlay

---

## 1. System Overview

VisionLink V1 is a split-compute perception loop. The phone acts as sensor and display; the laptop acts as compute node. A live JPEG frame stream flows from the phone to the laptop over Wi-Fi. The laptop runs OpenCV detection and sends structured detection metadata back to the phone, which renders a 2D bounding-box overlay on top of the live camera preview.

**Goal of V1:** Prove the full round-trip loop — frame capture → network transport → detection → overlay render — with full instrumentation, before any AI, SLAM, or ROS 2 is introduced.

```
┌─────────────────────────────────┐        ┌────────────────────────────────┐
│         Android Phone           │        │         Laptop (Python)        │
│                                 │        │                                │
│  CameraX (rear, 1280×720)       │        │  aiohttp HTTP server :8080     │
│       ↓ JPEG encode             │──POST─▶│       ↓                        │
│  VideoStreamClient              │        │  LatestFrameBuffer (1 slot)    │
│                                 │        │       ↓                        │
│                                 │        │  FramePipeline                 │
│                                 │        │    decode → preprocess         │
│                                 │        │    → detect → track → metrics  │
│                                 │        │       ↓                        │
│  MetadataWebSocketClient        │◀──WS───│  MetadataServer :8081          │
│       ↓                         │        │  (WebSocket broadcast)         │
│  OverlayView (Canvas draw)      │        │                                │
│  DebugPanel (5 TextViews)       │        │  DiagnosticsBundle             │
└─────────────────────────────────┘        └────────────────────────────────┘
```

### What V1 explicitly does NOT include
- No YOLO, no neural network inference
- No SLAM, no IMU, no pose estimation
- No ROS 2 (stub directory only)
- No WebRTC (HTTP POST per frame is intentional V1 simplification)
- No multi-object tracking (SimpleTracker assigns sequential IDs, not real tracking)
- No segmentation, depth, or 3D

---

## 2. Data Flow — Frame Lifecycle

### 2.1 Phone → Laptop (frame upload)

```
CameraX ImageAnalysis
  → imageProxy.toBitmap()            [RGBA_8888]
  → Bitmap.compress(JPEG, quality=80)
  → CameraFrame { frameId, timestampMs, width, height, jpegBytes, encodeDurationMs }
  → VideoStreamClient.sendFrame()
  → HTTP POST http://192.168.1.226:8080/frame
```

**Request headers:**

| Header | Value |
|--------|-------|
| `X-Frame-Id` | Monotonically incrementing Long |
| `X-Timestamp-Ms` | Phone epoch ms at capture |
| `X-Width` | Frame pixel width (1280) |
| `X-Height` | Frame pixel height (720) |
| `X-Rotation-Degrees` | CameraX reported rotation: 0, 90, 180, or 270 |
| `Content-Type` | `image/jpeg` |

**Rotation note:** `X-Rotation-Degrees` is forwarded in `FrameMetadata.rotation_degrees` but the laptop pipeline does **not** rotate the decoded frame before detection. Bounding boxes are therefore expressed in the raw JPEG coordinate frame, not the display orientation. `OverlayRenderer` scales coordinates but does not apply rotation. If the phone is held in portrait and CameraX reports 90°, bbox coordinates will be in landscape space — a known V1 limitation.

**Body:** Raw JPEG bytes (~30–100 KB at quality 80)

**Backpressure:** CameraX uses `STRATEGY_KEEP_ONLY_LATEST` — frames are dropped at the camera level if the sender is busy. `VideoStreamClient` uses a single-slot `LatestFrameBuffer` on the laptop side — if the pipeline hasn't finished the previous frame when a new one arrives, the old one is silently overwritten (logged as `frame_buffer_overwrite`). **Frames may be skipped under load. The system prioritizes low latency over frame completeness.** Frame ID gaps in the debug panel are normal and expected — they do not indicate packet loss or bugs.

---

### 2.2 Laptop Pipeline (processing)

```
VideoServer.handle_frame()
  → parse headers → FrameMetadata
  → LatestFrameBuffer.put(jpeg_bytes, meta)
  → [processing_loop coroutine] LatestFrameBuffer.get()
  → FramePipeline.process()         [run_in_executor — thread pool]
      decode:      cv2.imdecode(jpeg_bytes)
      preprocess:  grayscale → GaussianBlur(15,15) → threshold(127)
      detect:      findContours → largest contour → BBox + centroid
      track:       SimpleTracker.update() → assign sequential IDs
      metrics:     FpsCounter → fps, latency_ms estimate
  → MetadataResponse
  → MetadataServer.broadcast(result.to_dict())
```

**Latency note:** `latency_ms` in the JSON payload (labeled "pipeline: …ms est" in the phone HMI) is computed as `laptop_now_ms - frame.timestamp_ms`. Because phone and laptop clocks are not synchronized, this is a rough pipeline latency estimate, not a true RTT. Treat it as a relative trending indicator, not an absolute measurement. The "est" suffix in the HMI is intentional.

---

### 2.3 Laptop → Phone (metadata return)

**Protocol:** WebSocket
**URL:** `ws://192.168.1.226:8081/metadata`
**Direction:** Server → client broadcast (all connected phones receive every frame result)

**JSON schema (one message per frame):**

```json
{
  "frame_id":     1042,
  "fps":          28.3,
  "latency_ms":   47.0,
  "source_width": 1280,
  "source_height": 720,
  "mode":         "real",
  "objects": [
    {
      "id":         1,
      "label":      "object",
      "confidence": 0.85,
      "bbox":       [x, y, w, h],
      "centroid":   [cx, cy]
    }
  ]
}
```

**`mode` field:** `"fake"` when `FAKE_DETECTION_MODE = True` in `config.py`, `"real"` otherwise. Visible on phone debug panel.

---

### 2.4 Phone — Overlay Render

```
MetadataWebSocketClient.onMessage()
  → parse JSON → MetadataResponse
  → OverlayView.updateOverlay(metadata)
  → OverlayView.invalidate()
  → OverlayRenderer.draw(canvas, state, viewW, viewH)
      scaleX = viewW / source_width
      scaleY = viewH / source_height
      for each object:
        drawRect(bbox scaled)
        drawCircle(centroid scaled)
        drawText(label + confidence%)
```

**Coordinate space:** Bounding boxes are expressed in raw decoded JPEG coordinates — origin top-left, +x right, +y down, pixel units of the source frame (1280×720). `OverlayRenderer` scales these to view pixel dimensions using `scaleX = viewW / source_width` and `scaleY = viewH / source_height`. It does not apply rotation, flip, or crop. Aspect ratio mismatches between PreviewView and source frame are the primary overlay alignment risk; rotation mismatches (portrait hold vs landscape frame) are a secondary risk.

---

## 3. Runtime Components

### 3.1 Laptop Server

| Component | File | Responsibility |
|-----------|------|----------------|
| Entry point | `app/main.py` | Wires everything, runs aiohttp, processing loop, shutdown export |
| Config | `app/config.py` | All tunable constants |
| Frame receiver | `app/networking/video_server.py` | HTTP POST `/frame` handler |
| Frame buffer | `app/networking/frame_buffer.py` | Single-slot keep-latest buffer, async get/put |
| Metadata server | `app/networking/metadata_server.py` | WebSocket `/metadata`, broadcast to all clients |
| Models | `app/networking/models.py` | `FrameMetadata`, `MetadataResponse`, `DetectedObject`, `BBox` dataclasses |
| Pipeline | `app/processing/frame_pipeline.py` | Orchestrates decode → preprocess → detect → track → metrics |
| Preprocess | `app/processing/preprocess.py` | Grayscale, GaussianBlur, threshold |
| Detect | `app/processing/detect.py` | `detect_largest_contour()` — OpenCV contour detection |
| Fake detect | `app/processing/fake_detect.py` | Animated bbox, no OpenCV — used in fake mode |
| Tracker | `app/processing/track.py` | `SimpleTracker` — sequential ID assignment (not real tracking) |
| Metrics | `app/processing/metrics.py` | `MetricsTracker` → fps + latency_ms estimate |
| Debug window | `app/visualization/debug_window.py` | Optional OpenCV `imshow` window (main thread only) |
| ROS2 bridge | `app/ros2_bridge/` | Placeholder — not implemented in V1 |

### 3.2 Diagnostics (Laptop)

| Component | File | Responsibility |
|-----------|------|----------------|
| Session | `app/util/session.py` | Unique session ID, folder creation, config snapshot |
| Event log | `app/util/event_log.py` | Thread-safe JSONL writer |
| Recent store | `app/util/recent_store.py` | Rolling JSON window (`RecentStore`) + `ExceptionsLog` |
| Exporter | `app/util/exporter.py` | Bundles session files on shutdown |
| DiagnosticsBundle | `app/diagnostics.py` | Dataclass wiring session + events + timings + metadata + exceptions + exporter |
| Logging | `app/util/logging_utils.py` | Rotating file log `logs/visionlink.log`, console INFO, file DEBUG |

---

### 3.3 Android Phone

| Component | File | Responsibility |
|-----------|------|----------------|
| Entry point | `MainActivity.kt` | Lifecycle, permissions, session init, stale detection, debug panel, SNAP button |
| Camera | `camera/CameraController.kt` | CameraX setup, RGBA→JPEG encode, frame dispatch |
| Frame model | `camera/CameraFrame.kt` | Frame value object |
| Video sender | `network/VideoStreamClient.kt` | Owns `FrameSender`, thread pool, stats callback |
| Frame sender | `camera/FrameSender.kt` | HTTP POST per frame, send stats, EventLog |
| WS client | `network/MetadataWebSocketClient.kt` | OkHttp WebSocket, exponential backoff reconnect, metadata dispatch |
| Network models | `network/NetworkModels.kt` | `MetadataResponse`, `DetectedObject`, `BBox` — Kotlin serialization |
| Overlay view | `overlay/OverlayView.kt` | Custom View, holds state, triggers invalidate |
| Overlay renderer | `overlay/OverlayRenderer.kt` | Stateless Canvas drawing, coord scaling |
| Overlay models | `overlay/OverlayModels.kt` | `OverlayObject`, `OverlayState` |
| Debug panel | `ui/DebugPanel.kt` | Updates 5 TextViews, health coloring |
| Health state | `ui/MainScreen.kt` | `HealthState` enum (HEALTHY / STALE / DISCONNECTED) |
| Constants | `util/Constants.kt` | IP, ports, resolution, JPEG quality |

### 3.4 Diagnostics (Phone)

| Component | File | Responsibility |
|-----------|------|----------------|
| Session | `util/SessionManager.kt` | Session ID, `filesDir/sessions/<id>/`, config snapshot |
| Event log | `util/EventLog.kt` | JSONL writer + `appendException()` |
| Recent store | `util/RecentStore.kt` | Rolling JSON window, flushed to disk on each push |
| Export manager | `util/ExportManager.kt` | Bundles session files on app destroy |
| Snapshot manager | `util/SnapshotManager.kt` | On-demand numbered snapshot (`snapshot_NNN/`) |

---

## 4. Diagnostics System

### 4.1 Session Folders

Each run creates a unique session on both sides:

**Laptop:**
```
laptop-server/
└── sessions/
    └── 20260317_143022_a3f9b1/
        ├── config_snapshot.json      ← laptop config at startup
        ├── events.jsonl              ← structured event log
        ├── recent_timings.json       ← last 50 pipeline timings
        ├── recent_metadata.json      ← last 20 broadcast metadata frames
        ├── exceptions.txt            ← exception text + tracebacks
        └── export_bundle/            ← created on shutdown
            ├── config_snapshot.json
            ├── events.jsonl
            ├── recent_timings.json
            ├── recent_metadata.json
            ├── exceptions.txt
            └── manifest.json
```

**Phone:**
```
filesDir/
└── sessions/
    └── 20260317_143025_c7d2e8/
        ├── config_snapshot.json      ← phone config at startup
        ├── events.jsonl              ← structured event log
        ├── recent_send_stats.json    ← last 50 send stats
        ├── recent_metadata_stats.json ← last 20 received metadata
        ├── app_state.json            ← last saved state snapshot
        ├── exceptions.txt            ← exception text
        ├── snapshots/
        │   ├── snapshot_001/         ← manual SNAP captures
        │   │   ├── app_state.json
        │   │   ├── recent_metadata_stats.json
        │   │   ├── recent_send_stats.json
        │   │   └── snapshot_meta.json
        │   └── snapshot_002/
        └── export_bundle/            ← created on app destroy
```

---

### 4.2 events.jsonl Schema

One JSON object per line:

```json
{"ts": 1742218222431, "session_id": "20260317_143022_a3f9b1", "component": "frame_pipeline", "level": "DEBUG", "event": "frame_processed", "frame_id": 1042, "fps": 28.3, "latency_ms": 47.0, "total_ms": 3.2, "objects": 1}
```

**Standard fields:** `ts` (epoch ms), `session_id`, `component`, `level`, `event`
**Extra fields:** event-specific key/value pairs

**Key events logged:**

| Component | Event | Key Fields |
|-----------|-------|------------|
| `main` | `app_start`, `app_stop` | `session_id` |
| `main` | `config_loaded` | all config values |
| `video_server` | `frame_received` | `frame_id`, `size_bytes`, `arrival_latency_ms` |
| `frame_buffer` | `frame_buffer_overwrite` | `frame_id` (processor is lagging) |
| `frame_pipeline` | `frame_processed` | `frame_id`, `fps`, `latency_ms`, `total_ms`, `objects` |
| `frame_pipeline` | `pipeline_exception` | `frame_id`, `stage`, `error` |
| `ws_server` | `client_connected`, `client_disconnected` | `remote`, `total_clients` |
| `ws_server` | `metadata_broadcast` | `frame_id`, `payload_bytes`, `clients` |
| `camera` | `camera_started` | `width`, `height`, `jpeg_quality` |
| `camera` | `camera_encode_error` | `frame_id`, `stage`, `error` |
| `ws_client` | `websocket_connect`, `websocket_disconnect` | `url`, `reconnect_attempts` |
| `ws_client` | `metadata_received` | `frame_id`, `fps`, `objects` |
| `ws_client` | `metadata_parse_failed` | `packet_num`, `error`, `raw_preview` |
| `main` (phone) | `overlay_updated` | `frame_id`, `objects` |
| `main` (phone) | `metadata_stale` | `age_ms` |
| `snapshot` | `snapshot_captured` | `label`, `reason`, `path` |

---

### 4.3 Snapshot System

The SNAP button (top-right corner of phone UI) captures the exact system state at that instant:

```
Tap SNAP
  → SnapshotManager.capture()
  → sessions/<id>/snapshots/snapshot_NNN/
      app_state.json           ← full live state at tap time
      recent_metadata_stats.json  ← last 20 metadata packets
      recent_send_stats.json   ← last 50 send stats
      snapshot_meta.json       ← { index, label, reason, captured_at, session_id }
  → EventLog event: snapshot_captured
  → Toast: "Snapshot saved: snapshot_001"
```

Use this immediately when something looks wrong — lag spike, overlay misalignment, detection dropout. The snapshot folder is numbered and persists until you pull the export bundle.

To pull from device:
```bash
adb pull /data/data/com.jake.visionphone/files/sessions/ ./phone_sessions/
```

---

## 5. HMI / Debug Panel

The debug panel is a semi-transparent bar pinned to the bottom of the screen. Five rows:

| Row | TextView | Content | Example |
|-----|----------|---------|---------|
| 1 | `tvMode` | Detection mode + laptop IP | `mode: real  \|  IP: 192.168.1.226` |
| 2 | `tvFps` | Pipeline FPS + frame counters | `FPS: 28.3  \|  sent: 1042  fail: 0` |
| 3 | `tvLatency` | Pipeline timing breakdown | `pipeline: 47ms est  \|  send: 12ms  size: 43KB  enc: 8ms` |
| 4 | `tvFrameIds` | Frame ID sync + metadata age + health | `sent: #1042  \|  meta: #1040  \|  age: 72ms  \|  HEALTHY` |
| 5 | `tvStatus` | WebSocket connection state | `Receiving` |

**Row 4 color codes health state:**

| State | Color | Meaning |
|-------|-------|---------|
| `HEALTHY` | Green | Metadata arriving within 500 ms |
| `STALE` | Yellow | No metadata received for >500 ms; overlay cleared |
| `DISCONNECTED` | Red | WebSocket not connected |

**Row 5 connection states:** `Connecting…`, `Connected`, `Receiving`, `Disconnected (reconnects: N)`

**Stale detection:** A 100 ms Handler loop checks whether the last metadata message arrived more than 500 ms ago. On crossing the threshold: overlay clears, health turns STALE, `app_state.json` is saved, event logged. Recovers automatically when metadata resumes.

---

## 6. Configuration

### 6.1 Phone — must change before first run

File: [phone-app/app/src/main/java/com/jake/visionphone/util/Constants.kt](phone-app/app/src/main/java/com/jake/visionphone/util/Constants.kt)

```kotlin
const val LAPTOP_IP      = "192.168.1.226"   // ← your laptop's Wi-Fi IP
const val FRAME_PORT     = 8080
const val METADATA_WS_PORT = 8081
const val FRAME_WIDTH    = 1280
const val FRAME_HEIGHT   = 720
const val JPEG_QUALITY   = 80
```

### 6.2 Laptop — key toggles

File: [laptop-server/app/config.py](laptop-server/app/config.py)

```python
FAKE_DETECTION_MODE = False   # True = animated bbox, no OpenCV
DEBUG_WINDOW        = True    # False if no display connected
TARGET_FPS          = 30
FRAME_WIDTH         = 1280
FRAME_HEIGHT        = 720
JPEG_QUALITY        = 80
```

---

## 7. Bring-Up Procedure

### Phase A — Laptop only, fake mode

1. Set `FAKE_DETECTION_MODE = True`, `DEBUG_WINDOW = False` in `config.py`
2. Install deps: `pip install -r requirements.txt`
3. Start server: `python -m app.main` from `laptop-server/`
4. Verify startup banner shows session ID and both ports
5. Check `sessions/<id>/events.jsonl` contains `app_start` + `config_loaded` entries
6. Check `sessions/<id>/config_snapshot.json` is present

### Phase B — Full loop, fake detection

1. Confirm `LAPTOP_IP` in `Constants.kt` matches your laptop's Wi-Fi IP
2. Phone and laptop on same Wi-Fi network
3. Build + deploy phone app from Android Studio
4. Grant camera permission
5. Verify on phone debug panel:
   - Row 1: `mode: fake  |  IP: 192.168.1.226`
   - Row 2: FPS ticking, sent count incrementing
   - Row 4: frame IDs incrementing both sides, health GREEN
   - Row 5: `Receiving`
6. Verify an animated bounding box is moving on-screen
7. Tap SNAP — toast confirms, check `snapshots/snapshot_001/` via adb pull

### Phase C — Real OpenCV detection

1. Set `FAKE_DETECTION_MODE = False` in `config.py`
2. Optionally set `DEBUG_WINDOW = True` if laptop has a display
3. Restart laptop server
4. Phone panel Row 1 should now show `mode: real`
5. Point camera at a bright object on dark background — contour should be detected
6. Verify bounding box appears on phone overlay

### Phase D — Stability / failure testing

Force each failure mode and confirm recovery:

| Test | How | Expected |
|------|-----|----------|
| Network drop | Disable Wi-Fi on phone briefly | Panel: DISCONNECTED, then reconnects with backoff |
| Kill server | Ctrl+C laptop | Panel: reconnect attempts count up |
| Stale stream | Block camera | Panel: STALE (yellow) within 500 ms, overlay clears |
| Resume | Unblock / reconnect | Auto-recovers, health returns GREEN |

---

## 8. Expected Performance (Baseline)

Rough targets on a local Wi-Fi network (same subnet, 5 GHz recommended):

| Metric | Expected Range | Notes |
|--------|---------------|-------|
| End-to-end FPS | 15–30 | Limited by encode + send + pipeline |
| `latency_ms` estimate | 40–120 ms | Clock-drift affected; treat as relative |
| JPEG encode time (`enc`) | 5–15 ms | Varies by device |
| HTTP send time (`send`) | 10–40 ms | Highly network-dependent |
| Pipeline total (`total_ms`) | 2–10 ms | Fake mode ~0.5 ms; real mode varies with lighting |
| JPEG frame size | 25–80 KB | At quality 80, 1280×720 |

If `send` ms is consistently above 60 ms or FPS drops below 10, check:
1. Wi-Fi band (5 GHz vs 2.4 GHz)
2. `JPEG_QUALITY` (try 60)
3. Resolution (`FRAME_WIDTH` / `FRAME_HEIGHT`)

---

## 9. Known Limitations

| Limitation | Detail |
|------------|--------|
| Detector is not AI | OpenCV threshold + largest contour only. Brittle to lighting, shadows, clutter. One object max. |
| Tracker is not real tracking | `SimpleTracker` assigns sequential IDs. No motion prediction, no re-ID across occlusions. |
| Latency is estimated | Clock drift between phone and laptop makes `latency_ms` a rough estimate. Not a true RTT. |
| Overlay may misalign | `OverlayRenderer` scales by `viewW/source_width` and `viewH/source_height`. If PreviewView aspect ratio differs from 16:9, boxes will shift. |
| Rear camera assumed | `CameraSelector.DEFAULT_BACK_CAMERA` is hardcoded. |
| HTTP per frame | Not suitable for production. Intentional V1 simplification — one connection per frame, no WebRTC, no streaming protocol. |
| Single WebSocket client | `MetadataServer` broadcasts to all connected clients, but V1 is designed for one phone. |
| No auth | All endpoints are unauthenticated. Local Wi-Fi only. |

---

## 10. Failure Modes — Where to Look

| Symptom | Likely Cause | Where to Look |
|---------|-------------|---------------|
| Panel stays DISCONNECTED | Wrong IP, firewall, or server not running | `Constants.kt` IP, laptop server running, same Wi-Fi |
| Panel STALE (yellow) | Server running but no results returning | `events.jsonl` for `frame_processed` gaps; check `frame_buffer_overwrite` rate |
| No overlay boxes in real mode | Lighting / threshold | `detect.py` threshold value; OpenCV debug window on laptop |
| Overlay boxes offset/shifted | Aspect ratio / scaling | `OverlayRenderer.kt:35-36`; compare `sourceWidth/sourceHeight` vs view dims |
| High `send` ms in panel | JPEG too large or network congestion | Reduce `JPEG_QUALITY`; check `recent_send_stats.json` for `jpeg_kb` trend |
| High `enc` ms in panel | JPEG encode slow on device | `CameraController.kt` — bitmapToJpeg; try lower resolution |
| High `latency_ms` estimate | Pipeline backlog | `recent_timings.json` `total_ms`; check `frame_buffer_overwrite` events |
| Boxes disappear briefly | Stale detection triggering | `events.jsonl` for `metadata_stale`; check `age_ms` |
| Reconnect count climbing | Intermittent network | WebSocket logs in `events.jsonl`; check Wi-Fi signal |
| Parse errors in WS logs | Schema mismatch | `metadata_parse_failed` events; compare `NetworkModels.kt` vs `models.py` |
| `frame_buffer_overwrite` frequent | Pipeline slower than camera | Reduce `TARGET_FPS` or `FRAME_WIDTH/HEIGHT` in config |
| Exceptions in `exceptions.txt` | Pipeline crash at a stage | Full traceback in file; `pipeline_exception` event has stage name |

---

## 11. File Map — Quick Reference

```
laptop-server/
├── app/main.py                    Entry point, wiring, processing loop
├── app/config.py                  All constants — change before running
├── app/diagnostics.py             DiagnosticsBundle + make_diagnostics()
├── app/networking/
│   ├── video_server.py            POST /frame handler
│   ├── frame_buffer.py            Single-slot async keep-latest buffer
│   ├── metadata_server.py         WebSocket /metadata broadcast
│   └── models.py                  FrameMetadata, MetadataResponse, BBox, DetectedObject
├── app/processing/
│   ├── frame_pipeline.py          Orchestrator — all stages + timing
│   ├── preprocess.py              Grayscale → blur → threshold
│   ├── detect.py                  Largest contour → BBox
│   ├── fake_detect.py             Animated bbox (no OpenCV)
│   ├── track.py                   SimpleTracker (ID assignment)
│   └── metrics.py                 FpsCounter, latency estimate
├── app/visualization/
│   └── debug_window.py            Optional cv2.imshow window
├── app/util/
│   ├── session.py                 Session ID + folder creation
│   ├── event_log.py               JSONL event writer
│   ├── recent_store.py            Rolling JSON window + exceptions log
│   ├── exporter.py                Shutdown export bundle
│   └── logging_utils.py           Rotating file log setup
└── app/ros2_bridge/               Placeholder — V2 only

phone-app/app/src/main/java/com/jake/visionphone/
├── MainActivity.kt                Lifecycle, stale loop, SNAP button
├── camera/
│   ├── CameraController.kt        CameraX, JPEG encode, frame dispatch
│   └── CameraFrame.kt             Frame value object
├── network/
│   ├── VideoStreamClient.kt       Thread pool, FrameSender owner
│   ├── MetadataWebSocketClient.kt OkHttp WS, reconnect backoff
│   └── NetworkModels.kt           MetadataResponse, DetectedObject (kotlinx serialization)
├── overlay/
│   ├── OverlayView.kt             Custom View, state holder
│   ├── OverlayRenderer.kt         Canvas draw + coordinate scaling  ← overlay alignment
│   └── OverlayModels.kt           OverlayObject, OverlayState
├── ui/
│   ├── DebugPanel.kt              5-TextView panel, health coloring
│   └── MainScreen.kt              HealthState enum
└── util/
    ├── Constants.kt               IP, ports, resolution  ← change before running
    ├── SessionManager.kt          Session ID + folder
    ├── EventLog.kt                JSONL writer + exceptions
    ├── RecentStore.kt             Rolling JSON window
    ├── ExportManager.kt           Shutdown export bundle
    └── SnapshotManager.kt         On-demand SNAP captures
```
