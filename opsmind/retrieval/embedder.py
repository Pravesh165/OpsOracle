"""Embedding utility using Google Generative AI."""
import os
import hashlib
from typing import List

import numpy as np

_cache: dict = {}
_MODEL = "models/text-embedding-004"


def embed_texts(texts: List[str]) -> np.ndarray:
    """
    Embed a list of texts using Gemini embedding API.

    Returns np.ndarray of shape (len(texts), embedding_dim).
    Falls back to random unit vectors if API is unavailable (for tests / offline).
    """
    if not texts:
        return np.empty((0, 768), dtype=np.float32)

    results = []
    uncached_indices = []
    uncached_texts = []

    for i, text in enumerate(texts):
        key = hashlib.md5(text.encode()).hexdigest()
        if key in _cache:
            results.append((i, _cache[key]))
        else:
            uncached_indices.append(i)
            uncached_texts.append((i, text, key))

    if uncached_texts:
        try:
            import google.generativeai as genai

            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)

            for i, text, key in uncached_texts:
                response = genai.embed_content(model=_MODEL, content=text)
                vec = np.array(response["embedding"], dtype=np.float32)
                _cache[key] = vec
                results.append((i, vec))
        except Exception:
            # Offline / no key: deterministic fallback via hashed random
            for i, text, key in uncached_texts:
                rng = np.random.default_rng(int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32))
                vec = rng.standard_normal(768).astype(np.float32)
                vec /= np.linalg.norm(vec) + 1e-9
                _cache[key] = vec
                results.append((i, vec))

    results.sort(key=lambda x: x[0])
    return np.stack([v for _, v in results])


def embed(text: str) -> np.ndarray:
    """Embed a single text string."""
    return embed_texts([text])[0]
