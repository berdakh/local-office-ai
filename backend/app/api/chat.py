"""Streaming conversations backed by the configured local model."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db.generated import archive_text
from app.llm import OllamaClient
from app.transcribe import Bible
from app.transcribe.lookup import lookup

from .deps import get_bible, get_chat_model, get_conn, get_llm

router = APIRouter(prefix="/chat", tags=["chat"])

GENERAL_PROMPT = (
    "You are a practical local assistant. Answer clearly and directly and build on the "
    "conversation. State meaningful uncertainty. You have no web, files, or live data in "
    "General mode. Never imply you have checked them. Use concise plain text."
)
BIBLE_PROMPT = (
    "You are a respectful Christian studies assistant for readers of different traditions. "
    "Distinguish the Bible text from interpretation or later Christian tradition. When "
    "Christians disagree, describe major views neutrally and indicate uncertainty. Use "
    "only the numbered World English Bible passages provided for scriptural claims. "
    "Refer to sources by bracketed number, such as [1], without inventing references "
    "or reproducing quotations. The app displays the exact text separately. If the passages "
    "do not answer the question, say that, and keep any broader explanation clearly labeled. "
    "Use concise plain text."
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    mode: Literal["general", "bible"]
    messages: list[ChatMessage] = Field(min_length=1, max_length=15)


def event(kind: str, value: object) -> str:
    return json.dumps({"type": kind, "value": value}, ensure_ascii=False) + "\n"


@router.post("")
async def chat(
    req: ChatRequest,
    llm: OllamaClient = Depends(get_llm),
    chat_model: str = Depends(get_chat_model),
    bible: Bible | None = Depends(get_bible),
    conn=Depends(get_conn),
):
    if req.messages[-1].role != "user" or not req.messages[-1].content.strip():
        raise HTTPException(400, "Enter a question to continue.")
    passages: list[dict[str, str]] = []
    system = GENERAL_PROMPT
    if req.mode == "bible":
        if bible is None:
            raise HTTPException(503, "The local Bible is unavailable. Check Settings.")
        passages = lookup(bible, req.messages[-1].content, limit=5, topics=True)
        # Carry explicit passages forward for follow-ups such as "Who is speaking here?"
        if not passages:
            for message in reversed(req.messages[:-1]):
                if message.role == "user":
                    passages = lookup(bible, message.content, limit=5, topics=True)
                    if passages:
                        break
        numbered = "\n\n".join(
            f"[{index}] {item['ref']}\n{item['text'][:1800]}"
            for index, item in enumerate(passages, start=1)
        )
        system = BIBLE_PROMPT + ("\n\n" + numbered if numbered else "\nNo passages matched.")

    # Leave room for sources and the answer, retaining the most recent conversation turns.
    history = []
    budget = 12_000
    for message in reversed(req.messages):
        if len(message.content) > budget:
            break
        history.append(message.model_dump())
        budget -= len(message.content)
    messages = [{"role": "system", "content": system}, *reversed(history)]

    async def stream() -> AsyncIterator[str]:
        yield event("sources", passages)
        pieces = []
        try:
            async for token in llm.chat_stream(
                messages, model=chat_model, options={"num_predict": 600}
            ):
                pieces.append(token)
                yield event("text", token)
        except (httpx.HTTPError, ValueError) as exc:
            yield event("error", f"The local model could not finish the answer. {exc}")
            return
        answer = "".join(pieces)
        if not answer.strip():
            yield event("error", "The local model returned an empty answer. Try another model.")
            return
        with conn:
            archive_text(
                conn,
                run_id=uuid4().hex,
                workflow=req.mode,
                output_key="answer",
                title=req.messages[-1].content.strip(),
                body=answer,
                model=chat_model,
                sources=[item["ref"] for item in passages],
            )
        yield event("done", None)

    return StreamingResponse(
        stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"}
    )
