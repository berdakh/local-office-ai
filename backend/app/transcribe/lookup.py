"""Local passage lookup and verse ranking over the installed Bible."""

from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache
from math import log

from .bible import Bible
from .scripture import ScriptureRef, find_scripture_refs

_WORD = re.compile(r"[a-z0-9]+")
_STOP = set(
    "a about after all an and are at bible can chapter christian christians could did do does "
    "find for from give had has have how i in is it me of on or please say scripture show "
    "tell text that the their them this to use verse verses was were what when where which who "
    "why will with would you your".split()
)
_TOPICS = {
    "anxiety|anxious|worry|worried": ("Matthew 6:25-34", "Philippians 4:6-7", "1 Peter 5:7"),
    "baptism|baptize|baptized|baptise": ("Matthew 28:19-20", "Acts 2:38-39", "Romans 6:3-4"),
    "forgive|forgiveness|forgiving": ("Matthew 18:21-22", "Ephesians 4:32", "Colossians 3:13"),
    "grief|grieving|mourning|loss": ("Matthew 5:4", "John 11:32-36", "Revelation 21:4"),
    "communion|eucharist|lord s supper": ("Luke 22:19-20", "1 Corinthians 11:23-26"),
    "prayer|pray|praying": ("Matthew 6:9-13", "Philippians 4:6-7"),
    "neighbor|neighbour|neighbors|neighbours": ("Luke 10:25-37", "Mark 12:28-31"),
}


def words(text: str) -> list[str]:
    return _WORD.findall(text.casefold())


@lru_cache(maxsize=2)
def _index(bible: Bible) -> tuple[list[dict[str, str]], list[str], dict[str, list[int]]]:
    passages = []
    normalized = []
    inverted: dict[str, list[int]] = defaultdict(list)
    for book, chapters in bible.books.items():
        for chapter, verses in chapters.items():
            for verse, text in verses.items():
                if not chapter.isdigit() or not verse.isdigit() or not text.strip():
                    continue
                tokens = words(text)
                for word in set(tokens) - _STOP:
                    inverted[word].append(len(passages))
                normalized.append(" ".join(tokens))
                passages.append({"ref": f"{book} {chapter}:{verse}", "text": text})
    return passages, normalized, inverted


def _exact(bible: Bible, ref: ScriptureRef) -> dict[str, str] | None:
    check = bible.check(ref)
    if check.status != "verified":
        return None
    if check.text:
        return {"ref": check.ref, "text": check.text}
    verses = bible.chapter(ref.book, ref.chapter) or {}
    lines = [f"{n} {verses[n]}" for n in sorted(filter(str.isdigit, verses), key=int)]
    return {"ref": check.ref, "text": "\n".join(lines)}


def lookup(
    bible: Bible, query: str, limit: int = 8, *, topics: bool = False
) -> list[dict[str, str]]:
    references = find_scripture_refs(query)
    if references:
        exact = (_exact(bible, ref) for ref in references[:limit])
        return [passage for passage in exact if passage]

    tokens = words(query)
    phrase = " ".join(tokens)
    matches: dict[str, dict[str, str]] = {}
    if topics:
        for aliases, references in _TOPICS.items():
            if not re.search(rf"\b(?:{aliases})\b", phrase):
                continue
            for reference in references:
                if passage := _exact(bible, find_scripture_refs(reference)[0]):
                    matches[passage["ref"]] = passage
    if len(matches) >= limit:
        return list(matches.values())[:limit]

    terms = set(tokens) - _STOP
    if not terms:
        return list(matches.values())

    passages, normalized, inverted = _index(bible)
    terms = terms & inverted.keys()
    scores: dict[int, float] = defaultdict(float)
    overlaps: dict[int, int] = defaultdict(int)
    for word in terms:
        locations = inverted[word]
        weight = log(1 + len(passages) / len(locations))
        for index in locations:
            scores[index] += weight
            overlaps[index] += 1
    results = sorted(
        (index for index in scores if overlaps[index] >= min(2, len(terms))),
        key=lambda index: (
            len(tokens) > 1 and f" {phrase} " in f" {normalized[index]} ",
            overlaps[index],
            scores[index],
            -index,
        ),
        reverse=True,
    )
    for index in results:
        passage = passages[index]
        matches.setdefault(passage["ref"], passage)
        if len(matches) == limit:
            break
    return list(matches.values())
