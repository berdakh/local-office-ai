#!/usr/bin/env bash
# Launch from the prepared Python environment without dependency resolution.
set -euo pipefail
cd "$(dirname "$0")/../.."

if [[ ! -x .venv/bin/python ]]; then
  echo "Run scripts/install.sh --offline after provisioning the pilot." >&2
  exit 1
fi
exec .venv/bin/python scripts/pilot_setup.py launch
