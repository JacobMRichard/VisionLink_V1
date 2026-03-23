"""
IdentityMatcher — multi-cue matching between a new crop descriptor and object memory.

Decision thresholds (from config):
  composite >= MATCH_KNOWN_THRESHOLD     → known_match
  composite >= MATCH_AMBIGUOUS_THRESHOLD → ambiguous_candidate
  otherwise                              → new_object

Wrong merge is worse than a delayed merge: when uncertain, always prefer
ambiguous_candidate or new_object over forcing a known_match.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

import app.config as config
from app.memory.descriptor_extractor import DescriptorRecord
from app.memory.embedding_index import EmbeddingIndex
from app.memory.object_memory_store import ObjectMemoryStore

log = logging.getLogger(__name__)


@dataclass
class CandidateScore:
    object_uid: str
    embedding_score: float
    color_score: float
    label_score: float
    composite_score: float


@dataclass
class MatchResult:
    crop_id: str
    decision: str                           # known_match | ambiguous_candidate | new_object
    matched_uid: Optional[str] = None
    composite_score: float = 0.0
    candidates: List[CandidateScore] = field(default_factory=list)


class IdentityMatcher:
    def __init__(self, store: ObjectMemoryStore, index: EmbeddingIndex) -> None:
        self._store = store
        self._index = index

    def match(self, descriptor: DescriptorRecord) -> MatchResult:
        raw_candidates = self._index.search(
            descriptor.embedding, k=config.TOP_K_CANDIDATES
        )
        if not raw_candidates:
            return MatchResult(crop_id=descriptor.crop_id, decision="new_object")

        scored: List[CandidateScore] = []
        for uid, emb_score in raw_candidates:
            rec = self._store.load(uid)
            if rec is None:
                continue
            color_score = _color_similarity(descriptor.color_hist, rec.color_summary)
            label_score = 1.0 if descriptor.label in rec.detector_labels_seen else 0.0
            composite   = (
                config.EMBEDDING_WEIGHT * emb_score
                + config.COLOR_WEIGHT   * color_score
                + config.LABEL_WEIGHT   * label_score
            )
            scored.append(CandidateScore(
                object_uid=uid,
                embedding_score=round(emb_score, 4),
                color_score=round(color_score, 4),
                label_score=label_score,
                composite_score=round(composite, 4),
            ))

        scored.sort(key=lambda c: c.composite_score, reverse=True)
        best = scored[0] if scored else None

        if best is None or best.composite_score < config.MATCH_AMBIGUOUS_THRESHOLD:
            decision    = "new_object"
            matched_uid = None
            top_score   = 0.0
        elif best.composite_score >= config.MATCH_KNOWN_THRESHOLD:
            decision    = "known_match"
            matched_uid = best.object_uid
            top_score   = best.composite_score
        else:
            decision    = "ambiguous_candidate"
            matched_uid = best.object_uid
            top_score   = best.composite_score

        log.debug(
            "identity_matcher: %s → %s  score=%.3f  uid=%s",
            descriptor.crop_id, decision, top_score, matched_uid,
        )
        return MatchResult(
            crop_id=descriptor.crop_id,
            decision=decision,
            matched_uid=matched_uid,
            composite_score=top_score,
            candidates=scored,
        )


def _color_similarity(hist_a: List[float], hist_b: List[float]) -> float:
    """Bhattacharyya coefficient: 0 = no overlap, 1 = identical distributions."""
    if not hist_a or not hist_b or len(hist_a) != len(hist_b):
        return 0.0
    a = np.array(hist_a, dtype=np.float32)
    b = np.array(hist_b, dtype=np.float32)
    return float(np.sum(np.sqrt(a * b)))
