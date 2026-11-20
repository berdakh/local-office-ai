# Local Office AI

A free, fully offline AI assistant for small offices. Nothing leaves the
machine after install. The first vertical is a church office pilot; later
verticals (law, CPA, HOA management) are added as **packs** of prompts,
templates and YAML workflows, not as application code.

**Working name.** Rename the repo, the `LOA_` env prefix and the data folder
once the LLC has a brand.

[Follow the illustrated quick start for church office teams](docs/quick-start.md).

## What it does (church pack)

| Feature | What the user does | What comes out |
|---|---|---|
| Sermon Studio | Drops in Sunday's recording | Local transcript, scripture references verified against the World English Bible, summary, key points, discussion guide, blog draft, social posts, bulletin blurb |
| Announcement Hub | Pastes the week's messy announcements | Bulletin blurb, newsletter section, email, social post, slide text |
| Ask the Office | Asks a question | Answer with file and page citations from the church's own documents |
| Letter Drafter | Picks a template, fills fields | A Word letter on the church letterhead |

Principles: local only, human approves everything, citations or nothing,
workflows over chat, vertical content is configuration.

## Stack

Python 3.11+ / FastAPI backend, SQLite, BM25 + local embeddings for hybrid
search, [Ollama](https://ollama.com) for inference and embeddings,
faster-whisper for transcription, React + Vite frontend served by the backend.

## Single-machine pilot install

Install Python 3.11+, uv, Node.js with npm, and Ollama before staging. On the
pilot machine, copy `.env.example` to `.env` and set the desired model names.
The pilot uses a loopback Ollama service. A lighter chat option is
`LOA_CHAT_MODEL=qwen2.5:3b-instruct`.

| Stage | Linux/macOS | Windows (PowerShell) |
|---|---|---|
| Prepare once with internet access | `./scripts/install.sh --prepare` | `./scripts/install.ps1 -Mode Prepare` |
| Install or rebuild the Python environment offline | `./scripts/install.sh --offline` | `./scripts/install.ps1 -Mode Offline` |
| Launch offline | `./desktop/launcher/start.sh` | `./desktop/launcher/start.bat` |

Preparation caches the locked Python packages and Whisper model under
`.pilot-cache/`, builds `frontend/dist/`, saves the Bible and a starter
letterhead into the selected pack, and pulls the configured Ollama models into
the local Ollama store. Keep those staged assets, Ollama, uv, and a compatible
Python interpreter available for offline installation. After preparation, the
launcher uses the installed Python environment directly. Ollama and the app
communicate on the same computer and the app listens on `127.0.0.1` only.

See the [pilot runbook](docs/pilot-runbook.md) for testing with networking off.

The amd64 Debian package targets Pop!_OS 22.04 and opens the workspace
from the desktop application menu. It bundles Python, the frontend, and
the Whisper model. It uses the machine's existing Ollama installation and
the `qwen2.5:3b-instruct` and `nomic-embed-text` models. Build it from a
prepared checkout with `packaging/debian/build.sh /path/to/package.deb`.
The installed app uses `http://127.0.0.1:8765` and saves its data under
`${XDG_DATA_HOME:-$HOME/.local/share}/local-office-ai`.

## Quick start (development)

```bash
# 1. Install Ollama and pull models
ollama pull qwen3:8b
ollama pull nomic-embed-text

# 2. Backend (for audio, stage the Whisper model with the pilot preparation step)
uv sync --all-extras
uv run python scripts/fetch_bible.py                     # public-domain Bible for scripture checks
uv run python scripts/make_letterhead.py --name "Grace Community Church"   # starter letterhead
uv run uvicorn app.main:app --app-dir backend --reload --port 8000

# 3. Frontend (separate terminal)
cd frontend && npm install && npm run dev      # http://localhost:5173, proxies /api to :8000
```

Or with [just](https://github.com/casey/just): `just setup`, `just dev`.

Production-style run: `just build` then `just run` serves the built UI from the
backend at http://localhost:8000.

## Configuration

Environment variables (prefix `LOA_`), or a `.env` file. See `.env.example`.

| Variable | Default | Meaning |
|---|---|---|
| `LOA_DATA_DIR` | `~/LocalOfficeAI` | Database, uploaded files, outputs, logs. Backup = copy this folder. |
| `LOA_PACK` | `church` | Which pack in `packs/` to load |
| `LOA_OLLAMA_URL` | `http://127.0.0.1:11434` | Loopback Ollama endpoint |
| `LOA_CHAT_MODEL` | `qwen3:8b` | Generation model |
| `LOA_CHAT_CONTEXT` | `8192` | Context window in tokens for generation |
| `LOA_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `LOA_WHISPER_MODEL` | `small` | faster-whisper model size |
| `LOA_WHISPER_MODEL_DIR` | unset | Optional existing faster-whisper model directory |
| `LOA_PIN` | empty | Reserved for future authentication |

## Layout

```
backend/app/      FastAPI app: db, llm, ingest, rag, transcribe, workflows, render, jobs, audit, api
frontend/         React + Vite UI
packs/church/     prompts, workflows, templates, sample data for the church vertical
desktop/          launcher scripts now, Tauri shell later
scripts/          install, model pull, offline check, synthetic data
docs/             scope, architecture, pilot runbook, discovery notes
```

## Tests

```bash
uv run pytest
uv run ruff check .
```

Tests never require Ollama or a Whisper model; the LLM and transcriber are stubbed.

## Scripture verification

`scripts/fetch_bible.py` converts the World English Bible into
`packs/church/data/web.json`. Every transcript and every Sermon Studio run
detects references like `1 Corinthians 13:4-7`, looks them up locally, and
hands the exact text to the model with the instruction to quote only from it.
References that do not exist are flagged as probable transcription errors.

## License

Not yet decided. All rights reserved until a license file is added.
