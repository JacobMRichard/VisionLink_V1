"""
NotificationManager — sends Discord webhook alerts when tracked objects are detected.

- Rate-limited per label via cooldown (default 30 s).
- Only fires on CONFIRMED tracks (candidate/lost states are ignored).
- Async-native: runs directly in the event loop, no extra threads.
- Reuses a single aiohttp.ClientSession for efficiency.
"""
import logging
import time
from typing import Dict, List, Optional

import aiohttp

from app.networking.models import DetectedObject
from app.runtime_config import RuntimeConfig

log = logging.getLogger(__name__)

# Emoji icons per YOLO class label
_ICONS: Dict[str, str] = {
    "person":       "🧍",
    "dog":          "🐕",
    "cat":          "🐈",
    "bird":         "🐦",
    "horse":        "🐎",
    "cow":          "🐄",
    "elephant":     "🐘",
    "bear":         "🐻",
    "zebra":        "🦓",
    "giraffe":      "🦒",
    "sheep":        "🐑",
    "car":          "🚗",
    "truck":        "🚛",
    "bus":          "🚌",
    "bicycle":      "🚲",
    "motorcycle":   "🏍️",
    "airplane":     "✈️",
    "train":        "🚆",
    "boat":         "⛵",
    "tv":           "📺",
    "laptop":       "💻",
    "cell phone":   "📱",
    "bottle":       "🍾",
    "cup":          "☕",
    "chair":        "🪑",
    "couch":        "🛋️",
    "bed":          "🛏️",
    "dining table": "🍽️",
    "backpack":     "🎒",
    "umbrella":     "☂️",
    "sports ball":  "⚽",
    "pizza":        "🍕",
    "donut":        "🍩",
    "cake":         "🎂",
}


class NotificationManager:

    def __init__(self, webhook_url: str, session: aiohttp.ClientSession) -> None:
        self._webhook_url = webhook_url
        self._session = session
        # label → monotonic timestamp of last notification sent
        self._last_sent: Dict[str, float] = {}

    async def check_and_notify(self, objects: List[DetectedObject]) -> None:
        """Call after every processed frame. Fires Discord alerts as needed."""
        settings = RuntimeConfig.get_notification_settings()
        if not settings["enabled"] or not self._webhook_url:
            return

        confirmed = [o for o in objects if o.state == "confirmed"]
        if not confirmed:
            return

        # Group confirmed detections by label
        by_label: Dict[str, List[DetectedObject]] = {}
        for obj in confirmed:
            by_label.setdefault(obj.label, []).append(obj)

        now = time.monotonic()
        cooldown = settings["cooldown_s"]
        min_count = settings["min_count"]

        for label, group in by_label.items():
            if len(group) < min_count:
                continue
            if now - self._last_sent.get(label, 0.0) < cooldown:
                continue
            self._last_sent[label] = now
            await self._post(label, group)

    async def _post(self, label: str, objects: List[DetectedObject]) -> None:
        count = len(objects)
        conf = max(o.confidence for o in objects)
        icon = _ICONS.get(label, "🔍")
        count_str = f"×{count} " if count > 1 else ""
        message = f"{icon} **{label.upper()}** detected  {count_str}({conf:.0%} confidence)"

        try:
            async with self._session.post(
                self._webhook_url,
                json={"content": message, "username": "VisionLink"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status in (200, 204):
                    log.info("Discord notified: %s", message)
                else:
                    body = await resp.text()
                    log.warning("Discord webhook %d: %s", resp.status, body[:120])
        except Exception as exc:
            log.warning("Discord notify failed: %s", exc)
