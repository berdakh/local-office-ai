"""Download the World English Bible (public domain) and convert it to the pack's data format.

Source: the `world-english-bible` npm package, a versioned, immutable tarball of
per-book JSON. Output: packs/<pack>/data/web.json as
{"version": "WEB", "source": ..., "books": {"Genesis": {"1": {"1": "text"}}}}.

Usage: uv run python scripts/fetch_bible.py [--pack church] [--out path]
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = "https://registry.npmjs.org/world-english-bible/-/world-english-bible-1.0.1.tgz"

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
    "Proverbs",
    "Ecclesiastes",
    "Song of Solomon",
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
_WS = re.compile(r"\s+")


def download(url: str) -> bytes:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 - fixed https URL
        return r.read()


def convert(tgz: bytes) -> dict:
    books: dict[str, dict[str, dict[str, str]]] = {}
    with tarfile.open(fileobj=io.BytesIO(tgz), mode="r:gz") as tar:
        members = {Path(m.name).name: m for m in tar.getmembers() if m.name.endswith(".json")}
        for book in BOOKS:
            fname = re.sub(r"\s+", "", book).lower() + ".json"
            member = members.get(fname)
            if member is None:
                raise SystemExit(f"Book file missing in archive: {fname}")
            data = json.load(tar.extractfile(member))
            chapters: dict[str, dict[str, list[str]]] = {}
            for entry in data:
                if entry.get("type") not in {"paragraph text", "line text"}:
                    continue
                ch = str(entry["chapterNumber"])
                v = str(entry["verseNumber"])
                chapters.setdefault(ch, {}).setdefault(v, []).append(entry["value"])
            books[book] = {
                ch: {v: _WS.sub(" ", " ".join(parts)).strip() for v, parts in verses.items()}
                for ch, verses in chapters.items()
            }
    return {"version": "WEB", "source": SOURCE, "books": books}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default=os.environ.get("LOA_PACK", "church"))
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--from-file", type=Path, default=None, help="use a downloaded .tgz")
    args = ap.parse_args()
    out = args.out or REPO / "packs" / args.pack / "data" / "web.json"

    tgz = args.from_file.read_bytes() if args.from_file else download(SOURCE)
    data = convert(tgz)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    verses = sum(len(v) for b in data["books"].values() for v in b.values())
    print(f"Wrote {out} ({len(data['books'])} books, {verses} verses)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
