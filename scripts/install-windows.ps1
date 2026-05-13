$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "Installing Voice Transcription for Windows..."

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "Python is required. Install Python from:"
    Write-Host "https://www.python.org/downloads/windows/"
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

python -m venv .venv

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "ffmpeg is required for large audio files."

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "winget found. Installing ffmpeg..."
        winget install Gyan.FFmpeg
    }
    else {
        Write-Host ""
        Write-Host "Install ffmpeg manually:"
        Write-Host "https://ffmpeg.org/download.html"
        Write-Host ""
        Read-Host "Press Enter to close"
        exit 1
    }
}

Write-Host ""
Write-Host "Install complete."
Write-Host "Next: run scripts\set-api-key-windows.ps1"
Write-Host ""
Read-Host "Press Enter to close"
