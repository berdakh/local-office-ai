"""Write model-generated text and its provenance to the local archive."""

from __future__ import annotations

import json
import sqlite3


def archive_text(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    workflow: str,
    output_key: str,
    title: str,
    body: str,
    model: str,
    sources: list[str] | None = None,
) -> None:
    if not body.strip():
        return
    conn.execute(
        "INSERT INTO generated_texts (run_id, workflow, output_key, title, body, model, sources) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(run_id, output_key) DO NOTHING",
        (run_id, workflow, output_key, title[:200], body, model, json.dumps(sources or [])),
    )
