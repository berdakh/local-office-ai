"""Audio in, transcript out. Transcription runs as a background job; the result is a
library document of kind 'transcript' with scripture references checked."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.audit import record
from app.config import Settings
from app.ingest import Page
from app.jobs import JobQueue
from app.llm import OllamaClient
from app.rag import add_document, embed_document, get_document, list_documents
from app.transcribe import check_text, segments_to_text
from app.transcribe.whisper import transcription_available

from .deps import get_bible, get_conn, get_jobs, get_llm, get_settings_dep, get_transcriber

router = APIRouter(tags=["transcribe"])

AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".mp4", ".ogg", ".flac", ".aac", ".webm", ".wma"}


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name) or "recording"


@router.post("/transcribe")
async def transcribe(
    file: UploadFile,
    conn=Depends(get_conn),
    s: Settings = Depends(get_settings_dep),
    llm: OllamaClient = Depends(get_llm),
    jobs: JobQueue = Depends(get_jobs),
    transcriber=Depends(get_transcriber),
    bible=Depends(get_bible),
):
    if not transcription_available():
        raise HTTPException(
            503, "Transcription is not installed on this machine. Run: uv sync --extra transcribe"
        )
    name = _safe_name(file.filename or "recording")
    ext = Path(name).suffix.lower()
    if ext not in AUDIO_EXTS:
        raise HTTPException(400, f"Unsupported audio type {ext}. Allowed: {sorted(AUDIO_EXTS)}")
    dest = s.files_dir / name
    dest.write_bytes(await file.read())
    record(conn, "office", "transcribe.upload", {"name": name})

    async def job(progress):
        loop = asyncio.get_running_loop()

        def on_progress(p: float) -> None:
            loop.call_soon_threadsafe(progress, p * 0.9)

        segments = await asyncio.to_thread(transcriber.transcribe, dest, on_progress)
        text = segments_to_text(segments)
        checks = check_text(text, bible)

        stem = Path(name).stem
        out_dir = s.outputs_dir / "transcripts"
        out_dir.mkdir(parents=True, exist_ok=True)
        text_path = out_dir / f"{stem}.md"
        text_path.write_text(text, encoding="utf-8")
        seg_path = out_dir / f"{stem}.segments.json"
        seg_path.write_text(
            json.dumps([seg.__dict__ for seg in segments], ensure_ascii=False), encoding="utf-8"
        )

        meta = {
            "audio_path": str(dest),
            "text_path": str(text_path),
            "segments_path": str(seg_path),
            "duration": getattr(transcriber, "last_duration", 0.0),
            "segments": len(segments),
            "scripture": [c.to_dict() for c in checks],
            "whisper_model": s.whisper_model,
        }
        doc_id = add_document(
            conn,
            stem,
            str(text_path),
            "transcript",
            [Page(text)],
            s.chunk_size,
            s.chunk_overlap,
            meta=meta,
        )
        progress(0.95)
        try:
            await embed_document(conn, doc_id, llm.embed, s.embed_model)
            embedded = True
        except Exception:  # noqa: BLE001 - Ollama may be down; transcript is still saved
            embedded = False
        record(conn, "office", "transcribe.done", {"document_id": doc_id, "name": name})
        return {
            "document_id": doc_id,
            "title": stem,
            "text": text,
            "scripture": meta["scripture"],
            "segments": len(segments),
            "duration": meta["duration"],
            "embedded": embedded,
        }

    job_id = jobs.submit("transcribe", job)
    return {"job_id": job_id, "name": name}


@router.get("/transcripts")
async def transcripts(conn=Depends(get_conn)):
    out = []
    for d in list_documents(conn, kind="transcript"):
        m = d.get("meta", {})
        out.append(
            {
                "id": d["id"],
                "title": d["title"],
                "created_at": d["created_at"],
                "duration": m.get("duration"),
                "scripture": m.get("scripture", []),
            }
        )
    return out


@router.get("/transcripts/{doc_id}")
async def transcript(doc_id: int, conn=Depends(get_conn)):
    d = get_document(conn, doc_id)
    if d is None or d["kind"] != "transcript":
        raise HTTPException(404, "No such transcript")
    text_path = Path(d["meta"].get("text_path", d["path"]))
    text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
    return {"id": d["id"], "title": d["title"], "text": text, "meta": d["meta"]}
