"""Describe the local machine and offer a small catalogue of compatible models."""

from __future__ import annotations

import asyncio
import csv
import os
import platform
import shutil
import subprocess
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import Settings
from app.jobs import JobQueue
from app.llm import OllamaClient
from app.llm.ollama import model_tag

from .deps import get_jobs, get_llm, get_settings_dep

router = APIRouter(prefix="/settings/hardware", tags=["settings"])
GIB = 1024**3
CATALOGUE = [
    ("qwen2.5:1.5b", "Lightweight", 1.0, 4, 0),
    ("qwen2.5:3b-instruct", "Everyday", 1.9, 8, 4),
    ("qwen2.5:7b-instruct", "Higher quality", 4.7, 16, 8),
    ("qwen2.5:14b", "Largest", 9.0, 32, 14),
]


def _command(*args: str) -> str:
    try:
        return subprocess.check_output(
            args, text=True, stderr=subprocess.DEVNULL, timeout=2
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _ram() -> float | None:
    if platform.system() == "Darwin":
        value = _command("sysctl", "-n", "hw.memsize")
        return int(value) / GIB if value.isdigit() else None
    if platform.system() == "Windows":
        value = _command(
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
        )
        return int(value) / GIB if value.isdigit() else None
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / GIB
    except (OSError, ValueError):
        return None


def _gpus() -> list[dict]:
    devices = []
    output = _command(
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    )
    for name, memory, driver in csv.reader(output.splitlines(), skipinitialspace=True):
        if memory.isdigit():
            major = driver.split(".", 1)[0]
            devices.append(
                {
                    "name": name,
                    "vram_gib": round(int(memory) / 1024, 1),
                    "candidate": major.isdigit() and int(major) >= 550,
                }
            )
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return [{"name": "Apple silicon", "vram_gib": None, "candidate": True}]
    devices_seen = {
        "0x10de": "NVIDIA graphics",
        "0x1002": "AMD Radeon graphics",
        "0x8086": "Intel graphics",
    }
    for node in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
        device = node / "device"
        vendor = _read(device / "vendor")
        if vendor not in devices_seen or (vendor == "0x10de" and output):
            continue
        memory = _read(device / "mem_info_vram_total")
        vram = round(int(memory) / GIB, 1) if memory.isdigit() else None
        driver = (device / "driver").resolve().name
        devices.append(
            {
                "name": devices_seen[vendor],
                "vram_gib": vram,
                "candidate": vendor == "0x1002" and driver == "amdgpu" and vram is not None,
            }
        )
    return devices


def inspect_hardware(path: Path) -> dict:
    name = next(
        (
            line.partition(":")[2].strip()
            for line in _read(Path("/proc/cpuinfo")).splitlines()
            if line.startswith("model name")
        ),
        platform.processor() or platform.machine(),
    )
    ram = _ram()
    gpus = _gpus()
    gpu_ram = max((gpu["vram_gib"] or 0 for gpu in gpus if gpu["candidate"]), default=0)
    if platform.system() == "Darwin" and platform.machine() == "arm64" and ram:
        gpu_ram = max(0, ram - 6)
    free = shutil.disk_usage(path).free / 1_000_000_000
    models = []
    for tag, label, size, memory, vram in CATALOGUE:
        if ram is None or ram < memory - 0.6:
            continue
        gpu_fit = bool(vram and gpu_ram >= vram)
        models.append(
            {
                "tag": tag,
                "label": label,
                "download_gb": size,
                "gpu_candidate": gpu_fit,
            }
        )
    accelerated = [model for model in models if model["gpu_candidate"]]
    if accelerated:
        recommended = accelerated[-1]["tag"]
    else:
        everyday = [model for model in models if model["download_gb"] <= 1.9]
        recommended = everyday[-1]["tag"] if everyday else None
    return {
        "os": f"{platform.system()} · {platform.machine()}",
        "cpu": name,
        "threads": os.cpu_count(),
        "ram_gib": round(ram, 1) if ram else None,
        "free_gb": round(free, 1),
        "gpus": gpus,
        "models": models,
        "recommended": recommended,
    }


@router.get("")
async def hardware(
    settings: Settings = Depends(get_settings_dep), llm: OllamaClient = Depends(get_llm)
):
    specs, installed, running = await asyncio.gather(
        asyncio.to_thread(inspect_hardware, settings.data_dir),
        llm.list_models(),
        llm.running_models(),
    )
    tags = {model_tag(tag) for tag in installed}
    for entry in specs["models"]:
        entry["installed"] = model_tag(entry["tag"]) in tags
    return {**specs, "running": running}


class PullRequest(BaseModel):
    model: str


@router.post("/download")
async def download(
    req: PullRequest,
    settings: Settings = Depends(get_settings_dep),
    llm: OllamaClient = Depends(get_llm),
    jobs: JobQueue = Depends(get_jobs),
):
    if not await llm.is_available():
        raise HTTPException(503, "Start the local Ollama service before downloading a model.")
    specs = await asyncio.to_thread(inspect_hardware, settings.data_dir)
    model = next((entry for entry in specs["models"] if entry["tag"] == req.model), None)
    if model is None:
        raise HTTPException(400, "Choose a model recommended for the detected hardware.")
    if any(model_tag(tag) == model_tag(req.model) for tag in await llm.list_models()):
        return {"job_id": None, "installed": True}
    if specs["free_gb"] < model["download_gb"] + 1:
        raise HTTPException(409, "Free more disk space before downloading this model.")
    if any(
        job["kind"] == "model_download" and job["status"] in {"running", "queued"}
        for job in jobs.list()
    ):
        raise HTTPException(409, "A model download is already running.")

    async def job(progress):
        try:
            await llm.pull_model(req.model, progress)
        except httpx.HTTPError as exc:
            raise RuntimeError(
                "Ollama could not download the model. Check its internet connection."
            ) from exc
        return {"model": req.model}

    return {
        "job_id": jobs.submit(
            "model_download", job, label=f"Downloading {req.model}", route="/settings"
        ),
        "installed": False,
    }
