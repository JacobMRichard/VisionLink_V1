# ── Discord notifications ───────────────────────────────────────────────────
# Paste your Discord webhook URL here. Leave empty to disable notifications.
DISCORD_WEBHOOK_URL = ""  # Paste your webhook URL here — never commit it

# Minimum seconds between notifications for the same object class.
NOTIFICATION_COOLDOWN_S = 30.0

# ── Class groups (for MCP filter commands) ──────────────────────────────────
# Used by the MCP server so you can say "track people" or "track animals".
# Each key maps to a list of YOLO COCO class names.
CLASS_GROUPS: dict = {
    "people":      ["person"],
    "animals":     ["bird", "cat", "dog", "horse", "sheep", "cow",
                    "elephant", "bear", "zebra", "giraffe"],
    "pets":        ["cat", "dog"],
    "vehicles":    ["bicycle", "car", "motorcycle", "airplane",
                    "bus", "train", "truck", "boat"],
    "electronics": ["tv", "laptop", "mouse", "remote", "keyboard", "cell phone"],
    "furniture":   ["chair", "couch", "bed", "dining table", "toilet"],
    "food":        ["banana", "apple", "sandwich", "orange", "broccoli",
                    "carrot", "hot dog", "pizza", "donut", "cake"],
    "sports":      ["frisbee", "skis", "snowboard", "sports ball", "kite",
                    "baseball bat", "baseball glove", "skateboard",
                    "surfboard", "tennis racket"],
    "kitchen":     ["bottle", "wine glass", "cup", "fork", "knife",
                    "spoon", "bowl"],
}

HOST = "0.0.0.0"
FRAME_PORT = 8090       # HTTP POST endpoint: phone → laptop
METADATA_PORT = 8091    # WebSocket endpoint:  laptop → phone

TARGET_FPS = 30
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
JPEG_QUALITY = 80

# Show OpenCV debug window on the laptop
# NOTE: cv2.imshow must run from the main thread on some platforms.
# Set False if you see display errors.
DEBUG_WINDOW = True

# Fake detection mode — sends an animated bbox back to the phone WITHOUT
# running any OpenCV.  Use this first to prove the overlay + WebSocket path
# before worrying about real detection quality.
FAKE_DETECTION_MODE = False

# ── YOLO detection ─────────────────────────────────────────────────────────
# yolov8n.pt (~6 MB) is auto-downloaded to ~/.cache/ultralytics/ on first run.
# Requires: pip install ultralytics  (pulls in PyTorch, ~500 MB first install)
MODEL_PATH = "yolov8n.pt"

# Detections below this confidence are ignored before reaching the tracker.
CONFIDENCE_THRESHOLD = 0.4

# ── Tracker ────────────────────────────────────────────────────────────────
# Frames a track must be seen before moving CANDIDATE → CONFIRMED (shown on phone).
TRACK_CONFIRM_FRAMES = 3

# Consecutive missed frames before CONFIRMED → LOST.
TRACK_LOST_FRAMES = 4

# Additional frames in LOST state before the track is removed entirely.
TRACK_EXPIRE_FRAMES = 3

# Maximum confirmed + candidate tracks returned per frame.
MAX_TRACKED_OBJECTS = 10

# ── Matching ───────────────────────────────────────────────────────────────
# Weights for greedy cost function: cost = IOU_WEIGHT*(1-iou) + DISTANCE_WEIGHT*norm_dist
IOU_WEIGHT      = 0.5
DISTANCE_WEIGHT = 0.5

# Cost threshold above which a detection won't be matched to any existing track.
MAX_MATCH_COST = 0.7

# Centroid distance (pixels) that maps to a normalized distance of 1.0.
# Detections farther than this from a track are effectively unmatched.
MAX_CENTROID_DISTANCE = 300.0

# ── Floor preference ───────────────────────────────────────────────────────
# Weight of floor_score in the priority calculation (0.0 = disabled).
# floor_score = centroid_y / frame_height, so objects lower in frame are preferred.
FLOOR_WEIGHT = 0.2
