from fastapi import APIRouter, Depends

from app.config import Settings
from app.llm import OllamaClient
from app.llm.ollama import model_tag
from app.transcribe.whisper import transcription_available
from app.workflows import Pack

from .deps import get_chat_model, get_llm, get_pack, get_settings_dep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    s: Settings = Depends(get_settings_dep),
    llm: OllamaClient = Depends(get_llm),
    pack: Pack = Depends(get_pack),
    chat_model: str = Depends(get_chat_model),
):
    available = await llm.is_available()
    models = await llm.list_models() if available else []
    tags = {model_tag(name) for name in models}
    return {
        "ok": True,
        "pack": pack.manifest.name,
        "pack_title": pack.manifest.title,
        "ollama": {"available": available, "url": s.ollama_url, "models": models},
        "chat_model": chat_model,
        "embed_model": s.embed_model,
        "chat_model_installed": chat_model in tags,
        "embed_model_installed": model_tag(s.embed_model) in tags,
        "data_dir": str(s.data_dir),
        "transcription_available": transcription_available(s.whisper_model_path),
        "whisper_model": s.whisper_model,
        "bible_installed": s.bible_path.exists(),
        "letterhead_installed": s.letterhead_path.exists(),
    }
