"""Write light Markdown (headings, bullets, paragraphs) into a .docx, optionally on a template."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

import docx
from docx.document import Document

_NUMBERED = re.compile(r"^\s*\d+[.)]\s+")


def _build_docx(text: str, template: Path | None) -> Document:
    doc = docx.Document(str(template)) if template and template.exists() else docx.Document()
    # A template may carry an empty body paragraph; drop it so output starts clean.
    for para in list(doc.paragraphs):
        if not para.text.strip():
            para._element.getparent().remove(para._element)
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            doc.add_heading(line[4:], level=3)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        elif line.lstrip().startswith(("- ", "* ")):
            doc.add_paragraph(line.lstrip()[2:], style="List Bullet")
        elif _NUMBERED.match(line):
            doc.add_paragraph(_NUMBERED.sub("", line), style="List Number")
        else:
            doc.add_paragraph(line)
    return doc


def docx_bytes(text: str, template: Path | None = None) -> bytes:
    buffer = BytesIO()
    _build_docx(text, template).save(buffer)
    return buffer.getvalue()


def write_docx(text: str, path: Path, template: Path | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _build_docx(text, template).save(str(path))
    return path
