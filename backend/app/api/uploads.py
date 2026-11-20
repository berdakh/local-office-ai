"""Keep each original in its own directory while preserving its display filename."""

import re
import shutil
from pathlib import Path
from tempfile import mkdtemp

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool


def upload_name(filename: str | None, fallback: str) -> str:
    basename = (filename or fallback).replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9._-]+", "_", basename) or fallback


def _save_upload(file: UploadFile, root: Path, name: str) -> Path:
    folder = Path(mkdtemp(dir=root))
    # Use a fixed basename on disk, including on Windows where names like CON are reserved.
    path = folder / f"original{Path(name).suffix.lower()}"
    try:
        with path.open("xb") as dest:
            shutil.copyfileobj(file.file, dest)
    except BaseException:
        shutil.rmtree(folder)
        raise
    return path


async def save_upload(file: UploadFile, root: Path, name: str) -> Path:
    return await run_in_threadpool(_save_upload, file, root, name)
