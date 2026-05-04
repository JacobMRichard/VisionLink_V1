"""
RuntimeConfig — thread-safe, live-adjustable pipeline settings.

All pipeline code reads from this instead of config.py constants directly.
Updated via POST /control without restarting the server.
MCP tools call /control to change settings from Claude chat in real time.
"""
import threading
from typing import FrozenSet, Optional

import app.config as config


class RuntimeConfig:

    _lock = threading.Lock()

    # ── Detection ──────────────────────────────────────────────────────────────
    # None = all YOLO classes pass through. frozenset = only these labels.
    _class_filter: Optional[FrozenSet[str]] = None
    _confidence_threshold: float = config.CONFIDENCE_THRESHOLD
    _max_tracked_objects: int = config.MAX_TRACKED_OBJECTS

    # ── Notifications ──────────────────────────────────────────────────────────
    _notifications_enabled: bool = False   # off by default; enable via set_notifications(True)
    _notification_cooldown_s: float = config.NOTIFICATION_COOLDOWN_S
    _notification_min_count: int = 1   # min confirmed objects of a class to trigger

    # ── Class filter ───────────────────────────────────────────────────────────
    @classmethod
    def set_class_filter(cls, classes: Optional[list]) -> None:
        with cls._lock:
            cls._class_filter = frozenset(c.lower() for c in classes) if classes else None

    @classmethod
    def get_class_filter(cls) -> Optional[FrozenSet[str]]:
        with cls._lock:
            return cls._class_filter

    # ── Confidence ─────────────────────────────────────────────────────────────
    @classmethod
    def set_confidence(cls, threshold: float) -> None:
        with cls._lock:
            cls._confidence_threshold = max(0.05, min(0.99, threshold))

    @classmethod
    def get_confidence(cls) -> float:
        with cls._lock:
            return cls._confidence_threshold

    # ── Max objects ────────────────────────────────────────────────────────────
    @classmethod
    def set_max_objects(cls, n: int) -> None:
        with cls._lock:
            cls._max_tracked_objects = max(1, min(50, n))

    @classmethod
    def get_max_objects(cls) -> int:
        with cls._lock:
            return cls._max_tracked_objects

    # ── Notifications ──────────────────────────────────────────────────────────
    @classmethod
    def set_notifications(
        cls,
        enabled: bool,
        cooldown_s: Optional[float] = None,
        min_count: Optional[int] = None,
    ) -> None:
        with cls._lock:
            cls._notifications_enabled = enabled
            if cooldown_s is not None:
                cls._notification_cooldown_s = max(1.0, cooldown_s)
            if min_count is not None:
                cls._notification_min_count = max(1, min_count)

    @classmethod
    def get_notification_settings(cls) -> dict:
        with cls._lock:
            return {
                "enabled":    cls._notifications_enabled,
                "cooldown_s": cls._notification_cooldown_s,
                "min_count":  cls._notification_min_count,
            }

    # ── Snapshot ───────────────────────────────────────────────────────────────
    @classmethod
    def to_dict(cls) -> dict:
        with cls._lock:
            return {
                "class_filter":            sorted(cls._class_filter) if cls._class_filter else None,
                "confidence_threshold":    round(cls._confidence_threshold, 3),
                "max_tracked_objects":     cls._max_tracked_objects,
                "notifications_enabled":   cls._notifications_enabled,
                "notification_cooldown_s": cls._notification_cooldown_s,
                "notification_min_count":  cls._notification_min_count,
            }
