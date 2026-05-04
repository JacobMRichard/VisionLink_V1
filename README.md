# VisionLink V1

**Real-time split-compute perception pipeline — Android phone + Python laptop, end-to-end.**

An Android phone streams live camera frames over Wi-Fi to a laptop running YOLOv8 object detection. Detected and tracked objects are sent back to the phone as metadata, rendered as a live AR overlay on the camera preview. The phone never runs inference — it's a pure capture + display client.

---

## Architecture

```
┌──────────────────────┐         Wi-Fi          ┌──────────────────────────┐
│   Android Phone      │ ──── JPEG frames ────► │   Laptop (Python)        │
│                      │                         │                          │
│  CameraX capture     │ ◄── WebSocket JSON ──── │  YOLOv8n inference       │
│  HTTP POST sender    │     (metadata)          │  CentroidIoU tracker     │
│  AR overlay renderer │                         │  aiohttp async server    │
└──────────────────────┘                         └──────────────────────────┘
```

**Phone → Laptop:** JPEG frames via HTTP POST to port 8090. Headers carry frame ID, timestamp, resolution.

**Laptop → Phone:** JSON metadata via WebSocket on port 8091. Each message contains detected/tracked objects with bounding boxes, centroids, confidence, and track state.

---

## What it does

- Detects and tracks up to 10 objects simultaneously using YOLOv8n (80 COCO classes)
- Maintains stable numeric IDs across frames using a custom IoU + centroid tracker
- Renders a live overlay on the phone: bounding boxes, object labels, centroid dots
- Handles occlusion and re-appearance — lost tracks recover their original ID
- Prioritizes objects based on confidence, size, and floor position
- Displays per-object track state: confirmed (solid), candidate (semi-transparent), lost (dashed)
- Drops frames under load via `LatestFrameBuffer` — inference always runs on the freshest available frame
- Live runtime control via MCP — change what's tracked without restarting the server
- Discord notifications when specific objects are detected — off by default, on-demand only

---

## Live control via MCP

VisionLink includes an MCP server that gives Claude direct live access to the running pipeline. You can give natural-language commands in the chat and they execute immediately:

| Command | What happens |
|---|---|
| `track people` | Filters to person class only |
| `track dog` | Filters to dog class only |
| `track human, dog, cat` | Tracks all three simultaneously |
| `track everything` | Removes all filters |
| `track 1 person` | Tracks highest-priority person only |
| `notify me of cats` | Enables Discord alerts for cat detections |
| `notify of banana` | Enables Discord alerts for banana detections |
| `stop notifications` | Disables all Discord alerts |
| `confidence higher` | Raises detection threshold (fewer, more certain) |
| `reset everything` | Restores all defaults |

Start the MCP server alongside the main server:

```bash
# Terminal 1 — main server
cd laptop-server
python -m app.main

# Terminal 2 — MCP server (Claude tool access)
cd laptop-server
python -m app.mcp_server
```

---

## Discord notifications

When enabled, VisionLink posts to a Discord webhook when a confirmed object is detected. Notifications are:
- **Off by default** — must be explicitly enabled per session
- **Rate-limited** — 30s cooldown per class to avoid spam
- **Class-scoped** — only fires for whatever class filter is currently active

Set your webhook URL in `laptop-server/app/config.py`:
```python
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."
```

---

## Technical highlights

### Tracker — `laptop-server/app/processing/tracker.py`
Custom `CentroidIoUTracker` with a three-state machine:

```
CANDIDATE → CONFIRMED  after N matched detections  (filters false positives)
CONFIRMED → LOST       after N consecutive misses   (handles occlusion)
LOST      → CONFIRMED  if re-matched before expiry  (recovers original ID)
LOST      → expired    after expiry window
```

Two-pass greedy matching: active tracks matched first, then remaining detections offered to lost tracks for recovery.

### Async pipeline — `laptop-server/app/`
Python `asyncio` + `aiohttp` with two independent HTTP servers (frame receiver + WebSocket broadcaster). A `LatestFrameBuffer` decouples receive rate from inference rate — frames are dropped rather than queued. YOLO runs in a `ThreadPoolExecutor` to avoid blocking the event loop.

### Zero-queue phone sender — `phone-app/.../camera/FrameSender.kt`
Uses an `AtomicReference` single-slot pattern: new frames always replace any pending frame. No queue buildup under load — guaranteed single-frame latency on the send path.

### Non-blocking logging
Both laptop (Python `QueueHandler`/`QueueListener`) and phone (Android `HandlerThread`) write logs on background threads. The pipeline thread never waits on disk I/O.

### Android client — `phone-app/`
Kotlin + CameraX + OkHttp + kotlinx.serialization. The overlay is a custom `OverlayView` (Canvas-based) that renders directly on top of the camera preview with no intermediate bitmaps.

---

## Stack

| Layer | Technology |
|---|---|
| Android | Kotlin, CameraX, OkHttp, kotlinx.serialization, ViewBinding |
| Python server | Python 3.11, asyncio, aiohttp, OpenCV, NumPy |
| Detection | YOLOv8n (Ultralytics) — CPU inference |
| Tracking | Custom CentroidIoU tracker (no external lib) |
| Transport | HTTP (frames), WebSocket (metadata) |
| Live control | MCP (Model Context Protocol) + FastMCP |
| Notifications | Discord webhooks via aiohttp |
| Build | Gradle KTS, AGP 8.3.2, Conda |

---

## Project structure

```
VisionLinkV1/
├── laptop-server/
│   ├── app/
│   │   ├── main.py                  Entry point
│   │   ├── config.py                All tunable parameters + webhook URL
│   │   ├── runtime_config.py        Thread-safe live settings (updated via /control)
│   │   ├── mcp_server.py            MCP server — Claude tool access
│   │   ├── notification_manager.py  Discord webhook sender
│   │   ├── diagnostics.py           Session + timing + event log wiring
│   │   ├── networking/
│   │   │   ├── video_server.py      Receives JPEG frames via HTTP POST
│   │   │   ├── metadata_server.py   Broadcasts JSON metadata via WebSocket
│   │   │   └── frame_buffer.py      LatestFrameBuffer — drops stale frames
│   │   ├── processing/
│   │   │   ├── frame_pipeline.py    Orchestrates decode → detect → track → serialize
│   │   │   ├── detect.py            YOLOv8n inference → RawDetection list
│   │   │   └── tracker.py           CentroidIoUTracker
│   │   ├── util/
│   │   │   ├── logging_utils.py     Async file logging (laptop.log + phone.log)
│   │   │   ├── session.py           Session ID + folder management
│   │   │   ├── event_log.py         Background event log writer
│   │   │   └── recent_store.py      Dirty-flag coalescing store
│   │   └── visualization/
│   │       └── debug_window.py      Optional OpenCV debug window
│   └── requirements.txt
└── phone-app/
    └── app/src/main/java/com/jake/visionphone/
        ├── MainActivity.kt
        ├── camera/                  CameraX capture + FrameSender (atomic slot)
        ├── network/                 HTTP sender + WebSocket receiver
        ├── overlay/                 OverlayView + OverlayRenderer + models
        └── util/                    Constants, EventLog (background HandlerThread)
```

---

## Running it

### Laptop server

```bash
conda create -n visionlink python=3.11
conda activate visionlink
pip install -r laptop-server/requirements.txt

cd laptop-server
python -m app.main
```

### MCP server (optional — enables Claude live control)

```bash
# In a second terminal, same conda env
cd laptop-server
python -m app.mcp_server
```

### Android app

1. Open `phone-app/` in Android Studio
2. Set `LAPTOP_IP` in `phone-app/app/src/main/java/com/jake/visionphone/util/Constants.kt`
3. Run on a physical device (USB debug or wireless ADB)

Both phone and laptop must be on the same Wi-Fi network.

---

## Easily trackable YOLO classes (by category)

| Class | Category |
|---|---|
| `person` | People |
| `dog` | Pets |
| `bird` | Wildlife |
| `car` | Vehicles |
| `bicycle` | Two-wheelers |
| `chair` | Furniture |
| `couch` | Seating |
| `bottle` | Kitchen |
| `cell phone` | Electronics |
| `laptop` | Computing |
| `sports ball` | Sports |
| `banana` | Produce |
| `pizza` | Food |
| `clock` | Home decor |
| `backpack` | Accessories |
| `umbrella` | Outdoor gear |

---

## V2 roadmap

- YOLO segmentation masks (instance-level contours)
- ROS 2 bridge for robotics integration
- IMU fusion for camera-motion-aware tracking
- WebRTC transport (lower latency than HTTP)
- SLAM integration

---

## Why this project

VisionLink V1 is a proof-of-concept for offloading perception from a mobile device to a nearby compute node — a pattern relevant to assistive robotics, AR navigation aids, and any edge-compute scenario where the capture device is resource-constrained. The focus for V1 was validating the full round-trip loop with real detection, stable tracking, and live control before adding more complex components.
