"""
Build FAISS index from CSV datasets.

Usage:
    python scripts/build_index.py
"""
import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from opsmind.data.loader import load_incident_data, load_jira_data
from opsmind.retrieval.chunker import chunk_document
from opsmind.retrieval.embedder import embed_texts
from opsmind.retrieval.index import VectorIndex
from opsmind.retrieval.hybrid import build_index
import numpy as np


def _build_docs():
    docs = []

    # Incidents
    try:
        incidents_df = load_incident_data()
        for _, row in incidents_df.iterrows():
            text = " ".join(filter(None, [
                str(row.get("short_description", "")),
                str(row.get("description", "")),
                str(row.get("u_symptom", "")),
                str(row.get("category", "")),
            ]))
            for chunk in chunk_document(text):
                docs.append({
                    "text": chunk,
                    "source": "incident",
                    "id": str(row.get("number", "")),
                    "category": str(row.get("category", "")),
                    "priority": str(row.get("priority", "")),
                    "resolution": str(row.get("closed_code", "")),
                })
        print(f"Incidents: {len(incidents_df)} rows")
    except Exception as e:
        print(f"Warning: could not load incidents: {e}")

    # Jira
    try:
        jira_data = load_jira_data()

        issues_df = jira_data.get("issues")
        if issues_df is not None and not issues_df.empty:
            for _, row in issues_df.iterrows():
                text = " ".join(filter(None, [
                    str(row.get("summary", "")),
                    str(row.get("description", "")),
                ]))
                for chunk in chunk_document(text):
                    docs.append({
                        "text": chunk,
                        "source": "jira_issue",
                        "id": str(row.get("key", "")),
                        "summary": str(row.get("summary", "")),
                        "status": str(row.get("status.name", "")),
                        "priority": str(row.get("priority.name", "")),
                    })
            print(f"Jira issues: {len(issues_df)} rows")

        comments_df = jira_data.get("comments")
        if comments_df is not None and not comments_df.empty:
            body_col = "body" if "body" in comments_df.columns else "comment.body"
            key_col = "issue_key" if "issue_key" in comments_df.columns else "key"
            for _, row in comments_df.iterrows():
                text = str(row.get(body_col, ""))
                for chunk in chunk_document(text):
                    docs.append({
                        "text": chunk,
                        "source": "jira_comment",
                        "id": str(row.get(key_col, "")),
                        "author": str(row.get("author.displayName", row.get("author", ""))),
                    })
            print(f"Jira comments: {len(comments_df)} rows")
    except Exception as e:
        print(f"Warning: could not load Jira data: {e}")

    return docs


def main():
    print("Building index...")
    docs = _build_docs()
    if not docs:
        print("No documents found. Ensure datasets are downloaded.")
        sys.exit(1)

    print(f"Total chunks: {len(docs)}")
    print("Embedding (this may take a while)...")

    texts = [d["text"] for d in docs]
    vectors = embed_texts(texts)

    index_path = os.path.join(os.path.dirname(__file__), "..", "output", "opsmind.index")
    os.makedirs(os.path.dirname(index_path), exist_ok=True)

    vi = VectorIndex()
    vi.build(docs, vectors)
    vi.save(index_path)

    # Also wire into the in-memory retriever
    build_index(docs)

    print(f"Index saved to {index_path} ({vi.size} vectors)")


if __name__ == "__main__":
    main()
