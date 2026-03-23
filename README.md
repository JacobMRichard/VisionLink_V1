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

**Phone → Laptop:** JPEG frames via HTTP POST to port 8080. Headers carry frame ID, timestamp, resolution.

**Laptop → Phone:** JSON metadata via WebSocket on port 8081. Each message contains detected/tracked objects with bounding boxes, contours, centroids, confidence, and track state.

---

## What it does

- Detects and tracks up to 10 objects simultaneously using YOLOv8n (80 COCO classes)
- Maintains stable numeric IDs (1–10) across frames using a custom IoU + centroid tracker
- Renders a live overlay on the phone: bounding boxes, object labels, centroid dots
- Handles occlusion and re-appearance — lost tracks recover their original ID
- Prioritizes objects based on confidence, size, and floor position (floor-biased for navigation use cases)
- Displays per-object track state: confirmed (solid), candidate (semi-transparent), lost (dashed)
- Drops frames under load via `LatestFrameBuffer` — inference always runs on the freshest available frame

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

Two-pass greedy matching: active tracks are matched first, then remaining detections are offered to lost tracks for recovery. This prevents active tracks from being stolen by lost-track recovery logic.

### Async pipeline — `laptop-server/app/`
Python `asyncio` + `aiohttp` with two independent HTTP servers (frame receiver + WebSocket broadcaster). A `LatestFrameBuffer` decouples the receive rate from the inference rate — frames are dropped rather than queued, keeping latency low. Processing runs in a dedicated task.

### Android client — `phone-app/`
Kotlin + CameraX + OkHttp + kotlinx.serialization. A background coroutine streams frames; a WebSocket client receives metadata. The overlay is a custom `OverlayView` (Canvas-based) that renders directly on top of the camera preview with no intermediate bitmaps.

---

## Stack

| Layer | Technology |
|---|---|
| Android | Kotlin, CameraX, OkHttp, kotlinx.serialization, ViewBinding |
| Python server | Python 3.11, asyncio, aiohttp, OpenCV, NumPy |
| Detection | YOLOv8n (Ultralytics) — CPU inference |
| Tracking | Custom CentroidIoU tracker (no external lib) |
| Transport | HTTP (frames), WebSocket (metadata) |
| Build | Gradle KTS, AGP 8.3.2, Conda |

---

## Project structure

```
VisionLinkV1/
├── laptop-server/
│   ├── app/
│   │   ├── main.py                  Entry point
│   │   ├── config.py                All tunable parameters
│   │   ├── networking/
│   │   │   ├── video_server.py      Receives JPEG frames via HTTP POST
│   │   │   ├── metadata_server.py   Broadcasts JSON metadata via WebSocket
│   │   │   └── frame_buffer.py      LatestFrameBuffer — drops stale frames
│   │   ├── processing/
│   │   │   ├── frame_pipeline.py    Orchestrates decode → detect → track → serialize
│   │   │   ├── detect.py            YOLOv8n inference → RawDetection list
│   │   │   ├── tracker.py           CentroidIoUTracker
│   │   │   └── tracked_object.py    TrackedObject / RawDetection dataclasses
│   │   └── util/
│   │       └── logging_utils.py
│   └── requirements.txt
└── phone-app/
    └── app/src/main/java/com/jake/visionphone/
        ├── MainActivity.kt
        ├── camera/                  CameraX capture + frame encoding
        ├── network/                 HTTP sender + WebSocket receiver
        ├── overlay/                 OverlayView + OverlayRenderer + models
        └── util/                    Constants, session utilities
```

---

## Running it

### Laptop server

```bash
conda create -n visionlink python=3.11
conda activate visionlink
pip install -r laptop-server/requirements.txt

# Set your laptop's Wi-Fi IP in laptop-server/app/config.py (HOST)
cd laptop-server
python -m app.main
```

### Android app

1. Open `phone-app/` in Android Studio
2. Set `LAPTOP_IP` in `app/src/main/java/com/jake/visionphone/util/Constants.kt`
3. Run on a physical device (USB debug or wireless ADB)

Both phone and laptop must be on the same Wi-Fi network.

---

## V2 roadmap

- YOLO segmentation masks (instance-level contours)
- ROS 2 bridge for robotics integration
- IMU fusion for camera-motion-aware tracking
- WebRTC transport (lower latency than HTTP)
- SLAM integration

---

## Why this project

VisionLink V1 is a proof-of-concept for offloading perception from a mobile device to a nearby compute node — a pattern relevant to assistive robotics, AR navigation aids, and any edge-compute scenario where the capture device is resource-constrained. The focus for V1 was validating the full round-trip loop with real detection and stable tracking before adding more complex components.
