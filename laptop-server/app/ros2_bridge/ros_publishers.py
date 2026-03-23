"""
ROS 2 bridge — Version 1 placeholder.
Wire in actual rclpy publishers here when ROS 2 integration begins (V2+).
"""
import logging
from app.networking.models import MetadataResponse

log = logging.getLogger(__name__)


class RosPublishers:
    def publish(self, metadata: MetadataResponse) -> None:
        # TODO (V2): publish to /vision/objects and /vision/debug_image
        log.debug("ROS 2 not yet integrated — skipping publish for frame %d", metadata.frame_id)
