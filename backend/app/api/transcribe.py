"""Audio in, transcript out. Transcription runs as a background job; the result is a
library document of kind 'transcript' with scripture references checked."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.audit import record
from app.config import Settings
from app.ingest import Page
from app.jobs import JobQueue
from app.llm import OllamaClient
from app.rag import add_document, embed_document, get_document, list_documents
from app.transcribe import check_text, segments_to_text
from app.transcribe.whisper import transcription_available

from .deps import get_bible, get_conn, get_jobs, get_llm, get_settings_dep, get_transcriber
from .uploads import save_upload, upload_name

router = APIRouter(tags=["transcribe"])

AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".mp4", ".ogg", ".flac", ".aac", ".webm", ".wma"}
AUDIO_MIME = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".webm": "audio/webm",
    ".wma": "audio/x-ms-wma",
}
MAX_PREVIEW_BYTES = 16_000 * 2 * 12


@router.post("/transcribe/live")
async def preview_transcript(
    request: Request,
    s: Settings = Depends(get_settings_dep),
    transcriber=Depends(get_transcriber),
):
    if not transcription_available(s.whisper_model_path):
        raise HTTPException(503, "The local transcription model is unavailable.")
    if request.headers.get("content-type") != "application/octet-stream":
        raise HTTPException(415, "Send 16 kHz, 16-bit mono PCM audio.")
    pcm = bytearray()
    async for chunk in request.stream():
        if len(pcm) + len(chunk) > MAX_PREVIEW_BYTES:
            raise HTTPException(413, "Live transcription accepts up to twelve seconds per batch.")
        pcm.extend(chunk)
    if not pcm or len(pcm) % 2:
        raise HTTPException(400, "Invalid PCM audio.")
    try:
        text = await asyncio.to_thread(transcriber.preview, bytes(pcm))
    except RuntimeError as exc:
        raise HTTPException(503, "Could not transcribe the microphone preview.") from exc
    return {"text": text}


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
    if not transcription_available(s.whisper_model_path):
        raise HTTPException(
            503, "The local transcription model or package is missing. Prepare the pilot first."
        )
    name = upload_name(file.filename, "recording")
    ext = Path(name).suffix.lower()
    if ext not in AUDIO_EXTS:
        raise HTTPException(400, f"Unsupported audio type {ext}. Allowed: {sorted(AUDIO_EXTS)}")
    dest = await save_upload(file, s.files_dir, name)
    record(conn, "office", "transcribe.upload", {"name": name})

    async def job(progress):
        progress(0, "Transcribing recording")
        loop = asyncio.get_running_loop()

        def on_progress(p: float) -> None:
            loop.call_soon_threadsafe(progress, p * 0.9)

        transcription = await asyncio.to_thread(transcriber.transcribe, dest, on_progress)
        segments = transcription.segments
        text = segments_to_text(segments)
        checks = check_text(text, bible)

        stem = Path(name).stem
        out_dir = s.outputs_dir / "transcripts" / dest.parent.name
        out_dir.mkdir(parents=True, exist_ok=False)
        text_path = out_dir / "transcript.md"
        text_path.write_text(text, encoding="utf-8")
        seg_path = out_dir / "segments.json"
        seg_path.write_text(
            json.dumps([seg.__dict__ for seg in segments], ensure_ascii=False), encoding="utf-8"
        )

        meta = {
            "audio_path": str(dest),
            "text_path": str(text_path),
            "segments_path": str(seg_path),
            "duration": transcription.duration,
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
        progress(0.95, "Indexing the transcript")
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
            "audio_available": True,
            "scripture": meta["scripture"],
            "segments": len(segments),
            "duration": meta["duration"],
            "embedded": embedded,
        }

    job_id = jobs.submit(
        "transcribe",
        job,
        label=f"Transcribing {name}",
        route="/sermon",
        context={"name": name, "recording": str(dest.resolve().relative_to(s.files_dir.resolve()))},
    )
    return {"job_id": job_id, "name": name}


@router.get("/transcription-jobs/{job_id}/audio")
async def transcription_job_audio(
    job_id: str, jobs: JobQueue = Depends(get_jobs), settings: Settings = Depends(get_settings_dep)
):
    job = jobs.get(job_id)
    recording = (
        (job["context"] or {}).get("recording") if job and job["kind"] == "transcribe" else None
    )
    return _serve_audio(
        str(settings.files_dir / recording) if recording else None, settings.files_dir
    )


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
async def transcript(
    doc_id: int, conn=Depends(get_conn), settings: Settings = Depends(get_settings_dep)
):
    d = get_document(conn, doc_id)
    if d is None or d["kind"] != "transcript":
        raise HTTPException(404, "No such transcript")
    text_path = Path(d["meta"].get("text_path", d["path"]))
    text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
    audio_path = _media_path(d["meta"].get("audio_path"), settings.files_dir)
    segments_path = _media_path(d["meta"].get("segments_path"), settings.outputs_dir)
    segments = json.loads(segments_path.read_text(encoding="utf-8")) if segments_path else []
    return {
        "id": d["id"],
        "title": d["title"],
        "text": text,
        "meta": d["meta"],
        "audio_available": audio_path is not None,
        "timeline": segments,
    }


def _media_path(value: str | None, root: Path) -> Path | None:
    if not value:
        return None
    path = Path(value).resolve()
    return path if path.is_relative_to(root.resolve()) and path.is_file() else None


@router.get("/transcripts/{doc_id}/audio")
async def transcript_audio(
    doc_id: int, conn=Depends(get_conn), settings: Settings = Depends(get_settings_dep)
):
    doc = get_document(conn, doc_id)
    if doc is None or doc["kind"] != "transcript":
        raise HTTPException(404, "No such transcript.")
    return _serve_audio(doc["meta"].get("audio_path"), settings.files_dir)


def _serve_audio(value: str | None, root: Path) -> FileResponse:
    path = _media_path(value, root)
    if path is None or path.suffix.lower() not in AUDIO_MIME:
        raise HTTPException(404, "The original recording is unavailable.")
    return FileResponse(
        path,
        media_type=AUDIO_MIME[path.suffix.lower()],
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
