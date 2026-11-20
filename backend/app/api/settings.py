from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import Settings
from app.llm import OllamaClient
from app.llm.ollama import model_tag
from app.workflows import Pack

from .deps import get_chat_model, get_conn, get_llm, get_pack, get_settings_dep, validate_chat_model

router = APIRouter(tags=["settings"])


@router.get("/settings")
async def read_settings(
    s: Settings = Depends(get_settings_dep),
    pack: Pack = Depends(get_pack),
    chat_model: str = Depends(get_chat_model),
):
    return {
        "data_dir": str(s.data_dir),
        "pack": s.pack,
        "chat_model": chat_model,
        "embed_model": s.embed_model,
        "whisper_model": s.whisper_model,
        "pin_enabled": bool(s.pin),
        "nav": [n.model_dump() for n in pack.manifest.nav],
        "hardware_tiers": [t.model_dump() for t in pack.manifest.hardware_tiers],
    }


class ModelPreference(BaseModel):
    chat_model: str | None = Field(max_length=256)


@router.get("/settings/models")
async def list_chat_models(llm: OllamaClient = Depends(get_llm)):
    return await llm.list_chat_models()


@router.put("/settings/models")
async def save_model(
    preference: ModelPreference,
    llm: OllamaClient = Depends(get_llm),
    conn=Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
):
    if preference.chat_model is None:
        conn.execute("DELETE FROM app_preferences WHERE key = 'chat_model'")
        model = model_tag(settings.chat_model)
    else:
        model = await validate_chat_model(llm, preference.chat_model)
        conn.execute(
            "INSERT INTO app_preferences (key, value) VALUES ('chat_model', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (model,),
        )
    conn.commit()
    return {"chat_model": model}
