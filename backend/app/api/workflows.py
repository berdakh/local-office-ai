"""List and run pack workflows."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.audit import record
from app.config import Settings
from app.db.generated import archive_text
from app.jobs import JobQueue
from app.llm import OllamaClient
from app.render.docx import docx_bytes
from app.workflows import Pack, RunContext, run_workflow
from app.workflows.pack import Workflow

from .deps import (
    get_bible,
    get_chat_model,
    get_conn,
    get_jobs,
    get_llm,
    get_pack,
    get_settings_dep,
    validate_chat_model,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])


class DraftResume(BaseModel):
    email: str | None = Field(default=None, max_length=254)
    transcript_id: int | None = Field(default=None, gt=0)


class RunRequest(BaseModel):
    inputs: dict[str, Any]
    chat_model: str | None = Field(default=None, max_length=256)
    selected_outputs: list[str] | None = None
    resume: DraftResume | None = None


class ExportRequest(BaseModel):
    text: str
    format: Literal["md", "docx"]


@router.get("")
async def list_workflows(pack: Pack = Depends(get_pack)):
    return [
        {
            "id": w.id,
            "title": w.title,
            "description": w.description,
            "group": w.group,
            "inputs": [i.model_dump() for i in w.inputs],
            "outputs": [o.model_dump() for o in w.outputs],
        }
        for w in pack.workflows.values()
    ]


async def prepare_run(
    workflow_id: str,
    req: RunRequest,
    pack: Pack = Depends(get_pack),
    llm: OllamaClient = Depends(get_llm),
    conn=Depends(get_conn),
    s: Settings = Depends(get_settings_dep),
    bible=Depends(get_bible),
    chat_model: str = Depends(get_chat_model),
):
    wf = pack.workflows.get(workflow_id)
    if wf is None:
        raise HTTPException(404, f"No workflow {workflow_id!r}")
    if req.chat_model is not None:
        chat_model = await validate_chat_model(llm, req.chat_model)
    ctx = RunContext(
        pack=pack,
        llm=llm,
        conn=conn,
        outputs_dir=s.outputs_dir,
        bible=bible,
        chat_model=chat_model,
        embed_model=s.embed_model,
    )
    return wf, req, ctx


async def execute(wf: Workflow, req: RunRequest, ctx: RunContext) -> dict:
    assert ctx.conn is not None
    result = await run_workflow(wf, req.inputs, ctx, req.selected_outputs)
    scripture = result.state.get("scripture")
    sources = list(dict.fromkeys(hit.title for hit in result.citations))
    if scripture:
        sources.extend(ref["ref"] for ref in scripture["refs"] if ref["status"] == "verified")
    step_models = {step.id: step.model for step in wf.steps}
    fields = req.inputs.get("fields", {})
    with ctx.conn:
        for output in wf.outputs:
            value = result.outputs.get(output.name)
            if not isinstance(value, str) or result.no_evidence:
                continue
            title = output.name.replace("_", " ").capitalize()
            if wf.id == "letter" and isinstance(fields, dict):
                title = str(fields.get("subject") or req.inputs.get("letter_type") or title)
            archive_text(
                ctx.conn,
                run_id=result.id,
                workflow=wf.id,
                output_key=output.name,
                title=title,
                body=value,
                model=step_models.get(output.source) or ctx.chat_model or "Local model",
                sources=sources,
            )
        record(
            ctx.conn,
            "office",
            "workflow.run",
            {
                "workflow": wf.id,
                "chat_model": ctx.chat_model,
                "outputs": list(result.outputs),
                "citations": [hit.chunk_id for hit in result.citations],
            },
        )
    return {
        "run_id": result.id,
        "outputs": result.outputs,
        "citations": [h.__dict__ for h in result.citations],
        "files": [str(f) for f in result.files],
        "scripture": scripture,
    }


@router.post("/{workflow_id}/run")
async def run(prepared=Depends(prepare_run), s: Settings = Depends(get_settings_dep)):
    try:
        return await execute(*prepared)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(
            503, f"Could not reach the local model server at {s.ollama_url}. Is Ollama running?"
        ) from e


@router.post("/{workflow_id}/jobs", status_code=202)
async def start_run(prepared=Depends(prepare_run), jobs: JobQueue = Depends(get_jobs)):
    wf, req, ctx = prepared

    async def job(progress):
        ctx.report_progress = progress
        try:
            return await execute(wf, req, ctx)
        except httpx.HTTPError as error:
            raise RuntimeError(
                "The local model could not finish. Check Ollama in Settings."
            ) from error

    routes = {"sermon_studio": "/sermon", "announcements": "/announcements", "letter": "/letters"}
    label = {
        "sermon_studio": "Sermon drafts",
        "announcements": "Announcement drafts",
        "letter": "Correspondence draft",
    }.get(wf.id, wf.title)
    context = {
        "workflow": wf.id,
        "inputs": {
            field.name: req.inputs[field.name] for field in wf.inputs if field.name in req.inputs
        },
        "chat_model": ctx.chat_model,
        "selected_outputs": req.selected_outputs,
    }
    if req.resume:
        if wf.id == "letter":
            context["email"] = req.resume.email
        elif wf.id == "sermon_studio":
            context["transcript_id"] = req.resume.transcript_id
    return {
        "job_id": jobs.submit(
            "workflow", job, label=label, route=routes.get(wf.id, "/generated"), context=context
        )
    }


@router.post("/{workflow_id}/outputs/{output_name}/export")
def export_output(
    workflow_id: str,
    output_name: str,
    req: ExportRequest,
    pack: Pack = Depends(get_pack),
):
    workflow = pack.workflows.get(workflow_id)
    if workflow is None:
        raise HTTPException(404, "Workflow not found")
    output = next((item for item in workflow.outputs if item.name == output_name), None)
    if output is None or output.type == "json":
        raise HTTPException(404, "Draft output not found")

    if req.format == "docx":
        template = pack.templates_dir / output.template if output.template else None
        content = docx_bytes(req.text, template)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        content = req.text.encode("utf-8")
        media_type = "text/markdown; charset=utf-8"

    filename = quote(f"{output.name.replace('_', '-')}.{req.format}", safe="")
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
