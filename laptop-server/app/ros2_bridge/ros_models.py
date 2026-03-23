"""
ROS 2 message type stubs — Version 1 placeholder.
Replace with real ROS 2 message types (sensor_msgs, geometry_msgs, etc.) in V2.
"""
from dataclasses import dataclass
from typing import List


@dataclass
class RosDetectedObject:
    id: int
    label: str
    confidence: float
    bbox_xywh: List[int]    # [x, y, w, h] in pixel coords
    centroid_xy: List[int]  # [cx, cy] in pixel coords
