"""
MemoryUpdater — applies a MatchResult to ObjectMemoryStore and EmbeddingIndex.

  known_match        → update object record (times_seen, labels, color, exemplar)
  new_object         → create provisional object, add embedding to index
  ambiguous_candidate → log only; do not merge
"""
import logging
import time
from typing import List, Optional

import app.config as config
from app.memory.crop_extractor import CropRecord
from app.memory.crop_quality import QualityResult
from app.memory.descriptor_extractor import DescriptorRecord
from app.memory.embedding_index import EmbeddingIndex
from app.memory.identity_matcher import MatchResult
from app.memory.object_memory_store import ObjectMemoryStore

log = logging.getLogger(__name__)


class MemoryUpdater:
    def __init__(self, store: ObjectMemoryStore, index: EmbeddingIndex) -> None:
        self._store = store
        self._index = index

    def apply(
        self,
        match: MatchResult,
        descriptor: DescriptorRecord,
        crop_record: CropRecord,
        quality: QualityResult,
    ) -> Optional[str]:
        """
        Apply a match result to memory.
        Returns the object_uid that was updated/created, or None for ambiguous.
        """
        if match.decision == "known_match":
            return self._update_known(match.matched_uid, descriptor, crop_record, quality)
        elif match.decision == "new_object":
            return self._create_new(descriptor, crop_record, quality)
        else:  # ambiguous_candidate
            log.info(
                "memory_updater: ambiguous  crop=%s  best_uid=%s  score=%.3f — no merge",
                match.crop_id, match.matched_uid, match.composite_score,
            )
            return None

    # ── Private ───────────────────────────────────────────────────────────────

    def _update_known(
        self,
        uid: str,
        descriptor: DescriptorRecord,
        crop_record: CropRecord,
        quality: QualityResult,
    ) -> str:
        rec = self._store.load(uid)
        if rec is None:
            log.warning("memory_updater: uid %s not found — creating new instead", uid)
            return self._create_new(descriptor, crop_record, quality)

        now = int(time.time() * 1000)
        rec.times_seen  += 1
        rec.last_seen_ms = now
        if descriptor.label not in rec.detector_labels_seen:
            rec.detector_labels_seen.append(descriptor.label)
        if descriptor.color_hist:
            rec.color_summary = descriptor.color_hist  # rolling update with latest

        if rec.times_seen >= config.STABLE_SEEN_THRESHOLD and rec.status == "provisional":
            rec.status = "stable"
            log.info("object_memory: %s promoted to stable  times_seen=%d", uid, rec.times_seen)

        self._store.save(rec)
        if quality.accept_for_memory:
            self._store.add_exemplar(uid, crop_record.image_path, quality.quality_score)
        self._store.add_evidence(uid, _evidence_dict(descriptor, crop_record, quality, uid))
        log.info("memory_updater: updated %s  times_seen=%d", uid, rec.times_seen)
        return uid

    def _create_new(
        self,
        descriptor: DescriptorRecord,
        crop_record: CropRecord,
        quality: QualityResult,
    ) -> str:
        rec = self._store.create(
            label=descriptor.label,
            confidence=descriptor.confidence,
            color_summary=descriptor.color_hist,
        )
        self._index.add(descriptor.embedding, rec.object_uid)
        if quality.accept_for_memory:
            self._store.add_exemplar(rec.object_uid, crop_record.image_path, quality.quality_score)
        self._store.add_evidence(
            rec.object_uid,
            _evidence_dict(descriptor, crop_record, quality, rec.object_uid),
        )
        log.info("memory_updater: created %s  label=%s", rec.object_uid, descriptor.label)
        return rec.object_uid


def _evidence_dict(
    descriptor: DescriptorRecord,
    crop_record: CropRecord,
    quality: QualityResult,
    uid: str,
) -> dict:
    return {
        "crop_id":           descriptor.crop_id,
        "snapshot_id":       descriptor.snapshot_id,
        "object_uid":        uid,
        "image_path":        crop_record.image_path,
        "label":             descriptor.label,
        "confidence":        descriptor.confidence,
        "quality_score":     quality.quality_score,
        "blur_score":        quality.blur_score,
        "accept":            quality.accept_for_memory,
        "rejection_reasons": quality.rejection_reasons,
        "color_hist":        descriptor.color_hist,
        "shape":             descriptor.shape,
        "timestamp_ms":      int(time.time() * 1000),
    }
