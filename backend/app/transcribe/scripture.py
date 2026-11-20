"""Find and normalize written and transcribed scripture references."""

from __future__ import annotations

import re
from dataclasses import dataclass

BOOKS = [
    "Genesis",
    "Exodus",
    "Leviticus",
    "Numbers",
    "Deuteronomy",
    "Joshua",
    "Judges",
    "Ruth",
    "1 Samuel",
    "2 Samuel",
    "1 Kings",
    "2 Kings",
    "1 Chronicles",
    "2 Chronicles",
    "Ezra",
    "Nehemiah",
    "Esther",
    "Job",
    "Psalms",
    "Psalm",
    "Proverbs",
    "Ecclesiastes",
    "Song of Solomon",
    "Song of Songs",
    "Isaiah",
    "Jeremiah",
    "Lamentations",
    "Ezekiel",
    "Daniel",
    "Hosea",
    "Joel",
    "Amos",
    "Obadiah",
    "Jonah",
    "Micah",
    "Nahum",
    "Habakkuk",
    "Zephaniah",
    "Haggai",
    "Zechariah",
    "Malachi",
    "Matthew",
    "Mark",
    "Luke",
    "John",
    "Acts",
    "Romans",
    "1 Corinthians",
    "2 Corinthians",
    "Galatians",
    "Ephesians",
    "Philippians",
    "Colossians",
    "1 Thessalonians",
    "2 Thessalonians",
    "1 Timothy",
    "2 Timothy",
    "Titus",
    "Philemon",
    "Hebrews",
    "James",
    "1 Peter",
    "2 Peter",
    "1 John",
    "2 John",
    "3 John",
    "Jude",
    "Revelation",
]

_ORDINALS = {"1": "First", "2": "Second", "3": "Third"}
_SPOKEN_BOOKS = {f"{_ORDINALS[book[0]]}{book[1:]}": book for book in BOOKS if book[0] in _ORDINALS}
# Longest names first so "First John" wins over "John".
_BOOK_NAMES = sorted([*BOOKS, *_SPOKEN_BOOKS], key=len, reverse=True)
_BOOK_ALT = "|".join(re.escape(book) for book in _BOOK_NAMES)
_REF = re.compile(
    rf"\b(?P<book>{_BOOK_ALT})\s+(?:chapter[ \t]+)?(?P<chapter>\d{{1,3}})"
    rf"(?:(?:[ \t]*[:,][ \t]*|[ \t]+)(?:verses?[ \t]+)?(?P<verse>\d{{1,3}})"
    rf"(?:\s*[-–]\s*(?P<verse_end>\d{{1,3}}))?)?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ScriptureRef:
    book: str
    chapter: int
    verse: int | None = None
    verse_end: int | None = None

    def __str__(self) -> str:
        s = f"{self.book} {self.chapter}"
        if self.verse is not None:
            s += f":{self.verse}"
            if self.verse_end is not None:
                s += f"-{self.verse_end}"
        return s


ALIASES = {"Psalm": "Psalms", "Song of Songs": "Song of Solomon"}
_CANONICAL_BOOK = {book.lower(): ALIASES.get(book, book) for book in BOOKS}
_CANONICAL_BOOK.update({spoken.lower(): book for spoken, book in _SPOKEN_BOOKS.items()})


def find_scripture_refs(text: str) -> list[ScriptureRef]:
    refs: list[ScriptureRef] = []
    seen: set[ScriptureRef] = set()
    for m in _REF.finditer(text):
        ref = ScriptureRef(
            book=_CANONICAL_BOOK[m.group("book").lower()],
            chapter=int(m.group("chapter")),
            verse=int(m.group("verse")) if m.group("verse") else None,
            verse_end=int(m.group("verse_end")) if m.group("verse_end") else None,
        )
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs
