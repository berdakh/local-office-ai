#!/usr/bin/env bash
# Build the Pop!_OS 22.04 x86-64 package after preparing the local pilot assets.
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"

if [[ $(uname -m) != x86_64 || $(uname -s) != Linux ]]; then
    echo "Build on x86-64 Linux for the amd64 package." >&2
    exit 1
fi

output=$(realpath "${1:-$root/local-office-ai_0.4.0_amd64.deb}")
export UV_CACHE_DIR="${UV_CACHE_DIR:-$root/.pilot-cache/uv}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$root/.pilot-cache/python}"
export UV_PYTHON_BIN_DIR="${UV_PYTHON_BIN_DIR:-$root/.pilot-cache/python-bin}"
model="${LOA_PACKAGE_WHISPER_DIR:-$root/.pilot-cache/whisper/model-tiny.en}"

for asset in "$model/model.bin" "$model/config.json" "$model/tokenizer.json" \
    "$root/packs/church/data/web.json" "$root/packs/church/templates/letterhead.docx"; do
    if [[ ! -s "$asset" ]]; then
        echo "Missing prepared asset: $asset" >&2
        exit 1
    fi
done

scratch=$(mktemp -d "$root/.pilot-cache/debian-build.XXXXXX")
trap 'rm -rf "$scratch"' EXIT
package="$scratch/package"
install_root="$package/opt/local-office-ai"
app="$install_root/app"

uv python install 3.12
python=$(uv python find --managed-python 3.12)
runtime=$(dirname "$(dirname "$python")")
UV_PROJECT_ENVIRONMENT="$scratch/venv" uv sync --locked --extra transcribe --no-dev --python "$python"
(cd frontend && npm ci && npm run build)

mkdir -p "$install_root/runtime" "$app/backend" "$app/frontend" "$app/packs/church" \
    "$app/models/whisper" "$app/scripts" "$package/DEBIAN" "$package/usr/bin"
cp -a "$runtime/." "$install_root/runtime/"
cp -a "$scratch/venv/lib/python3.12/site-packages/." "$install_root/runtime/lib/python3.12/site-packages/"
cp -a backend/app "$app/backend/"
cp -a frontend/dist "$app/frontend/"
cp -a packs/church/{pack.yaml,prompts,workflows,data,templates} "$app/packs/church/"
install -m 644 scripts/{pilot_setup.py,fetch_bible.py} "$app/scripts/"
for asset in config.json model.bin tokenizer.json vocabulary.json vocabulary.txt preprocessor_config.json; do
    if [[ -f "$model/$asset" ]]; then install -m 644 "$model/$asset" "$app/models/whisper/$asset"; fi
done

find "$install_root" -type d -name __pycache__ -prune -exec rm -rf {} +
install -m 755 packaging/debian/start "$install_root/start"
ln -s ../../opt/local-office-ai/start "$package/usr/bin/local-office-ai"
install -Dm644 packaging/debian/local-office-ai.desktop "$package/usr/share/applications/local-office-ai.desktop"
install -Dm644 frontend/src/assets/office-icon.png "$package/usr/share/icons/hicolor/128x128/apps/local-office-ai.png"

cat > "$package/DEBIAN/control" <<CONTROL
Package: local-office-ai
Version: 0.4.0
Architecture: amd64
Section: office
Priority: optional
Maintainer: Local Office AI <local-office-ai@localhost>
Installed-Size: $(du -sk "$package" | cut -f 1)
Depends: libc6 (>= 2.35), libgcc-s1, libstdc++6, libgomp1, xdg-utils
Recommends: bubblewrap, python3
Description: On-device sermon and office drafting workspace
 Runs on localhost and opens in the user's browser. Includes the Python
 runtime, a Whisper speech recognition model and the church workflow pack.
 Uses installed Ollama generation and embedding models.
CONTROL

desktop-file-validate "$package/usr/share/applications/local-office-ai.desktop"
dpkg-deb --root-owner-group -Zzstd -z9 --build "$package" "$scratch/local-office-ai.deb"
install -m 644 "$scratch/local-office-ai.deb" "$output"
