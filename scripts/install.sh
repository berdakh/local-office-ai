#!/usr/bin/env bash
# Prepare once online, then install from the staged assets on the same machine.
set -euo pipefail
cd "$(dirname "$0")/.."

mode="${1:---prepare}"
if [[ "$#" -gt 1 || ( "$mode" != "--prepare" && "$mode" != "--offline" ) ]]; then
  echo "Usage: scripts/install.sh [--prepare|--offline]" >&2
  exit 2
fi
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.pilot-cache/uv}"
export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
if [[ "$mode" == "--prepare" ]]; then
  command -v npm >/dev/null || { echo "Install Node.js with npm before preparing." >&2; exit 1; }
  uv sync --locked --extra transcribe --no-dev --reinstall
  (cd frontend && npm ci && npm run build)
  .venv/bin/python scripts/pilot_setup.py prepare
else
  uv sync --offline --locked --extra transcribe --no-dev --no-python-downloads
  .venv/bin/python scripts/pilot_setup.py check
fi
echo "Start with desktop/launcher/start.sh"
