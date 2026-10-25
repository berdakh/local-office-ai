"""Verify scripture references against a local public-domain Bible text.

The data file is produced by scripts/fetch_bible.py and looks like:
{"version": "WEB", "books": {"Genesis": {"1": {"1": "In the beginning..."}}}}
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .scripture import ScriptureRef, find_scripture_refs

Status = str  # "verified" | "not_found" | "unverified"


@dataclass
class ScriptureCheck:
    ref: str
    book: str
    chapter: int
    verse: int | None
    verse_end: int | None
    status: Status
    text: str | None = None
    note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class Bible:
    def __init__(self, books: dict[str, dict[str, dict[str, str]]], version: str = "WEB"):
        self.books = books
        self.version = version

    @classmethod
    def load(cls, path: Path) -> Bible | None:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data["books"], data.get("version", "WEB"))

    def chapter(self, book: str, chapter: int) -> dict[str, str] | None:
        return self.books.get(book, {}).get(str(chapter))

    def verse(self, book: str, chapter: int, verse: int) -> str | None:
        ch = self.chapter(book, chapter)
        return ch.get(str(verse)) if ch else None

    def check(self, ref: ScriptureRef) -> ScriptureCheck:
        base = dict(
            ref=str(ref),
            book=ref.book,
            chapter=ref.chapter,
            verse=ref.verse,
            verse_end=ref.verse_end,
        )
        if ref.book not in self.books:
            return ScriptureCheck(**base, status="not_found", note="unknown book")
        ch = self.chapter(ref.book, ref.chapter)
        if ch is None:
            return ScriptureCheck(**base, status="not_found", note="no such chapter")
        if ref.verse is None:
            return ScriptureCheck(**base, status="verified", note=f"{len(ch)} verses")
        end = ref.verse_end or ref.verse
        if end < ref.verse:
            return ScriptureCheck(**base, status="not_found", note="verse range is backwards")
        parts = []
        for v in range(ref.verse, end + 1):
            text = ch.get(str(v))
            if text is None:
                return ScriptureCheck(**base, status="not_found", note=f"no verse {v}")
            parts.append(f"{v} {text}" if end > ref.verse else text)
        return ScriptureCheck(**base, status="verified", text=" ".join(parts))


def check_text(text: str, bible: Bible | None) -> list[ScriptureCheck]:
    refs = find_scripture_refs(text)
    if bible is None:
        return [
            ScriptureCheck(
                ref=str(r),
                book=r.book,
                chapter=r.chapter,
                verse=r.verse,
                verse_end=r.verse_end,
                status="unverified",
                note="no Bible text installed",
            )
            for r in refs
        ]
    return [bible.check(r) for r in refs]


def format_checks(checks: list[ScriptureCheck], version: str = "WEB") -> str:
    """Prompt-ready block: verified passages with text, others flagged."""
    lines = []
    for c in checks:
        if c.status == "verified" and c.text:
            lines.append(f"- {c.ref} ({version}): {c.text.strip()}")
        elif c.status == "verified":
            lines.append(f"- {c.ref} (chapter referenced; {c.note})")
        elif c.status == "not_found":
            lines.append(f"- {c.ref}: NOT FOUND ({c.note}); likely a transcription error")
        else:
            lines.append(f"- {c.ref}: unverified")
    return "\n".join(lines)
