import shutil
import subprocess
import sys
from pathlib import Path

from .config import (
    AUDIO_BITRATE,
    AUDIO_EXTENSIONS,
    AUDIO_SAMPLE_RATE,
    CHUNK_OVERLAP_SECONDS,
    CHUNK_SECONDS,
    MAX_UPLOAD_BYTES,
)


def require_ffmpeg() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        print("")
        print("Missing required audio tools:", ", ".join(missing))
        print("")
        print("macOS:")
        print("  brew install ffmpeg")
        print("")
        print("Windows:")
        print("  winget install Gyan.FFmpeg")
        print("")
        sys.exit(1)


def run_command(args: list[str], *, capture: bool = False) -> str:
    if capture:
        result = subprocess.run(args, text=True, capture_output=True)
    else:
        result = subprocess.run(args)

    if result.returncode != 0:
        if capture and result.stderr:
            print(result.stderr)
        raise RuntimeError(f"Command failed: {' '.join(map(str, args))}")

    return result.stdout.strip() if capture else ""


def get_duration_seconds(path: Path) -> float:
    try:
        output = run_command(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture=True,
        )
        return float(output)
    except Exception:
        return 0.0


def format_ts(seconds: float) -> str:
    try:
        seconds = int(round(float(seconds)))
    except Exception:
        seconds = 0

    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    return f"{h:02d}:{m:02d}:{s:02d}"


def is_audio_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS


def _validate_chunk_settings() -> None:
    if CHUNK_SECONDS <= 0:
        print("VOICE_TRANSCRIPTION_CHUNK_SECONDS must be greater than 0.")
        sys.exit(1)

    if CHUNK_OVERLAP_SECONDS < 0:
        print("VOICE_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS must be 0 or greater.")
        sys.exit(1)

    if CHUNK_OVERLAP_SECONDS >= CHUNK_SECONDS:
        print("VOICE_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS must be less than VOICE_TRANSCRIPTION_CHUNK_SECONDS.")
        sys.exit(1)


def _chunk_windows(total_duration: float) -> list[tuple[float, float]]:
    """
    Returns (start_seconds, duration_seconds) windows.

    Example with 10-minute chunks and 45-second overlap:
    - chunk 1: 00:00-10:00
    - chunk 2: 09:15-19:15
    - chunk 3: 18:30-28:30

    The overlap intentionally duplicates a little audio so that context around
    boundaries is preserved. Later summarization is instructed to treat overlap
    as context and avoid duplicate action items.
    """
    if total_duration <= 0:
        return [(0.0, float(CHUNK_SECONDS))]

    stride = CHUNK_SECONDS - CHUNK_OVERLAP_SECONDS
    windows: list[tuple[float, float]] = []

    start = 0.0
    while start < total_duration:
        remaining = total_duration - start
        duration = min(float(CHUNK_SECONDS), remaining)
        windows.append((start, duration))

        if start + duration >= total_duration:
            break

        start += stride

    return windows


def make_chunks(audio_path: Path, run_dir: Path) -> list[dict]:
    require_ffmpeg()
    _validate_chunk_settings()

    chunks_dir = run_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    total_duration = get_duration_seconds(audio_path)
    windows = _chunk_windows(total_duration)

    print("")
    print("Preparing audio chunks...")
    print(f"Chunk length: {CHUNK_SECONDS} seconds")
    print(f"Chunk overlap: {CHUNK_OVERLAP_SECONDS} seconds")
    print(f"Bitrate: {AUDIO_BITRATE}")
    print(f"Sample rate: {AUDIO_SAMPLE_RATE}")
    if total_duration:
        print(f"Detected duration: {format_ts(total_duration)}")
    print("")

    chunks: list[dict] = []

    for index, (start_seconds, duration_seconds) in enumerate(windows):
        chunk_path = chunks_dir / f"chunk_{index:03d}.m4a"

        # We intentionally re-encode each chunk because:
        # 1. it keeps file sizes safely below upload limits,
        # 2. it works for most source formats,
        # 3. it allows overlapping chunk windows.
        run_command(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-ss",
                str(start_seconds),
                "-t",
                str(duration_seconds),
                "-i",
                str(audio_path),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(AUDIO_SAMPLE_RATE),
                "-b:a",
                AUDIO_BITRATE,
                str(chunk_path),
            ]
        )

        size = chunk_path.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            print("")
            print(f"{chunk_path.name} is still too large: {size / (1024 * 1024):.1f} MB")
            print("")
            print("Try smaller chunks or lower bitrate:")
            print("macOS/Linux:")
            print(
                "  VOICE_TRANSCRIPTION_CHUNK_SECONDS=300 VOICE_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS=30 VOICE_TRANSCRIPTION_AUDIO_BITRATE=32k python -m voice_transcription"
            )
            print("")
            print("Windows PowerShell:")
            print(
                '  $env:VOICE_TRANSCRIPTION_CHUNK_SECONDS="300"; $env:VOICE_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS="30"; $env:VOICE_TRANSCRIPTION_AUDIO_BITRATE="32k"; python -m voice_transcription'
            )
            sys.exit(1)

        chunks.append(
            {
                "path": chunk_path,
                "index": index,
                "start_seconds": start_seconds,
                "duration_seconds": get_duration_seconds(chunk_path) or duration_seconds,
                "requested_duration_seconds": duration_seconds,
                "is_overlap_with_previous": index > 0 and CHUNK_OVERLAP_SECONDS > 0,
                "overlap_seconds": CHUNK_OVERLAP_SECONDS if index > 0 else 0,
            }
        )

    if not chunks:
        raise RuntimeError("No chunks were created. ffmpeg may not have found an audio track.")

    print(f"Created {len(chunks)} chunk(s).")
    print("")
    return chunks
