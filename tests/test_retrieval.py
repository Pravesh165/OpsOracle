"""Tests for opsmind/retrieval — Phase 1."""
import importlib
import os
import sys
import tempfile

import numpy as np
import pytest

# Import retrieval submodules directly to avoid triggering opsmind/__init__.py
# which requires google-adk (not installed in test env).
_ROOT = os.path.dirname(os.path.dirname(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Stub out opsmind top-level so sub-imports don't pull in ADK
import types as _types
if "opsmind" not in sys.modules:
    _pkg = _types.ModuleType("opsmind")
    _pkg.__path__ = [os.path.join(_ROOT, "opsmind")]
    _pkg.__package__ = "opsmind"
    sys.modules["opsmind"] = _pkg

from opsmind.retrieval.chunker import chunk_document  # noqa: E402
from opsmind.retrieval.embedder import embed_texts, embed  # noqa: E402
from opsmind.retrieval.index import VectorIndex  # noqa: E402
from opsmind.retrieval.hybrid import (  # noqa: E402
    HybridRetriever,
    RankedResult,
    _minmax,
    _make_citation_id,
    search,
    build_index,
)


# ---------------------------------------------------------------------------
# chunker
# ---------------------------------------------------------------------------

def test_chunk_document_short_text():
    chunks = chunk_document("hello world", max_tokens=512)
    assert chunks == ["hello world"]


def test_chunk_document_splits_long_text():
    words = ["word"] * 600
    text = " ".join(words)
    chunks = chunk_document(text, max_tokens=512)
    assert len(chunks) == 2
    assert all(len(c.split()) <= 512 for c in chunks)


def test_chunk_document_empty():
    assert chunk_document("") == []
    assert chunk_document("   ") == []


# ---------------------------------------------------------------------------
# embedder
# ---------------------------------------------------------------------------

def test_embedder_returns_correct_shape():
    texts = ["redis out of memory", "nginx 502 bad gateway"]
    vecs = embed_texts(texts)
    assert vecs.shape == (2, 768)
    assert vecs.dtype == np.float32


def test_embedder_single():
    vec = embed("kubernetes pod crash")
    assert vec.shape == (768,)


def test_embedder_caches():
    """Second call for same text must not change the vector."""
    text = "cache test string"
    v1 = embed(text)
    v2 = embed(text)
    np.testing.assert_array_equal(v1, v2)


def test_embedder_empty_list():
    result = embed_texts([])
    assert result.shape == (0, 768)


# ---------------------------------------------------------------------------
# VectorIndex
# ---------------------------------------------------------------------------

def _make_index(n=5):
    docs = [{"id": str(i), "source": "incident", "text": f"doc {i}"} for i in range(n)]
    vecs = embed_texts([d["text"] for d in docs])
    vi = VectorIndex()
    vi.build(docs, vecs)
    return vi, docs


def test_index_build_and_query():
    vi, docs = _make_index(5)
    assert vi.size == 5
    q_vec = embed("doc 2")
    results = vi.search(q_vec, k=3)
    assert len(results) == 3
    scores = [s for s, _ in results]
    assert scores == sorted(scores, reverse=True)


def test_index_save_load_roundtrip():
    vi, docs = _make_index(4)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.index")
        vi.save(path)
        vi2 = VectorIndex()
        vi2.load(path)
        assert vi2.size == vi.size
        q_vec = embed("doc 1")
        r1 = vi.search(q_vec, k=2)
        r2 = vi2.search(q_vec, k=2)
        assert len(r1) == len(r2)


# ---------------------------------------------------------------------------
# hybrid
# ---------------------------------------------------------------------------

def _sample_docs():
    return [
        {"id": "INC001", "source": "incident", "text": "redis out of memory OOM killer", "category": "database"},
        {"id": "INC002", "source": "incident", "text": "nginx 502 bad gateway upstream timeout", "category": "network"},
        {"id": "INC003", "source": "incident", "text": "kubernetes pod crash loop back off", "category": "container"},
        {"id": "JIRA-001", "source": "jira_issue", "text": "redis memory leak configuration fix", "summary": "Redis OOM"},
        {"id": "JIRA-002", "source": "jira_issue", "text": "nginx proxy timeout configuration", "summary": "Nginx 502"},
    ]


def test_hybrid_search_returns_ranked_results():
    r = HybridRetriever()
    r.build(_sample_docs())
    results = r.search("redis memory", k=3)
    assert len(results) == 3
    assert all(isinstance(res, RankedResult) for res in results)
    scores = [res.similarity_score for res in results]
    assert scores == sorted(scores, reverse=True)


def test_known_incident_top_result():
    """'redis out of memory' should surface a redis-related record first."""
    r = HybridRetriever()
    r.build(_sample_docs())
    results = r.search("redis out of memory", k=5)
    assert results, "Expected at least one result"
    top = results[0]
    assert "redis" in top.text.lower() or "redis" in top.source_id.lower()


def test_hybrid_search_returns_ranked_results_module_level():
    """Module-level search() falls back gracefully when no index on disk."""
    # No index built → returns empty list (not an error)
    results = search("some query", k=5)
    assert isinstance(results, list)


def test_hybrid_alpha_pure_bm25():
    r = HybridRetriever(alpha=0.0)
    r.build(_sample_docs())
    results = r.search("nginx 502", k=2)
    assert len(results) == 2


def test_hybrid_alpha_pure_dense():
    r = HybridRetriever(alpha=1.0)
    r.build(_sample_docs())
    results = r.search("nginx 502", k=2)
    assert len(results) == 2


def test_ranked_result_citation_id():
    r = HybridRetriever()
    r.build(_sample_docs())
    results = r.search("redis", k=5)
    for res in results:
        assert res.citation_id != ""


def test_minmax_uniform():
    arr = np.array([3.0, 3.0, 3.0])
    result = _minmax(arr)
    np.testing.assert_array_equal(result, np.zeros(3))


def test_minmax_range():
    arr = np.array([0.0, 0.5, 1.0])
    result = _minmax(arr)
    assert result[0] == pytest.approx(0.0)
    assert result[-1] == pytest.approx(1.0)


def test_make_citation_id_incident():
    assert _make_citation_id({"source": "incident", "id": "0045"}) == "INC-0045"


def test_make_citation_id_jira():
    assert _make_citation_id({"source": "jira_issue", "id": "WW-712"}) == "JIRA-WW-712"


def test_build_index_module_level():
    """build_index() populates the module-level retriever."""
    docs = _sample_docs()
    build_index(docs)
    results = search("kubernetes pod crash", k=3)
    assert len(results) > 0
    assert all(isinstance(r, RankedResult) for r in results)
