"""Run a workflow: a sequence of steps sharing one state dict.

State keys are the workflow's input names and each step's id. Prompts see the
whole state, so a step can reference any earlier result by name.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from app.llm.prompts import PromptRenderer
from app.rag.search import Hit, hybrid_search, lexical_order
from app.render import write_docx, write_markdown
from app.transcribe.bible import Bible, check_text, format_checks

from .pack import Pack, Workflow, WorkflowStep


class LLM(Protocol):
    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        options: dict | None = None,
        *,
        think: bool | None = None,
    ) -> str: ...

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]: ...


class Transcribe(Protocol):
    def __call__(self, path: Path) -> str: ...


@dataclass
class RunContext:
    pack: Pack
    llm: LLM
    conn: sqlite3.Connection | None = None
    outputs_dir: Path | None = None
    transcribe: Transcribe | None = None
    bible: Bible | None = None
    chat_model: str | None = None
    embed_model: str | None = None
    citations: list[Hit] = field(default_factory=list)
    report_progress: Callable[[float, str], None] | None = None


@dataclass
class RunResult:
    id: str
    state: dict[str, Any]
    outputs: dict[str, Any]
    citations: list[Hit]
    files: list[Path]
    no_evidence: bool = False


NO_SOURCE_REPLY = (
    "I didn’t find relevant passages in your Library. "
    "Add a relevant document or try a more specific question."
)


def _format_hits(hits: list[Hit]) -> str:
    blocks = []
    for i, h in enumerate(hits, start=1):
        where = f"{h.title}" + (f", page {h.page}" if h.page else "")
        blocks.append(f"[{i}] ({where})\n{h.text}")
    return "\n\n".join(blocks)


def _source_lines(question: str, hits: list[Hit]) -> tuple[str, dict[str, tuple[str, Hit]]]:
    excerpts: list[tuple[str, Hit]] = []
    for hit in hits:
        for excerpt in re.split(r"(?<=[.!?])\s+(?=[A-Z“])|\n+", hit.text):
            if excerpt.strip():
                excerpts.append((excerpt.strip(), hit))
    order = lexical_order(question, [excerpt for excerpt, _ in excerpts], match_prefixes=True)
    # Keep semantic candidates when paraphrasing leaves little vocabulary in common.
    seen = set(order)
    order.extend(index for index in range(len(excerpts)) if index not in seen)
    choices = dict(zip("ABCDEFGH", (excerpts[index] for index in order[:8]), strict=False))
    lines = [
        f"{letter}) [{hit.title.replace('_', ' ')}] {excerpt}"
        for letter, (excerpt, hit) in choices.items()
    ]
    return "\n".join(lines), choices


def _parse_json(text: str) -> Any:
    m = re.search(r"\{.*\}|\[.*\]", text, re.DOTALL)
    return json.loads(m.group(0) if m else text)


async def _run_step(
    step: WorkflowStep, state: dict[str, Any], ctx: RunContext, renderer: PromptRenderer
) -> Any:
    if step.type in {"generate", "extract", "quote"}:
        if not step.prompt:
            raise ValueError(f"step {step.id}: {step.type} needs a prompt")
        prompt = renderer.render(step.prompt, **state)
        system = renderer.render(step.system, **state) if step.system else None
        model = step.model or ctx.chat_model
        if step.type == "quote":
            return await ctx.llm.generate(
                prompt,
                system=system,
                model=model,
                options={"temperature": 0, "num_predict": 96},
                think=False,
            )
        text = await ctx.llm.generate(prompt, system=system, model=model)
        return _parse_json(text) if step.type == "extract" else text

    if step.type == "retrieve":
        if ctx.conn is None:
            raise ValueError(f"step {step.id}: retrieve needs a database connection")
        query = str(state[step.source]) if step.source else str(state.get("question", ""))
        hits = await hybrid_search(
            ctx.conn, query, ctx.llm.embed, k=step.k, embedding_model=ctx.embed_model
        )
        ctx.citations.extend(hits)
        return {"hits": [h.__dict__ for h in hits], "context": _format_hits(hits)}

    if step.type == "transcribe":
        if ctx.transcribe is None:
            raise ValueError(f"step {step.id}: no transcriber configured")
        audio = state[step.source or "audio"]
        return ctx.transcribe(Path(str(audio)))

    if step.type == "scripture":
        text = str(state[step.source or "transcript"])
        checks = check_text(text, ctx.bible)
        version = ctx.bible.version if ctx.bible else "WEB"
        return {
            "refs": [c.to_dict() for c in checks],
            "context": format_checks(checks, version),
            "verified": ctx.bible is not None,
        }

    if step.type == "render":
        return state[step.source] if step.source else ""

    raise ValueError(f"unknown step type {step.type}")


async def run_workflow(
    workflow: Workflow,
    inputs: dict[str, Any],
    ctx: RunContext,
    selected_outputs: list[str] | None = None,
) -> RunResult:
    for inp in workflow.inputs:
        if inp.required and inp.name not in inputs:
            raise ValueError(f"missing required input {inp.name!r}")
    output_specs = workflow.outputs
    skipped_sources: set[str] = set()
    if selected_outputs is not None:
        names = {out.name for out in output_specs}
        if not workflow.selectable_outputs or not selected_outputs or set(selected_outputs) - names:
            raise ValueError("Choose one or more available drafts for this workflow.")
        output_specs = [out for out in output_specs if out.name in selected_outputs]
        skipped_sources = {out.source for out in workflow.outputs} - {
            out.source for out in output_specs
        }
    renderer = PromptRenderer(ctx.pack.prompts_dir)
    state: dict[str, Any] = dict(inputs)
    steps = [step for step in workflow.steps if step.id not in skipped_sources]
    no_evidence = False
    for index, step in enumerate(steps):
        if ctx.report_progress:
            label = {
                "scripture": "Checking scripture references",
                "retrieve": "Finding related material",
            }.get(step.type, f"Writing {step.id.replace('_', ' ')}")
            ctx.report_progress(index / (len(steps) + 1), label)
        if not ctx.citations and (
            step.type == "quote" or (workflow.requires_sources and step.type == "generate")
        ):
            state[step.id] = NO_SOURCE_REPLY
            no_evidence = True
        elif step.type == "quote":
            lines, choices = _source_lines(str(state.get("question", "")), ctx.citations)
            output = await _run_step(step, {**state, "source_lines": lines}, ctx, renderer)
            evidence = choices.get(output.strip().upper())
            if evidence is None:
                ctx.citations.clear()
                state[step.id] = (
                    "I couldn’t find an answer to that question in the office documents."
                )
                no_evidence = True
            else:
                quote, hit = evidence
                ctx.citations[:] = [hit]
                state[step.id] = f"{quote} [1]"
        else:
            state[step.id] = await _run_step(step, state, ctx, renderer)

    if ctx.report_progress:
        ctx.report_progress(len(steps) / (len(steps) + 1), "Saving generated texts")
    outputs: dict[str, Any] = {}
    files: list[Path] = []
    run_id = uuid4().hex
    for out in output_specs:
        value = state.get(out.source)
        outputs[out.name] = value
        if ctx.outputs_dir and isinstance(value, str) and not no_evidence:
            base = ctx.outputs_dir / workflow.id / run_id / out.name
            if out.type == "docx":
                tpl = ctx.pack.templates_dir / out.template if out.template else None
                files.append(write_docx(value, base.with_suffix(".docx"), tpl))
            elif out.type == "markdown":
                files.append(write_markdown(value, base.with_suffix(".md")))
    return RunResult(
        id=run_id,
        state=state,
        outputs=outputs,
        citations=ctx.citations,
        files=files,
        no_evidence=no_evidence,
    )
