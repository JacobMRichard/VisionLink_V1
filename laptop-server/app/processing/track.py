from typing import List
from app.networking.models import DetectedObject, BBox


class SimpleTracker:
    """
    V1 pass-through tracker.  Assigns a stable ID of 1 to the single detected
    object.  Replace with a proper centroid tracker in V2.
    """

    def update(self, objects: List[DetectedObject]) -> List[DetectedObject]:
        result = []
        for i, obj in enumerate(objects):
            result.append(
                DetectedObject(
                    id=i + 1,
                    label=obj.label,
                    confidence=obj.confidence,
                    bbox=BBox(obj.bbox.x, obj.bbox.y, obj.bbox.w, obj.bbox.h),
                    centroid=obj.centroid,
                    contour=obj.contour,
                )
            )
        return result
