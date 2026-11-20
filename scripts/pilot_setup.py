"""Stage assets online, then check or launch the prepared single-machine pilot."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Timer

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fetch_bible import SOURCE, convert, download  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.llm.ollama import model_tag  # noqa: E402
from app.render.letterhead import build_letterhead  # noqa: E402
from app.transcribe import Bible  # noqa: E402
from app.transcribe.whisper import model_files_present, transcription_available  # noqa: E402


def local_models(client: httpx.Client) -> set[str]:
    response = client.get("/api/tags")
    response.raise_for_status()
    return {
        model_tag(item["name"])
        for item in response.json().get("models", [])
        if not item.get("remote_host")
    }


@contextmanager
def local_ollama(s: Settings) -> Iterator[httpx.Client]:
    env = {**os.environ, "OLLAMA_HOST": s.ollama_url, "OLLAMA_NO_CLOUD": "1"}
    server = None
    with httpx.Client(base_url=s.ollama_url, timeout=2, trust_env=False) as client:
        try:
            try:
                local_models(client)
            except httpx.TransportError:
                server = subprocess.Popen(["ollama", "serve"], env=env)
                for _ in range(40):
                    try:
                        local_models(client)
                    except httpx.TransportError:
                        if server.poll() is not None:
                            break
                        time.sleep(0.25)
                    else:
                        break
                else:
                    raise RuntimeError("Ollama did not become ready. Check the local service.")
                local_models(client)
            yield client
        finally:
            if server is not None and server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


def prepare(s: Settings, client: httpx.Client) -> None:
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from faster_whisper.utils import download_model

    models = local_models(client)
    for model in (s.chat_model, s.embed_model):
        if model_tag(model) not in models:
            subprocess.run(
                ["ollama", "pull", model],
                env={**os.environ, "OLLAMA_HOST": s.ollama_url},
                check=True,
            )
    if not model_files_present(s.whisper_model_path):
        # Use the Hub cache, then materialize the snapshot as a standalone directory.
        # faster-whisper 1.2.1's output_dir branch uses a removed Hub argument.
        model_cache = s.whisper_model_path.parent / ".hub-downloads"
        snapshot = download_model(s.whisper_model, cache_dir=str(model_cache))
        shutil.copytree(snapshot, s.whisper_model_path, dirs_exist_ok=True)
    if not s.bible_path.exists():
        bible = convert(download(SOURCE))
        s.bible_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = s.bible_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(bible, ensure_ascii=False), encoding="utf-8")
        tmp.replace(s.bible_path)
    if not s.letterhead_path.exists():
        build_letterhead(s.letterhead_path, os.environ.get("LOA_CHURCH_NAME", "Church Office"))


def check(s: Settings, client: httpx.Client) -> None:
    expected = {model_tag(name) for name in (s.chat_model, s.embed_model)}
    missing = [f"Ollama model {name}" for name in sorted(expected - local_models(client))]
    for description, present in (
        ("Whisper package or model", transcription_available(s.whisper_model_path)),
        ("World English Bible", Bible.load(s.bible_path) is not None),
        ("Word letterhead", s.letterhead_path.is_file()),
        ("built frontend", (s.frontend_dist / "index.html").is_file()),
    ):
        if not present:
            missing.append(description)
    if missing:
        raise RuntimeError(
            "Missing " + ", ".join(missing) + ". Run the online preparation step once."
        )
    s.ensure_dirs()
    print(f"Pilot ready. Chat: {s.chat_model}. Transcription: {s.whisper_model}.", flush=True)


def reopen(s: Settings) -> bool:
    port = os.environ.get("LOA_PORT", "8000")
    url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(timeout=1, trust_env=False) as client:
            response = client.get(f"{url}/api/health")
            response.raise_for_status()
            folder = response.json().get("data_dir")
            if not folder or Path(folder).resolve() != s.data_dir.resolve():
                return False
    except (httpx.HTTPError, ValueError):
        return False
    print(f"Local Office AI is already running at {url}", flush=True)
    if os.environ.get("LOA_NO_BROWSER") != "1":
        webbrowser.open(url)
    return True


def launch() -> int:
    port = os.environ.get("LOA_PORT", "8000")
    url = f"http://127.0.0.1:{port}"
    print(f"Local Office AI at {url}", flush=True)
    if os.environ.get("LOA_NO_BROWSER") != "1":
        opener = Timer(1.5, webbrowser.open, args=(url,))
        opener.daemon = True
        opener.start()
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", "backend"]
    return subprocess.call([*cmd, "--host", "127.0.0.1", "--port", port])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "check", "launch"])
    args = parser.parse_args()
    os.chdir(ROOT)
    try:
        s = get_settings()
        if args.action == "launch" and reopen(s):
            return 0
        with local_ollama(s) as client:
            if args.action == "prepare":
                prepare(s, client)
            check(s, client)
            return launch() if args.action == "launch" else 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, httpx.HTTPError) as exc:
        print(f"Pilot setup: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
