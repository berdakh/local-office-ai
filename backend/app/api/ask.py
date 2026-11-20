"""Ask the Office: a question over the library with citations.

Thin wrapper over the pack's `ask` workflow.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.audit import record
from app.config import Settings
from app.db.generated import archive_text
from app.llm import OllamaClient
from app.workflows import Pack, RunContext, run_workflow

from .deps import get_chat_model, get_conn, get_llm, get_pack, get_settings_dep

router = APIRouter(prefix="/ask", tags=["ask"])


class AskRequest(BaseModel):
    question: str


@router.post("")
async def ask(
    req: AskRequest,
    pack: Pack = Depends(get_pack),
    llm: OllamaClient = Depends(get_llm),
    conn=Depends(get_conn),
    chat_model: str = Depends(get_chat_model),
    settings: Settings = Depends(get_settings_dep),
):
    wf = pack.workflows.get("ask")
    if wf is None:
        raise HTTPException(500, "This pack has no 'ask' workflow")
    ctx = RunContext(
        pack=pack, llm=llm, conn=conn, chat_model=chat_model, embed_model=settings.embed_model
    )
    try:
        result = await run_workflow(wf, {"question": req.question}, ctx)
    except httpx.HTTPError as e:
        raise HTTPException(
            503, f"Could not reach the local model server at {llm.base_url}. Is Ollama running?"
        ) from e
    answer = result.outputs.get("answer", "")
    if not result.no_evidence:
        archive_text(
            conn,
            run_id=result.id,
            workflow="ask",
            output_key="answer",
            title=req.question.strip(),
            body=answer,
            model=chat_model,
            sources=list(dict.fromkeys(hit.title for hit in result.citations)),
        )
    record(
        conn,
        "office",
        "ask",
        {"question": req.question, "citations": [h.chunk_id for h in result.citations]},
    )
    return {
        "answer": answer,
        "citations": [h.__dict__ for h in result.citations],
    }
