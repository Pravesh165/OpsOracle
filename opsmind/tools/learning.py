"""
Knowledge learning loop for OpsMind — Phase 6.

ingest_postmortem()        — parse saved markdown → chunk → embed → upsert into retriever
mark_resolution_helpful()  — record helpful/unhelpful weight for a resolution
get_knowledge_stats()      — index size, source breakdown, top-weighted incidents
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from opsmind.config import OUTPUT_DIR, logger

_WEIGHTS_FILE = os.path.join(OUTPUT_DIR, "resolution_weights.json")


# ---------------------------------------------------------------------------
# Markdown section parser
# ---------------------------------------------------------------------------

def _parse_markdown_sections(text: str) -> List[Dict[str, str]]:
    """
    Split a postmortem markdown into named sections.

    Returns list of {heading, content} dicts.
    Falls back to a single section when no headings are found.
    """
    import re
    sections: List[Dict[str, str]] = []
    # Match ## or # headings
    parts = re.split(r"(?m)^(#{1,3} .+)$", text)
    if len(parts) <= 1:
        return [{"heading": "full_document", "content": text.strip()}]

    # parts alternates: [pre-heading text, heading, content, heading, content, ...]
    # Skip empty pre-heading text
    i = 0
    if parts[0].strip():
        sections.append({"heading": "preamble", "content": parts[0].strip()})
    i = 1
    while i < len(parts) - 1:
        heading = parts[i].lstrip("#").strip()
        content = parts[i + 1].strip()
        if content:
            sections.append({"heading": heading, "content": content})
        i += 2

    return sections if sections else [{"heading": "full_document", "content": text.strip()}]


# ---------------------------------------------------------------------------
# Weights file helpers
# ---------------------------------------------------------------------------

def _load_weights() -> Dict[str, Any]:
    try:
        if os.path.exists(_WEIGHTS_FILE):
            with open(_WEIGHTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_weights(weights: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_WEIGHTS_FILE), exist_ok=True)
    with open(_WEIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(weights, f, indent=2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_postmortem(
    filepath: str,
    incident_id: str,
) -> Dict[str, Any]:
    """
    Parse a saved postmortem markdown file, chunk it, embed the chunks,
    and upsert them into the module-level HybridRetriever singleton.

    Each chunk is stored with metadata:
        {source: "postmortem", incident_id, chunk_index, filepath, heading}

    Args:
        filepath:    Absolute or relative path to the saved .md file.
        incident_id: Incident identifier for metadata tagging.

    Returns:
        {status, incident_id, chunks_added, filepath}
    """
    try:
        from opsmind.retrieval.chunker import chunk_document
        from opsmind.retrieval.hybrid import _get_retriever, embed_batch

        path = Path(filepath)
        if not path.exists():
            return {
                "status": "error",
                "incident_id": incident_id,
                "message": f"File not found: {filepath}",
            }

        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return {
                "status": "error",
                "incident_id": incident_id,
                "message": "Postmortem file is empty.",
            }

        # Parse into sections, then chunk each section
        sections = _parse_markdown_sections(text)
        new_docs: List[Dict[str, Any]] = []
        chunk_idx = 0
        for section in sections:
            chunks = chunk_document(section["content"], max_tokens=256)
            for chunk_text in chunks:
                if not chunk_text.strip():
                    continue
                new_docs.append({
                    "text": chunk_text,
                    "source": "postmortem",
                    "id": f"{incident_id}-chunk-{chunk_idx}",
                    "incident_id": incident_id,
                    "chunk_index": chunk_idx,
                    "heading": section["heading"],
                    "filepath": str(filepath),
                    "ingested_at": datetime.now().isoformat(),
                })
                chunk_idx += 1

        if not new_docs:
            return {
                "status": "error",
                "incident_id": incident_id,
                "message": "No chunks produced from postmortem content.",
            }

        # Upsert into the singleton retriever
        retriever = _get_retriever()
        existing_docs = list(retriever._docs)  # copy current corpus
        all_docs = existing_docs + new_docs

        # Rebuild index with combined corpus
        retriever.build(all_docs)

        logger.info(
            "Ingested postmortem %s: %d chunks added (total corpus: %d)",
            incident_id, len(new_docs), len(all_docs),
        )
        return {
            "status": "success",
            "incident_id": incident_id,
            "chunks_added": len(new_docs),
            "total_documents": len(all_docs),
            "filepath": str(filepath),
        }

    except Exception as exc:
        logger.error("ingest_postmortem error for %s: %s", incident_id, exc)
        return {"status": "error", "incident_id": incident_id, "message": str(exc)}


def mark_resolution_helpful(
    incident_id: str,
    helpful: bool,
) -> Dict[str, Any]:
    """
    Record whether a resolution was helpful or not.

    Stores a weight in output/resolution_weights.json:
        helpful=True  → weight += 1
        helpful=False → weight -= 1

    Args:
        incident_id: Incident identifier.
        helpful:     True if resolution was helpful, False otherwise.

    Returns:
        {status, incident_id, weight, helpful}
    """
    try:
        weights = _load_weights()
        current = weights.get(incident_id, {})
        score = int(current.get("weight", 0))
        score += 1 if helpful else -1

        weights[incident_id] = {
            "weight": score,
            "last_updated": datetime.now().isoformat(),
            "helpful_count": int(current.get("helpful_count", 0)) + (1 if helpful else 0),
            "unhelpful_count": int(current.get("unhelpful_count", 0)) + (0 if helpful else 1),
        }
        _save_weights(weights)

        logger.info(
            "Resolution weight for %s: %+d → %d",
            incident_id, 1 if helpful else -1, score,
        )
        return {
            "status": "success",
            "incident_id": incident_id,
            "weight": score,
            "helpful": helpful,
        }

    except Exception as exc:
        logger.error("mark_resolution_helpful error: %s", exc)
        return {"status": "error", "incident_id": incident_id, "message": str(exc)}


def get_knowledge_stats() -> Dict[str, Any]:
    """
    Return statistics about the current knowledge base state.

    Returns:
        {
            total_documents: int,
            sources: {source_name: count},
            postmortem_count: int,
            top_weighted: [{incident_id, weight}],
            index_loaded: bool,
            weights_file: str,
        }
    """
    try:
        from opsmind.retrieval.hybrid import _get_retriever

        retriever = _get_retriever()
        docs = retriever._docs

        # Source breakdown
        sources: Dict[str, int] = {}
        for doc in docs:
            src = doc.get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1

        postmortem_count = sources.get("postmortem", 0)

        # Top-weighted incidents from weights file
        weights = _load_weights()
        top_weighted = sorted(
            [{"incident_id": k, "weight": v["weight"]} for k, v in weights.items()],
            key=lambda x: x["weight"],
            reverse=True,
        )[:10]

        return {
            "status": "success",
            "total_documents": len(docs),
            "sources": sources,
            "postmortem_count": postmortem_count,
            "index_loaded": retriever._loaded,
            "top_weighted": top_weighted,
            "weights_file": _WEIGHTS_FILE,
        }

    except Exception as exc:
        logger.error("get_knowledge_stats error: %s", exc)
        return {"status": "error", "message": str(exc)}
