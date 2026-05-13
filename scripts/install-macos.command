#!/bin/zsh
set -e

cd "$(dirname "$0")/.."

echo "Installing Voice Transcription for macOS..."

if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "Python 3 is required."
  echo "Install Python from https://www.python.org/downloads/macos/ or run:"
  echo "xcode-select --install"
  echo ""
  read -k 1 "?Press any key to close..."
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate

python -m ensurepip --upgrade >/dev/null 2>&1 || true
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo ""
  echo "ffmpeg is required for large audio files."

  if command -v brew >/dev/null 2>&1; then
    echo "Homebrew found. Installing ffmpeg..."
    brew install ffmpeg
  else
    echo ""
    echo "Homebrew is not installed."
    echo "Install Homebrew from https://brew.sh, then run:"
    echo "brew install ffmpeg"
    echo ""
    read -k 1 "?Press any key to close..."
    exit 1
  fi
fi

echo ""
echo "Install complete."
echo "Next: double-click scripts/set-api-key-macos.command"
echo ""
read -k 1 "?Press any key to close..."
