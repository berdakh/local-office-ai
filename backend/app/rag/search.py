"""Hybrid retrieval: BM25 over chunk text plus cosine over embeddings, fused with RRF."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

import httpx
import numpy as np
from rank_bm25 import BM25L

from app.llm.ollama import model_tag

from .store import EmbedFn

_TOKEN = re.compile(r"\w+")
_FUNCTION_WORDS = frozenset(
    "a an and are as at be by can could did do does for from had has have how i in is it "
    "may of on or our should that the their there these they this those to was we were "
    "what when where which who why will with would you your".split()
)


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class Hit:
    chunk_id: int
    document_id: int
    title: str
    page: int | None
    text: str
    score: float


def _rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return scores


async def _semantic_ranking(
    conn: sqlite3.Connection,
    query: str,
    embed: EmbedFn,
    embedding_model: str | None,
    candidates: int,
) -> list[int]:
    sql = "SELECT chunk_id, embedding, dim FROM chunk_embeddings"
    if embedding_model is None:
        rows = conn.execute(sql).fetchall()
    else:
        name = model_tag(embedding_model)
        rows = conn.execute(
            sql + " WHERE model IN (?, ?)", (name, name.removesuffix(":latest"))
        ).fetchall()
    if not rows:
        return []

    try:
        qvec = np.asarray((await embed([query]))[0], dtype=np.float32)
    except (httpx.HTTPError, IndexError, KeyError, TypeError, ValueError):
        # Text search remains available if the local embedding service cannot supply a vector.
        return []
    if qvec.ndim != 1 or not np.isfinite(qvec).all():
        return []
    query_norm = np.linalg.norm(qvec)
    if not np.isfinite(query_norm) or query_norm <= 0:
        return []

    compatible = [r for r in rows if r["dim"] == qvec.size and len(r["embedding"]) == qvec.nbytes]
    if not compatible:
        return []
    mat = np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in compatible])
    norms = np.linalg.norm(mat, axis=1) * query_norm
    sims = mat @ qvec / np.where(norms == 0, 1.0, norms)
    positive = np.flatnonzero((sims > 0) & np.isfinite(sims))
    order = positive[np.argsort(-sims[positive])[:candidates]]
    return [compatible[i]["chunk_id"] for i in order]


def lexical_order(query: str, texts: list[str], *, match_prefixes: bool = False) -> list[int]:
    if not texts:
        return []
    # BM25L's IDF stays positive even for a two-document library.
    tokens = [_tokenize(text) for text in texts]
    query_tokens = [token for token in _tokenize(query) if token not in _FUNCTION_WORDS]
    if match_prefixes:
        vocabulary = {word for words in tokens for word in words}
        stems = {term for term in query_tokens if len(term) >= 5}
        query_tokens.extend(
            word
            for word in sorted(vocabulary - set(query_tokens))
            if any(word.startswith(term) for term in stems)
        )
    if not query_tokens or not any(tokens):
        return []
    terms = set(query_tokens)
    scores = BM25L(tokens).get_scores(query_tokens)
    return sorted(
        (index for index, words in enumerate(tokens) if terms.intersection(words)),
        key=lambda index: -scores[index],
    )


async def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    embed: EmbedFn | None,
    k: int = 6,
    candidates: int = 25,
    *,
    embedding_model: str | None = None,
) -> list[Hit]:
    rows = conn.execute(
        "SELECT c.id, c.document_id, c.page, c.text, d.title "
        "FROM chunks c JOIN documents d ON d.id = c.document_id"
    ).fetchall()
    if not rows:
        return []
    by_id = {r["id"]: r for r in rows}

    order = lexical_order(query, [row["text"] for row in rows])
    lex_rank = [rows[i]["id"] for i in order[:candidates]]

    rankings = [lex_rank]

    # Semantic ranking, only if we have an embedder and stored vectors
    if embed is not None:
        rankings.append(await _semantic_ranking(conn, query, embed, embedding_model, candidates))

    fused = _rrf(rankings)
    top = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
    hits = []
    for cid, score in top:
        r = by_id.get(cid)
        if r is None:
            continue
        hits.append(
            Hit(
                chunk_id=cid,
                document_id=r["document_id"],
                title=r["title"],
                page=r["page"],
                text=r["text"],
                score=score,
            )
        )
    return hits
