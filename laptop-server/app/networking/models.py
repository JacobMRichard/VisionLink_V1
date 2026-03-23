from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class FrameMetadata:
    frame_id: int
    timestamp_ms: int
    width: int
    height: int
    rotation_degrees: int = 0


@dataclass
class BBox:
    x: int
    y: int
    w: int
    h: int


@dataclass
class DetectedObject:
    """
    Wire format — the contract between laptop tracker and phone renderer.
    Converted from TrackedObject in the pipeline before going into MetadataResponse.
    """
    id: int
    label: str
    confidence: float
    bbox: BBox
    centroid: Tuple[int, int]
    contour: List[List[float]] = field(default_factory=list)  # normalized [[x,y],...] 0.0-1.0
    state: str = "confirmed"                                   # "candidate" | "confirmed" | "lost"


@dataclass
class MetadataResponse:
    frame_id: int
    fps: float
    latency_ms: float
    source_width: int = 0
    source_height: int = 0
    objects: List[DetectedObject] = field(default_factory=list)
    mode: str = "real"   # "fake" or "real"

    def to_dict(self) -> dict:
        return {
            "frame_id":      self.frame_id,
            "fps":           self.fps,
            "latency_ms":    self.latency_ms,
            "source_width":  self.source_width,
            "source_height": self.source_height,
            "mode":          self.mode,
            "objects": [
                {
                    "id":         obj.id,
                    "label":      obj.label,
                    "confidence": round(obj.confidence, 3),
                    "bbox":       [obj.bbox.x, obj.bbox.y, obj.bbox.w, obj.bbox.h],
                    "centroid":   list(obj.centroid),
                    "contour":    obj.contour,
                    "state":      obj.state,
                }
                for obj in self.objects
            ],
        }
