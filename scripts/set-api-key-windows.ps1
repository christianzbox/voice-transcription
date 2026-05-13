$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Missing .venv. Run scripts\install-windows.ps1 first."
    Read-Host "Press Enter to close"
    exit 1
}

& ".\.venv\Scripts\python.exe" -m voice_transcription.set_api_key

Write-Host ""
Read-Host "Press Enter to close"
