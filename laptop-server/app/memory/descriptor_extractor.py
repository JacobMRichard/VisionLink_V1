"""
DescriptorExtractor — extracts multi-cue descriptors for accepted crops.

Descriptors:
  - embedding:   2048-dim ResNet-50 feature vector (L2-normalised)
  - color_hist:  HSV histogram (8×8×8 bins, normalised to sum=1)
  - shape:       aspect ratio, contour extent, area fraction of frame

The ResNet-50 backbone is loaded once on first call (lazy init).
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np

import app.config as config

log = logging.getLogger(__name__)

# ── Lazy model state ──────────────────────────────────────────────────────────
_model = None
_transform = None


def _load_model() -> None:
    global _model, _transform
    if _model is not None:
        return
    import torch
    import torchvision.models as tv_models

    log.info("descriptor_extractor: loading ResNet-50 …")
    weights = tv_models.ResNet50_Weights.DEFAULT
    backbone = tv_models.resnet50(weights=weights)
    backbone.fc = torch.nn.Identity()   # strip classifier → 2048-dim output
    backbone.eval()
    _model = backbone
    _transform = weights.transforms()
    log.info("descriptor_extractor: ResNet-50 ready")


# ── Public data type ──────────────────────────────────────────────────────────

@dataclass
class DescriptorRecord:
    crop_id: str
    snapshot_id: str
    label: str
    confidence: float
    quality_score: float
    embedding: List[float]          # 2048-dim, L2-normalised
    color_hist: List[float]         # flattened 8×8×8 HSV histogram
    shape: dict = field(default_factory=dict)


# ── Extraction ────────────────────────────────────────────────────────────────

def extract(
    crop_id: str,
    snapshot_id: str,
    label: str,
    confidence: float,
    quality_score: float,
    image: np.ndarray,
    frame_area: Optional[int] = None,
) -> Optional[DescriptorRecord]:
    """
    Extract all descriptors for a single accepted crop (BGR ndarray).
    Returns None if extraction fails.
    """
    _load_model()
    if image is None or image.size == 0:
        log.warning("descriptor_extractor: empty image for %s", crop_id)
        return None

    try:
        embedding  = _embedding(image)
        color_hist = _color_histogram(image)
        shape      = _shape_descriptor(image, frame_area)
    except Exception as exc:
        log.warning("descriptor_extractor: failed for %s: %s", crop_id, exc)
        return None

    return DescriptorRecord(
        crop_id=crop_id,
        snapshot_id=snapshot_id,
        label=label,
        confidence=confidence,
        quality_score=quality_score,
        embedding=embedding,
        color_hist=color_hist,
        shape=shape,
    )


# ── Private helpers ───────────────────────────────────────────────────────────

def _embedding(image: np.ndarray) -> List[float]:
    """ResNet-50 feature vector, L2-normalised."""
    import torch
    from PIL import Image as PILImage

    rgb     = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pil_img = PILImage.fromarray(rgb)
    tensor  = _transform(pil_img).unsqueeze(0)   # (1, 3, H, W)
    with torch.no_grad():
        feat = _model(tensor)                     # (1, 2048)
    vec  = feat[0].numpy().astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec.tolist()


def _color_histogram(image: np.ndarray) -> List[float]:
    """Flattened, normalised 8×8×8 HSV histogram."""
    hsv  = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 8],
                        [0, 180, 0, 256, 0, 256])
    hist = hist.flatten().astype(np.float32)
    total = hist.sum()
    if total > 0:
        hist /= total
    return hist.tolist()


def _shape_descriptor(image: np.ndarray, frame_area: Optional[int]) -> dict:
    """Aspect ratio, contour extent, and area fraction relative to frame."""
    h, w   = image.shape[:2]
    aspect = round(w / max(h, 1), 4)
    area   = w * h
    area_frac = round(area / frame_area, 6) if frame_area else None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        cnt_area = sum(cv2.contourArea(c) for c in contours)
        extent   = round(cnt_area / max(area, 1), 4)
    else:
        extent = 0.0

    return {"aspect": aspect, "extent": extent, "area_frac": area_frac}
