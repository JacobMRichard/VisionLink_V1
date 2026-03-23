"""
EmbeddingIndex — FAISS-backed cosine similarity index for object embeddings.

Because embeddings are L2-normalised, IndexFlatIP (inner product) is
equivalent to cosine similarity.

Layout:
  memory_data/indexes/embedding_index.faiss
  memory_data/indexes/embedding_map.json   →  ordered list of object_uid per row
"""
import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

import app.config as config

log = logging.getLogger(__name__)


def _faiss():
    """Lazy import so the server starts even if faiss is not yet installed."""
    import faiss as _f
    return _f


class EmbeddingIndex:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        idx_dir = Path(base_dir or config.MEMORY_DATA_DIR) / "indexes"
        idx_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = idx_dir / "embedding_index.faiss"
        self._map_path   = idx_dir / "embedding_map.json"
        self._uid_map: List[str] = []
        self._index = None
        self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def add(self, embedding: List[float], object_uid: str) -> None:
        f   = _faiss()
        vec = np.array(embedding, dtype=np.float32).reshape(1, -1)
        if self._index is None:
            self._index = f.IndexFlatIP(len(embedding))
        self._index.add(vec)
        self._uid_map.append(object_uid)
        self.save()
        log.debug("embedding_index: added uid=%s  total=%d", object_uid, self._index.ntotal)

    def search(self, embedding: List[float], k: int = 5) -> List[Tuple[str, float]]:
        """Return up to k (object_uid, cosine_score) pairs, highest score first."""
        if self._index is None or self._index.ntotal == 0:
            return []
        vec = np.array(embedding, dtype=np.float32).reshape(1, -1)
        k   = min(k, self._index.ntotal)
        scores, indices = self._index.search(vec, k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            results.append((self._uid_map[int(idx)], float(score)))
        return results

    def save(self) -> None:
        if self._index is not None:
            _faiss().write_index(self._index, str(self._index_path))
        self._map_path.write_text(json.dumps(self._uid_map))

    @property
    def size(self) -> int:
        return self._index.ntotal if self._index else 0

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        try:
            f = _faiss()
            self._index  = f.read_index(str(self._index_path))
            self._uid_map = (
                json.loads(self._map_path.read_text()) if self._map_path.exists() else []
            )
            log.info("embedding_index: loaded  entries=%d", self._index.ntotal)
        except Exception as exc:
            log.warning("embedding_index: load failed: %s", exc)
