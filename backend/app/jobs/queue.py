"""In-process background jobs for long tasks (transcription, embedding). State lives in SQLite."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import traceback
import uuid
from collections.abc import Awaitable, Callable
from typing import Protocol


class ProgressFn(Protocol):
    def __call__(self, progress: float, detail: str | None = None, /) -> None: ...


JobFn = Callable[[ProgressFn], Awaitable[dict]]


class JobQueue:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._tasks: dict[str, asyncio.Task] = {}
        self.conn.execute(
            "UPDATE jobs SET status = 'error', error = ?, updated_at = datetime('now') "
            "WHERE status IN ('queued', 'running')",
            ("The app stopped before this work finished. Start it again to retry.",),
        )
        self.conn.commit()

    def submit(
        self,
        kind: str,
        fn: JobFn,
        *,
        label: str | None = None,
        route: str | None = None,
        context: dict | None = None,
    ) -> str:
        job_id = uuid.uuid4().hex[:12]
        self.conn.execute(
            "INSERT INTO jobs (id, kind, status, label, route, context) "
            "VALUES (?, ?, 'queued', ?, ?, ?)",
            (job_id, kind, label, route, json.dumps(context) if context is not None else None),
        )
        self.conn.commit()
        self._tasks[job_id] = asyncio.create_task(self._run(job_id, fn))
        return job_id

    def _set(self, job_id: str, **fields) -> None:
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE jobs SET {cols}, updated_at = datetime('now') WHERE id = ?",
            (*fields.values(), job_id),
        )
        self.conn.commit()

    async def _run(self, job_id: str, fn: JobFn) -> None:
        self._set(job_id, status="running")

        def progress(p: float, detail: str | None = None) -> None:
            if job_id in self._tasks:
                fields = {"detail": detail} if detail is not None else {}
                self._set(job_id, progress=max(0.0, min(1.0, p)), **fields)

        try:
            result = await fn(progress)
            self._set(job_id, status="done", progress=1.0, result=json.dumps(result))
        except asyncio.CancelledError:
            self._set(job_id, status="error", error="The app stopped before this work finished.")
            raise
        except Exception as e:  # noqa: BLE001 - job failures are recorded, not raised
            self._set(job_id, status="error", error=f"{e}\n{traceback.format_exc()}")
        finally:
            self._tasks.pop(job_id, None)

    async def close(self) -> None:
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def get(self, job_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        for key in ("result", "context"):
            d[key] = json.loads(d[key]) if d[key] else None
        return d

    def list(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, kind, label, detail, route, status, progress, error, "
            "created_at, updated_at FROM jobs "
            "ORDER BY (status IN ('queued', 'running')) DESC, created_at DESC, rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
