"""
CropQualityScorer — scores each crop for memory usefulness.

Checks:
  - blur / sharpness   (Laplacian variance)
  - minimum crop size
  - detector confidence
  - edge clipping
  - extreme aspect ratio

Returns a QualityResult per crop; accept_for_memory is True only when ALL
checks pass so that memory stays clean.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np

import app.config as config
from app.memory.crop_extractor import CropRecord

log = logging.getLogger(__name__)


@dataclass
class QualityResult:
    crop_id: str
    quality_score: float            # 0.0 – 1.0 composite
    accept_for_memory: bool
    blur_score: float               # raw Laplacian variance (higher = sharper)
    rejection_reasons: List[str] = field(default_factory=list)


def score(
    crop_record: CropRecord,
    image: Optional[np.ndarray] = None,
) -> QualityResult:
    """
    Score a single crop.
    Pass *image* (BGR numpy array) directly or leave None to load from disk.
    """
    reasons: List[str] = []

    if image is None:
        image = cv2.imread(crop_record.image_path)
    if image is None:
        return QualityResult(
            crop_id=crop_record.crop_id,
            quality_score=0.0,
            accept_for_memory=False,
            blur_score=0.0,
            rejection_reasons=["image_load_failed"],
        )

    h, w = image.shape[:2]

    # ── Blur score (Laplacian variance) ──────────────────────────────────────
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blur_score_norm = min(blur_var / config.BLUR_SHARP_THRESHOLD, 1.0)

    # ── Size check ───────────────────────────────────────────────────────────
    min_side = min(w, h)
    if min_side < config.CROP_MIN_SIDE_PX:
        reasons.append(f"too_small:{min_side}px")

    # ── Confidence check ─────────────────────────────────────────────────────
    if crop_record.confidence < config.CROP_MIN_CONFIDENCE:
        reasons.append(f"low_confidence:{crop_record.confidence:.2f}")

    # ── Edge clipping ─────────────────────────────────────────────────────────
    if crop_record.clipped:
        reasons.append("edge_clipped")

    # ── Aspect ratio check ────────────────────────────────────────────────────
    aspect = max(w, h) / max(min_side, 1)
    if aspect > config.CROP_MAX_ASPECT:
        reasons.append(f"bad_aspect:{aspect:.1f}")

    # ── Blur check ────────────────────────────────────────────────────────────
    if blur_score_norm < config.BLUR_MIN_SCORE:
        reasons.append(f"blurry:{blur_var:.1f}")

    # ── Composite quality score ───────────────────────────────────────────────
    quality = (
        blur_score_norm * 0.40
        + min(min_side / config.CROP_MIN_SIDE_PX, 1.0) * 0.20
        + min(crop_record.confidence, 1.0) * 0.20
        + (0.0 if crop_record.clipped else 0.10)
        + (0.10 if aspect <= config.CROP_MAX_ASPECT else 0.0)
    )
    quality = round(min(quality, 1.0), 4)

    return QualityResult(
        crop_id=crop_record.crop_id,
        quality_score=quality,
        accept_for_memory=(len(reasons) == 0),
        blur_score=round(blur_var, 2),
        rejection_reasons=reasons,
    )


def score_all(
    crop_records: List[CropRecord],
    crop_images: Optional[dict] = None,
) -> List[QualityResult]:
    """Score all crops. crop_images: optional {crop_id: ndarray} map."""
    results = []
    for rec in crop_records:
        img = (crop_images or {}).get(rec.crop_id)
        results.append(score(rec, img))
    return results
