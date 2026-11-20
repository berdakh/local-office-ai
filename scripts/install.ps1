# Prepare once online, then install from the staged assets on the same machine.
param([ValidateSet("Prepare", "Offline")] [string] $Mode = "Prepare")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = Join-Path $PWD ".pilot-cache\uv"
}
$env:UV_PROJECT_ENVIRONMENT = Join-Path $PWD ".venv"
if ($Mode -eq "Prepare") {
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw "Install Node.js with npm before preparing."
    }
    uv sync --locked --extra transcribe --no-dev --reinstall
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Push-Location frontend
    try {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
    & .\.venv\Scripts\python.exe scripts/pilot_setup.py prepare
} else {
    uv sync --offline --locked --extra transcribe --no-dev --no-python-downloads
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .\.venv\Scripts\python.exe scripts/pilot_setup.py check
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Start with desktop\launcher\start.bat"
