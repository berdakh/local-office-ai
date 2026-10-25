"""Write light Markdown (headings, bullets, paragraphs) into a .docx, optionally on a template."""

from __future__ import annotations

import re
from pathlib import Path

import docx

_NUMBERED = re.compile(r"^\s*\d+[.)]\s+")


def write_docx(text: str, path: Path, template: Path | None = None) -> Path:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path
