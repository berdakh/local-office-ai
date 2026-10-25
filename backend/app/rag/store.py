"""Documents and chunks in SQLite, embeddings as float32 blobs."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Awaitable, Callable

import numpy as np

from app.ingest import Page, chunk_text

EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]


def add_document(
    conn: sqlite3.Connection,
    title: str,
    path: str,
    kind: str,
    pages: list[Page],
    chunk_size: int = 800,
    chunk_overlap: int = 120,
    meta: dict | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO documents (title, path, kind, meta) VALUES (?, ?, ?, ?)",
        (title, path, kind, json.dumps(meta, ensure_ascii=False) if meta else None),
    )
    doc_id = int(cur.lastrowid)
    idx = 0
    for page in pages:
        for piece in chunk_text(page.text, chunk_size, chunk_overlap):
            conn.execute(
                "INSERT INTO chunks (document_id, idx, page, text) VALUES (?, ?, ?, ?)",
                (doc_id, idx, page.page, piece),
            )
            idx += 1
    conn.commit()
    return doc_id


async def embed_document(
    conn: sqlite3.Connection, doc_id: int, embed: EmbedFn, model: str, batch: int = 32
) -> int:
    rows = conn.execute(
        "SELECT id, text FROM chunks WHERE document_id = ? ORDER BY idx", (doc_id,)
    ).fetchall()
    count = 0
    for i in range(0, len(rows), batch):
        part = rows[i : i + batch]
        vectors = await embed([r["text"] for r in part])
        for row, vec in zip(part, vectors, strict=True):
            arr = np.asarray(vec, dtype=np.float32)
            conn.execute(
                "INSERT OR REPLACE INTO chunk_embeddings (chunk_id, model, dim, embedding) "
                "VALUES (?, ?, ?, ?)",
                (row["id"], model, arr.size, arr.tobytes()),
            )
            count += 1
    conn.commit()
    return count


def list_documents(conn: sqlite3.Connection, kind: str | None = None) -> list[dict]:
    where = "WHERE d.kind = ?" if kind else ""
    rows = conn.execute(
        "SELECT d.id, d.title, d.kind, d.meta, d.created_at, COUNT(c.id) AS chunks "
        f"FROM documents d LEFT JOIN chunks c ON c.document_id = d.id {where} "
        "GROUP BY d.id ORDER BY d.created_at DESC, d.id DESC",
        (kind,) if kind else (),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["meta"] = json.loads(d["meta"]) if d["meta"] else {}
        out.append(d)
    return out


def get_document(conn: sqlite3.Connection, doc_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if r is None:
        return None
    d = dict(r)
    d["meta"] = json.loads(d["meta"]) if d["meta"] else {}
    return d


def remove_document(conn: sqlite3.Connection, doc_id: int) -> None:
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
