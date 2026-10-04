"""Hybrid BM25 + dense retrieval with re-ranking."""
import os
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

import numpy as np

from opsmind.retrieval.embedder import embed
from opsmind.retrieval.index import VectorIndex

try:
    from rank_bm25 import BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False

_INDEX_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "output", "opsmind.index"
)

@dataclass
class RankedResult:
    """Single retrieval result with provenance."""
    text: str
    similarity_score: float
    source: str                          # "incident" | "jira_issue" | "jira_comment" | etc.
    source_id: str                       # incident number / jira key / etc.
    metadata: Dict[str, Any] = field(default_factory=dict)
    citation_id: str = ""                # e.g. "INC-0045" or "JIRA-WW-712"


class HybridRetriever:
    """
    Merges BM25 lexical scores with FAISS dense scores.

    alpha=1.0  → pure dense
    alpha=0.0  → pure BM25
    alpha=0.5  → equal blend (default)
    """

    def __init__(self, alpha: float = 0.5):
        self.alpha = alpha
        self._docs: List[Dict[str, Any]] = []
        self._texts: List[str] = []
        self._bm25: Optional[Any] = None
        self._vector_index: Optional[VectorIndex] = None
        self._lock = threading.Lock()
        self._loaded = False

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def build(self, docs: List[Dict[str, Any]]) -> None:
        """Build BM25 + FAISS index from docs list."""
        with self._lock:
            self._docs = docs
            self._texts = [d.get("text", "") for d in docs]
            self._build_bm25()
            self._build_dense()
            self._loaded = True

    def _build_bm25(self) -> None:
        if not _BM25_AVAILABLE:
            return
        tokenized = [t.lower().split() for t in self._texts]
        self._bm25 = BM25Okapi(tokenized)

    def _build_dense(self) -> None:
        try:
            from opsmind.retrieval.index import VectorIndex
            import numpy as np
            vecs = embed_batch(self._texts)
            vi = VectorIndex()
            vi.build(self._docs, vecs)
            self._vector_index = vi
        except Exception:
            self._vector_index = None

    def load_from_disk(self, path: str) -> bool:
        """Load pre-built FAISS index from disk. Returns True on success."""
        try:
            vi = VectorIndex()
            vi.load(path)
            with self._lock:
                self._vector_index = vi
                self._docs = vi._metadata
                self._texts = [d.get("text", "") for d in self._docs]
                self._build_bm25()
                self._loaded = True
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, k: int = 10) -> List[RankedResult]:
        """Return top-k RankedResult objects."""
        if not self._loaded or not self._docs:
            return []

        n = len(self._docs)
        k = min(k, n)

        dense_scores = self._dense_scores(query, n)
        bm25_scores = self._bm25_scores(query, n)

        # Normalize both to [0, 1]
        dense_norm = _minmax(dense_scores)
        bm25_norm = _minmax(bm25_scores)

        combined = self.alpha * dense_norm + (1 - self.alpha) * bm25_norm

        top_indices = np.argsort(combined)[::-1][:k]

        results = []
        for idx in top_indices:
            doc = self._docs[idx]
            score = float(combined[idx])
            results.append(RankedResult(
                text=self._texts[idx],
                similarity_score=score,
                source=doc.get("source", "unknown"),
                source_id=doc.get("id", ""),
                metadata=doc,
                citation_id=_make_citation_id(doc),
            ))
        return results

    def _dense_scores(self, query: str, n: int) -> np.ndarray:
        if self._vector_index is None or self._vector_index.size == 0:
            return np.zeros(n)
        try:
            q_vec = embed(query)
            hits = self._vector_index.search(q_vec, k=n)
            scores = np.zeros(n)
            for score, meta in hits:
                idx = self._docs.index(meta) if meta in self._docs else -1
                if idx >= 0:
                    scores[idx] = score
            return scores
        except Exception:
            return np.zeros(n)

    def _bm25_scores(self, query: str, n: int) -> np.ndarray:
        if not _BM25_AVAILABLE or self._bm25 is None:
            return np.zeros(n)
        try:
            tokens = query.lower().split()
            scores = self._bm25.get_scores(tokens)
            return np.array(scores, dtype=np.float32)
        except Exception:
            return np.zeros(n)


# ------------------------------------------------------------------
# Module-level singleton + convenience helpers
# ------------------------------------------------------------------

_retriever: Optional[HybridRetriever] = None
_retriever_lock = threading.Lock()


def _get_retriever() -> HybridRetriever:
    global _retriever
    with _retriever_lock:
        if _retriever is None:
            _retriever = HybridRetriever()
            index_path = os.path.abspath(_INDEX_PATH)
            if os.path.exists(index_path):
                _retriever.load_from_disk(index_path)
    return _retriever


def search(query: str, k: int = 10, alpha: float = 0.5) -> List[RankedResult]:
    """
    Module-level search. Uses pre-built index if available.
    Returns empty list (not an error) when index not yet built.
    """
    r = _get_retriever()
    r.alpha = alpha
    return r.search(query, k=k)


def build_index(docs: List[Dict[str, Any]]) -> None:
    """Build in-memory index from docs. Called by scripts/build_index.py."""
    global _retriever
    with _retriever_lock:
        _retriever = HybridRetriever()
        _retriever.build(docs)


def embed_batch(texts: List[str]) -> np.ndarray:
    """Batch embed helper used by build_index."""
    from opsmind.retrieval.embedder import embed_texts
    return embed_texts(texts)


def _minmax(arr: np.ndarray) -> np.ndarray:
    lo, hi = arr.min(), arr.max()
    if hi == lo:
        return np.zeros_like(arr)
    return (arr - lo) / (hi - lo)


def _make_citation_id(doc: Dict[str, Any]) -> str:
    source = doc.get("source", "")
    doc_id = str(doc.get("id", ""))
    if source == "incident":
        return f"INC-{doc_id}"
    if "jira" in source:
        return f"JIRA-{doc_id}"
    return doc_id
