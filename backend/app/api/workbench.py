"""Local diagnostics and disposable Python experiments on Linux."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryFile
from threading import Semaphore
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import Settings
from app.llm import OllamaClient

from .deps import get_conn, get_llm, get_settings_dep

router = APIRouter(prefix="/workbench", tags=["workbench"])
_CAPACITY = Semaphore(1)
_PYTHON = Path("/usr/bin/python3")
_BOOTSTRAP = r"""
import json, reprlib, resource, sys
resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
resource.setrlimit(resource.RLIMIT_NPROC, (24, 24))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
marker = sys.argv[1]
workspace = {'__name__': '__main__'}
try:
    exec(compile(sys.stdin.read(), 'experiment.py', 'exec'), workspace)
finally:
    report = []
    primitives = (bool, int, float, str, list, tuple, dict, set, bytes)
    for name, value in list(workspace.items()):
        cls = type(value)
        if name.startswith('_') or cls not in primitives:
            continue
        report.append({'name': name[:80], 'type': cls.__name__, 'value': reprlib.repr(value)[:200]})
        if len(report) >= 24:
            break
    print('\n' + marker + json.dumps(report))
"""


def available() -> bool:
    return platform.system() == "Linux" and _PYTHON.is_file() and bool(shutil.which("bwrap"))


@router.get("/diagnostics")
async def diagnostics(
    conn=Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
    llm: OllamaClient = Depends(get_llm),
):
    return {
        "python_runner": available(),
        "python": platform.python_version(),
        "build": "0.4.0",
        "database": conn.execute("PRAGMA quick_check(1)").fetchone()[0],
        "documents": conn.execute("SELECT count(*) FROM documents").fetchone()[0],
        "job_counts": {
            row["status"]: row["total"]
            for row in conn.execute("SELECT status, count(*) AS total FROM jobs GROUP BY status")
        },
        "ollama_connected": await llm.is_available(),
        "binary_assets": {
            "web": (settings.frontend_dist / "index.html").is_file(),
            "bible": settings.bible_path.is_file(),
            "whisper": (settings.whisper_model_path / "model.bin").is_file(),
        },
    }


class Experiment(BaseModel):
    code: str = Field(min_length=1, max_length=20_000)


@router.post("/python")
def run_experiment(experiment: Experiment):
    if not available():
        raise HTTPException(503, "The Python runner requires Linux and Bubblewrap.")
    if not _CAPACITY.acquire(blocking=False):
        raise HTTPException(409, "An experiment is already running.")
    try:
        with TemporaryFile() as output:
            marker = "LOA_VARIABLES_" + uuid4().hex
            command = [
                "bwrap",
                "--unshare-all",
                "--die-with-parent",
                "--cap-drop",
                "ALL",
                "--clearenv",
                "--setenv",
                "HOME",
                "/tmp",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
                "--ro-bind",
                "/usr/lib",
                "/usr/lib",
                "--ro-bind-try",
                "/lib64",
                "/lib64",
                "--ro-bind",
                "/lib",
                "/lib",
                "--ro-bind",
                str(_PYTHON),
                str(_PYTHON),
                "--chdir",
                "/tmp",
                str(_PYTHON),
                "-I",
                "-B",
                "-c",
                _BOOTSTRAP,
                marker,
            ]
            try:
                result = subprocess.run(
                    command,
                    input=experiment.code.encode(),
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    timeout=7,
                    check=False,
                )
                status = result.returncode
            except subprocess.TimeoutExpired:
                status = 124
            output.seek(0)
            contents = output.read(65_536).decode(errors="replace")
            before, found, after = contents.rpartition(marker)
            variables = []
            if found:
                line, _, tail = after.partition("\n")
                try:
                    candidate = json.loads(line)
                    if isinstance(candidate, list):
                        variables = candidate
                        contents = before.rstrip("\n") + ("\n" + tail if tail else "")
                except ValueError:
                    pass
            return {"exit_code": status, "output": contents, "variables": variables}
    finally:
        _CAPACITY.release()
