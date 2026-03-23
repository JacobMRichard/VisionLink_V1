from dataclasses import dataclass, field
from enum import Enum
from typing import List


class TrackState(Enum):
    CANDIDATE = "candidate"   # seen < CONFIRM_FRAMES, tentative — not yet shown
    CONFIRMED = "confirmed"   # stable, actively rendered on phone
    LOST      = "lost"        # missed recently, held briefly before expiry


@dataclass
class RawDetection:
    """Output of the detector, input to the tracker. No tracker state."""
    label: str
    confidence: float
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    centroid_x: int
    centroid_y: int
    floor_score: float   # 0.0 (top of frame) → 1.0 (bottom of frame)


@dataclass
class TrackedObject:
    """
    Full internal tracker state. This is the contract between tracker and pipeline.
    Never sent directly over the wire — pipeline converts to DetectedObject first.
    """
    id: int
    label: str
    confidence: float
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    centroid_x: int
    centroid_y: int
    contour: List[List[float]]   # normalized [[x,y],...] 0.0-1.0; empty in Phase 1
    state: TrackState
    age: int               # total frames this track has been alive
    frames_seen: int       # frames successfully matched to a detection
    frames_missed: int     # consecutive missed frames — resets on match
    last_seen_frame: int   # frame_id of last successful match
    floor_score: float     # soft floor preference 0.0-1.0
