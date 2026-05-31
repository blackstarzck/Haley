$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[1/3] Creating local Python environment..."
    python -m venv .venv
}

Write-Host "[2/3] Installing project dependencies..."
& $VenvPython -m pip install --disable-pip-version-check --quiet -e .

Write-Host "[3/3] Starting Haley PAPER console..."
Write-Host ""
Write-Host "Open: http://127.0.0.1:8000/console"
Write-Host "Stop: Ctrl + C"
Write-Host ""

& $VenvPython -m haley.api.local_server
