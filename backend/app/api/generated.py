"""Search and edit the local generated-text database."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .deps import get_conn

router = APIRouter(prefix="/generated", tags=["generated"])
Status = Literal["draft", "reviewed"]


def _item(row) -> dict:
    item = dict(row)
    for key in ("tags", "sources"):
        item[key] = json.loads(item[key])
    return item


@router.get("")
async def list_texts(
    q: str = Query(default="", max_length=250),
    workflow: str = Query(default="", max_length=80),
    status: Status | None = None,
    sort: Literal["newest", "oldest", "title"] = "newest",
    run_id: str = Query(default="", max_length=64),
    offset: int = Query(default=0, ge=0),
    conn=Depends(get_conn),
):
    where = (
        "WHERE (:q = '' OR instr(lower(title || ' ' || body || ' ' || tags), lower(:q))) "
        "AND (:workflow = '' OR workflow = :workflow) "
        "AND (:status IS NULL OR status = :status) "
        "AND (:run_id = '' OR run_id = :run_id)"
    )
    args = {
        "q": q.strip(),
        "workflow": workflow,
        "status": status,
        "offset": offset,
        "run_id": run_id,
    }
    order = {
        "newest": "created_at DESC, id DESC",
        "oldest": "created_at, id",
        "title": "title COLLATE NOCASE, id",
    }[sort]
    fields = (
        "id, run_id, workflow, output_key, title, model, sources, tags, status, created_at, "
        "updated_at, substr(body, 1, 160) AS preview"
    )
    rows = conn.execute(
        f"SELECT {fields} FROM generated_texts {where} ORDER BY {order} LIMIT 40 OFFSET :offset",
        args,
    ).fetchall()
    total = conn.execute(f"SELECT count(*) FROM generated_texts {where}", args).fetchone()[0]
    return {"items": [_item(row) for row in rows], "total": total}


@router.get("/{text_id}")
async def get_text(text_id: int, conn=Depends(get_conn)):
    row = conn.execute("SELECT * FROM generated_texts WHERE id = ?", (text_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "This generated text is unavailable.")
    return _item(row)


class UpdateText(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=100_000)
    status: Status
    tags: list[str] = Field(max_length=20)


@router.put("/{text_id}")
async def update_text(text_id: int, update: UpdateText, conn=Depends(get_conn)):
    if not update.title.strip() or not update.body.strip():
        raise HTTPException(400, "Enter a title and some text.")
    tags = list(dict.fromkeys(tag.strip()[:45] for tag in update.tags if tag.strip()))
    row = conn.execute(
        "UPDATE generated_texts SET title=?, body=?, status=?, tags=?, "
        "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=? RETURNING *",
        (update.title.strip(), update.body, update.status, json.dumps(tags), text_id),
    ).fetchone()
    conn.commit()
    if row is None:
        raise HTTPException(404, "This generated text is unavailable.")
    return _item(row)
