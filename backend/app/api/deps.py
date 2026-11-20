"""Shared request dependencies. Everything hangs off app.state, set up in main.lifespan."""

from fastapi import Depends, HTTPException, Request

from app.config import Settings
from app.jobs import JobQueue
from app.llm import OllamaClient
from app.llm.ollama import model_tag
from app.workflows import Pack


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_conn(request: Request):
    return request.app.state.conn


def get_llm(request: Request) -> OllamaClient:
    return request.app.state.llm


async def get_chat_model(
    conn=Depends(get_conn), settings: Settings = Depends(get_settings_dep)
) -> str:
    row = conn.execute("SELECT value FROM app_preferences WHERE key = 'chat_model'").fetchone()
    return model_tag(row["value"] if row else settings.chat_model)


async def validate_chat_model(llm: OllamaClient, name: str) -> str:
    tag = model_tag(name)
    if not await llm.has_chat_model(tag):
        raise HTTPException(400, "Choose an installed Ollama model that supports drafting.")
    return tag


def get_pack(request: Request) -> Pack:
    return request.app.state.pack


def get_jobs(request: Request) -> JobQueue:
    return request.app.state.jobs


def get_transcriber(request: Request):
    return request.app.state.transcriber


def get_bible(request: Request):
    return request.app.state.bible
