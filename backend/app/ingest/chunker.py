"""Word-based chunking with overlap. Simple on purpose; tune after real documents."""

import re


def chunk_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    words = list(re.finditer(r"\S+", text))
    if not words:
        return []
    chunks = []
    step = size - overlap
    for start in range(0, len(words), step):
        end = min(start + size, len(words))
        chunks.append(text[words[start].start() : words[end - 1].end()])
        if end == len(words):
            break
    return chunks
