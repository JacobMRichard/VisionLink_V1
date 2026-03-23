HOST = "0.0.0.0"
FRAME_PORT = 8080       # HTTP POST endpoint: phone → laptop
METADATA_PORT = 8081    # WebSocket endpoint:  laptop → phone

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

# ── V2 Memory system ───────────────────────────────────────────────────────
MEMORY_DATA_DIR = "memory_data"

# Crop extraction
CROP_MARGIN_PX    = 10     # pixels of padding added around each detected bbox
EDGE_CLIP_MARGIN  = 5      # pixels from edge that counts as "clipped"

# Crop quality gating
CROP_MIN_SIDE_PX      = 40      # reject crop if min(w,h) < this
CROP_MIN_CONFIDENCE   = 0.35    # reject crop if detector confidence < this
CROP_MAX_ASPECT       = 8.0     # reject crop if max/min side ratio > this
BLUR_SHARP_THRESHOLD  = 200.0   # Laplacian variance considered "sharp" (calibrate on your camera)
BLUR_MIN_SCORE        = 0.15    # normalised blur score below this → rejected as blurry

# Embedding / descriptor
EMBEDDING_DIM = 2048    # ResNet-50 output dimension

# Embedding retrieval
TOP_K_CANDIDATES = 5    # max candidates to retrieve from FAISS per crop

# Identity matching thresholds
MATCH_KNOWN_THRESHOLD     = 0.75   # composite score >= this → known_match
MATCH_AMBIGUOUS_THRESHOLD = 0.50   # composite score >= this → ambiguous_candidate

# Match cue weights (must not necessarily sum to 1.0; composite is a weighted sum)
EMBEDDING_WEIGHT = 0.65
COLOR_WEIGHT     = 0.25
LABEL_WEIGHT     = 0.10

# Memory management
MAX_EXEMPLARS         = 10   # max crop images kept per object
STABLE_SEEN_THRESHOLD = 3    # times_seen before provisional → stable
