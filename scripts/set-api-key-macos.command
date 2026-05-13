#!/bin/zsh
set -e

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  echo "Missing .venv. Run scripts/install-macos.command first."
  read -k 1 "?Press any key to close..."
  exit 1
fi

source .venv/bin/activate
python -m voice_transcription.set_api_key

echo ""
read -k 1 "?Press any key to close..."
