import logging
import math
from typing import List, Set, Tuple

import app.config as config
from app.processing.tracked_object import RawDetection, TrackedObject, TrackState

log = logging.getLogger(__name__)


class CentroidIoUTracker:
    """
    Greedy centroid + IoU tracker with candidate / confirmed / lost state machine.

    Matching is two-pass greedy:
        Pass 1 — detections vs active (candidate + confirmed) tracks  [preferred]
        Pass 2 — remaining unmatched detections vs lost tracks         [recovery]

    This means active tracks are never beaten by a lost track for the same
    detection, but a lost track can still recover its original ID if a
    detection has no better active match.

    State machine:
        CANDIDATE → CONFIRMED  after TRACK_CONFIRM_FRAMES matched detections
        CONFIRMED → LOST       after TRACK_LOST_FRAMES consecutive missed frames
        LOST      → CONFIRMED  if re-matched before expiry (recovers original ID)
        LOST      → expired    after TRACK_EXPIRE_FRAMES frames in LOST state

    Known Phase 1 limitation: fast camera panning causes IoU to drop to zero,
    resetting IDs on all objects. This is inherent to image-space tracking, not a bug.
    """

    def __init__(self) -> None:
        self._tracks: List[TrackedObject] = []
        self._next_id: int = 1

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, detections: List[RawDetection], frame_id: int) -> List[TrackedObject]:
        # Snapshot which tracks were already LOST before any mutations this frame.
        # This prevents double-incrementing frames_missed for tracks that transition
        # to LOST during this same update call.
        already_lost_ids: Set[int] = {t.id for t in self._tracks if t.state == TrackState.LOST}

        active = [t for t in self._tracks if t.state != TrackState.LOST]
        lost   = [t for t in self._tracks if t.state == TrackState.LOST]

        # ── Pass 1: match detections against active tracks ────────────────────
        matched_active_ids, unmatched_dets, unmatched_active = self._greedy_match(
            detections, active
        )

        # ── Pass 2: try to recover lost tracks with remaining detections ──────
        matched_lost_ids, still_unmatched_dets, _ = self._greedy_match(
            unmatched_dets, lost
        )

        all_matched_ids = matched_active_ids | matched_lost_ids

        # ── Update unmatched active tracks ────────────────────────────────────
        for track in unmatched_active:
            track.frames_missed += 1
            track.age += 1
            if track.state == TrackState.CANDIDATE:
                self._tracks.remove(track)   # candidates that miss once are dropped immediately
            elif track.frames_missed >= config.TRACK_LOST_FRAMES:
                track.state = TrackState.LOST
                log.debug("track %d → LOST  frames_missed=%d", track.id, track.frames_missed)

        # ── Age lost tracks that were already LOST at frame start ─────────────
        # Tracks that just transitioned to LOST above are NOT in already_lost_ids,
        # so they are skipped here — preventing the double-increment bug.
        for track in self._tracks:
            if (track.state == TrackState.LOST
                    and track.id in already_lost_ids
                    and track.id not in all_matched_ids):
                track.frames_missed += 1
                track.age += 1

        # ── Expire old lost tracks ────────────────────────────────────────────
        expire_threshold = config.TRACK_LOST_FRAMES + config.TRACK_EXPIRE_FRAMES
        self._tracks = [
            t for t in self._tracks
            if not (t.state == TrackState.LOST and t.frames_missed >= expire_threshold)
        ]

        # ── New candidates for still-unmatched detections ─────────────────────
        for det in still_unmatched_dets:
            self._create_track(det, frame_id)

        return self._prioritized_output()

    # ── Matching ──────────────────────────────────────────────────────────────

    def _greedy_match(
        self,
        detections: List[RawDetection],
        tracks: List[TrackedObject],
    ) -> Tuple[Set[int], List[RawDetection], List[TrackedObject]]:
        """
        Greedy assignment: detections sorted by confidence desc, each picks its
        best unmatched track below MAX_MATCH_COST.
        Returns (matched_track_ids, unmatched_detections, unmatched_tracks).
        """
        matched_ids: Set[int] = set()
        unmatched_dets: List[RawDetection] = []

        for det in sorted(detections, key=lambda d: d.confidence, reverse=True):
            best_track, best_cost = None, config.MAX_MATCH_COST
            for track in tracks:
                if track.id in matched_ids:
                    continue
                cost = self._cost(det, track)
                if cost < best_cost:
                    best_cost, best_track = cost, track

            if best_track is not None:
                matched_ids.add(best_track.id)
                self._apply_match(best_track, det)
            else:
                unmatched_dets.append(det)

        unmatched_tracks = [t for t in tracks if t.id not in matched_ids]
        return matched_ids, unmatched_dets, unmatched_tracks

    def _cost(self, det: RawDetection, track: TrackedObject) -> float:
        iou  = self._iou(det, track)
        dist = self._norm_dist(det, track)
        return config.IOU_WEIGHT * (1.0 - iou) + config.DISTANCE_WEIGHT * dist

    def _iou(self, det: RawDetection, track: TrackedObject) -> float:
        ax1, ay1 = det.bbox_x, det.bbox_y
        ax2, ay2 = ax1 + det.bbox_w, ay1 + det.bbox_h
        bx1, by1 = track.bbox_x, track.bbox_y
        bx2, by2 = bx1 + track.bbox_w, by1 + track.bbox_h
        iw = max(0, min(ax2, bx2) - max(ax1, bx1))
        ih = max(0, min(ay2, by2) - max(ay1, by1))
        inter = iw * ih
        if inter == 0:
            return 0.0
        union = det.bbox_w * det.bbox_h + track.bbox_w * track.bbox_h - inter
        return inter / union if union > 0 else 0.0

    def _norm_dist(self, det: RawDetection, track: TrackedObject) -> float:
        dx = det.centroid_x - track.centroid_x
        dy = det.centroid_y - track.centroid_y
        return min(math.sqrt(dx * dx + dy * dy) / config.MAX_CENTROID_DISTANCE, 1.0)

    # ── Track management ──────────────────────────────────────────────────────

    def _apply_match(self, track: TrackedObject, det: RawDetection) -> None:
        track.label        = det.label
        track.confidence   = det.confidence
        track.bbox_x       = det.bbox_x
        track.bbox_y       = det.bbox_y
        track.bbox_w       = det.bbox_w
        track.bbox_h       = det.bbox_h
        track.centroid_x   = det.centroid_x
        track.centroid_y   = det.centroid_y
        track.floor_score  = det.floor_score
        track.frames_missed = 0
        track.frames_seen  += 1
        track.age          += 1

        if track.state == TrackState.LOST:
            track.state = TrackState.CONFIRMED
            log.debug("track %d recovered  LOST→CONFIRMED", track.id)
        elif track.state == TrackState.CANDIDATE and track.frames_seen >= config.TRACK_CONFIRM_FRAMES:
            track.state = TrackState.CONFIRMED
            log.debug("track %d confirmed  frames_seen=%d", track.id, track.frames_seen)

    def _create_track(self, det: RawDetection, frame_id: int) -> None:
        t = TrackedObject(
            id              = self._next_id,
            label           = det.label,
            confidence      = det.confidence,
            bbox_x          = det.bbox_x,
            bbox_y          = det.bbox_y,
            bbox_w          = det.bbox_w,
            bbox_h          = det.bbox_h,
            centroid_x      = det.centroid_x,
            centroid_y      = det.centroid_y,
            contour         = [],
            state           = TrackState.CANDIDATE,
            age             = 1,
            frames_seen     = 1,
            frames_missed   = 0,
            last_seen_frame = frame_id,
            floor_score     = det.floor_score,
        )
        self._next_id += 1
        self._tracks.append(t)
        log.debug("track %d created  label=%s  conf=%.2f", t.id, t.label, t.confidence)

    def _prioritized_output(self) -> List[TrackedObject]:
        """Sort active tracks by priority, cap at MAX_TRACKED_OBJECTS, append lost."""
        def priority(t: TrackedObject) -> float:
            area_score = min(t.bbox_w * t.bbox_h / (config.FRAME_WIDTH * config.FRAME_HEIGHT), 1.0)
            return t.confidence * 0.5 + area_score * 0.3 + t.floor_score * config.FLOOR_WEIGHT

        active = [t for t in self._tracks if t.state != TrackState.LOST]
        lost   = [t for t in self._tracks if t.state == TrackState.LOST]
        return sorted(active, key=priority, reverse=True)[:config.MAX_TRACKED_OBJECTS] + lost
