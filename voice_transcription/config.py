from pathlib import Path
import os

APP_NAME = "voice-transcription"
KEYRING_SERVICE = "voice-transcription"
KEYRING_USERNAME = "openai-api-key"

BASE_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = BASE_DIR / "input"
RUNS_DIR = BASE_DIR / "runs"


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}

AUDIO_EXTENSIONS = {
    ".m4a",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".wav",
    ".webm",
    ".ogg",
    ".flac",
}

# Audio chunking.
#
# For huge files, we split locally with ffmpeg before upload.
# Overlap reduces context loss around chunk boundaries.
CHUNK_SECONDS = int(os.environ.get("VOICE_TRANSCRIPTION_CHUNK_SECONDS", "600"))
CHUNK_OVERLAP_SECONDS = int(os.environ.get("VOICE_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS", "45"))

AUDIO_BITRATE = os.environ.get("VOICE_TRANSCRIPTION_AUDIO_BITRATE", "48k")
AUDIO_SAMPLE_RATE = os.environ.get("VOICE_TRANSCRIPTION_AUDIO_SAMPLE_RATE", "24000")

MAX_UPLOAD_MB = int(os.environ.get("VOICE_TRANSCRIPTION_MAX_UPLOAD_MB", "24"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

TRANSCRIBE_MODEL = os.environ.get("VOICE_TRANSCRIPTION_TRANSCRIBE_MODEL", "gpt-4o-transcribe-diarize")
NOTES_MODEL = os.environ.get("VOICE_TRANSCRIPTION_NOTES_MODEL", "gpt-5.5")
INTERACTIVE_SPEAKER_NAMING = _env_bool("VOICE_TRANSCRIPTION_INTERACTIVE_SPEAKER_NAMING", True)
