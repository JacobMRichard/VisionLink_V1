"""
CropExtractor — crops individual detected objects from a full snapshot image.

Each crop is saved under snap_dir/crops/.
Invalid crops (zero area, badly clipped) are rejected here.

Saves:  snap_dir/crops/det_0001.jpg  ...
Returns a list of CropRecord.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

import cv2
import numpy as np

import app.config as config
from app.processing.tracked_object import RawDetection

log = logging.getLogger(__name__)


@dataclass
class CropRecord:
    crop_id: str
    snapshot_id: str
    image_path: str
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    padded_x: int
    padded_y: int
    padded_w: int
    padded_h: int
    label: str
    confidence: float
    clipped: bool


def extract(
    snap_dir: Path,
    snapshot_id: str,
    image: np.ndarray,
    detections: List[RawDetection],
) -> List[CropRecord]:
    """
    Crop all detected objects from *image* (full BGR numpy array).
    Returns accepted CropRecord list; saves crop images to disk.
    """
    crops_dir = snap_dir / "crops"
    crops_dir.mkdir(exist_ok=True)

    h, w = image.shape[:2]
    margin = config.CROP_MARGIN_PX
    records: List[CropRecord] = []

    for i, det in enumerate(detections):
        # Apply padding, clamped to image bounds
        x1 = max(0, det.bbox_x - margin)
        y1 = max(0, det.bbox_y - margin)
        x2 = min(w, det.bbox_x + det.bbox_w + margin)
        y2 = min(h, det.bbox_y + det.bbox_h + margin)

        pw, ph = x2 - x1, y2 - y1
        if pw <= 0 or ph <= 0:
            log.debug("crop %d rejected: zero area", i)
            continue

        # Detect edge clipping: original bbox touches frame edge
        clipped = (
            det.bbox_x <= config.EDGE_CLIP_MARGIN
            or det.bbox_y <= config.EDGE_CLIP_MARGIN
            or (det.bbox_x + det.bbox_w) >= (w - config.EDGE_CLIP_MARGIN)
            or (det.bbox_y + det.bbox_h) >= (h - config.EDGE_CLIP_MARGIN)
        )

        crop = image[y1:y2, x1:x2]
        crop_id = f"det_{i + 1:04d}"
        crop_path = crops_dir / f"{crop_id}.jpg"
        cv2.imwrite(str(crop_path), crop)

        records.append(CropRecord(
            crop_id=crop_id,
            snapshot_id=snapshot_id,
            image_path=str(crop_path),
            bbox_x=det.bbox_x,
            bbox_y=det.bbox_y,
            bbox_w=det.bbox_w,
            bbox_h=det.bbox_h,
            padded_x=x1,
            padded_y=y1,
            padded_w=pw,
            padded_h=ph,
            label=det.label,
            confidence=det.confidence,
            clipped=clipped,
        ))

    log.info("crop_extractor: %d crops saved  snap=%s", len(records), snap_dir.name)
    return records
