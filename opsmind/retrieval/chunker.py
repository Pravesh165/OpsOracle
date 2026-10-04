"""Text chunker for long documents."""
from typing import List


def chunk_document(text: str, max_tokens: int = 512) -> List[str]:
    """Split text into chunks of approximately max_tokens words."""
    if not text or not text.strip():
        return []
    words = text.split()
    if len(words) <= max_tokens:
        return [text]
    chunks = []
    for i in range(0, len(words), max_tokens):
        chunk = " ".join(words[i : i + max_tokens])
        if chunk.strip():
            chunks.append(chunk)
    return chunks
