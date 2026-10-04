"""FAISS vector index wrapper."""
import os
import pickle
from typing import List, Tuple, Dict, Any

import numpy as np

try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False


class VectorIndex:
    """Thin FAISS IndexFlatIP wrapper with metadata storage."""

    def __init__(self):
        self._index = None
        self._metadata: List[Dict[str, Any]] = []
        self._dim: int = 0

    def build(self, docs: List[Dict[str, Any]], vectors: np.ndarray) -> None:
        """
        Build index from pre-computed vectors.

        Args:
            docs: list of metadata dicts (one per vector row)
            vectors: float32 array of shape (n, dim)
        """
        if not _FAISS_AVAILABLE:
            raise ImportError("faiss-cpu is required. Run: pip install faiss-cpu")
        if len(docs) != vectors.shape[0]:
            raise ValueError("docs and vectors must have same length")

        self._dim = vectors.shape[1]
        # Normalize for cosine similarity via inner product
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / (norms + 1e-9)

        self._index = faiss.IndexFlatIP(self._dim)
        self._index.add(vectors.astype(np.float32))
        self._metadata = docs

    def search(self, query_vec: np.ndarray, k: int = 10) -> List[Tuple[float, Dict[str, Any]]]:
        """
        Search index.

        Returns list of (score, metadata) tuples sorted by score descending.
        """
        if self._index is None or self._index.ntotal == 0:
            return []
        k = min(k, self._index.ntotal)
        vec = query_vec.astype(np.float32).reshape(1, -1)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        scores, indices = self._index.search(vec, k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0:
                results.append((float(score), self._metadata[idx]))
        return results

    def save(self, path: str) -> None:
        """Save index and metadata to disk."""
        if not _FAISS_AVAILABLE:
            raise ImportError("faiss-cpu required")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        faiss.write_index(self._index, path)
        with open(path + ".meta", "wb") as f:
            pickle.dump({"metadata": self._metadata, "dim": self._dim}, f)

    def load(self, path: str) -> None:
        """Load index and metadata from disk."""
        if not _FAISS_AVAILABLE:
            raise ImportError("faiss-cpu required")
        self._index = faiss.read_index(path)
        with open(path + ".meta", "rb") as f:
            data = pickle.load(f)
        self._metadata = data["metadata"]
        self._dim = data["dim"]

    @property
    def size(self) -> int:
        return self._index.ntotal if self._index else 0
