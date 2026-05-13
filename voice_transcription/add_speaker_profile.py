from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI

from .config import TRANSCRIBE_MODEL
from .openai_workflow import object_to_dict
from .secrets import get_api_key
from .speaker_profiles import (
    add_reference_clip_to_profile,
    load_speaker_profiles,
    save_speaker_profiles,
)


def _read_transcript_text(transcript: str | None, transcript_file: Path | None) -> str:
    if transcript and transcript_file:
        raise RuntimeError("Use either --transcript or --transcript-file, not both.")
    if transcript:
        return transcript.strip()
    if transcript_file:
        return transcript_file.expanduser().read_text(encoding="utf-8").strip()
    return ""


def _transcription_to_text(data: dict[str, Any]) -> str:
    text = str(data.get("text") or "").strip()
    if text:
        return text

    parts: list[str] = []
    for segment in data.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        segment_text = str(segment.get("text") or "").strip()
        if segment_text:
            parts.append(segment_text)
    return " ".join(parts).strip()


def transcribe_reference_clip(client: OpenAI, audio_path: Path) -> str:
    print(f"Transcribing reference clip: {audio_path.name}")
    with audio_path.expanduser().open("rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model=TRANSCRIBE_MODEL,
            file=audio_file,
            language="en",
        )

    return _transcription_to_text(object_to_dict(transcription))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add a local known-speaker reference clip for future voice-aware speaker matching."
    )
    parser.add_argument("--name", required=True, help="Display name for the speaker profile.")
    parser.add_argument("audio_path", type=Path, help="Short audio clip containing only this speaker.")
    parser.add_argument("--transcript", help="Optional transcript text for the reference clip.")
    parser.add_argument("--transcript-file", type=Path, help="Optional path to transcript text for the reference clip.")
    parser.add_argument(
        "--transcribe",
        action="store_true",
        help="Transcribe the reference clip once and store the transcript in speaker_profiles.json.",
    )
    args = parser.parse_args()

    try:
        transcript_text = _read_transcript_text(args.transcript, args.transcript_file)
        if args.transcribe:
            if transcript_text:
                raise RuntimeError("Use --transcribe only when --transcript and --transcript-file are not provided.")
            client = OpenAI(api_key=get_api_key())
            transcript_text = transcribe_reference_clip(client, args.audio_path)
            if not transcript_text:
                raise RuntimeError("Reference clip transcription returned no text.")
        profiles = load_speaker_profiles()
        result = add_reference_clip_to_profile(
            profiles,
            display_name=args.name,
            source_audio_path=args.audio_path,
            transcript_text=transcript_text,
        )
        save_speaker_profiles(profiles)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print("")
    print(f"Updated speaker profile: {result['display_name']} ({result['profile_id']})")
    print(f"Stored reference clip: {result['stored_file']}")
    print(f"Reference clips for profile: {result['reference_clip_count']}")
    if transcript_text:
        print("Stored reference transcript text.")


if __name__ == "__main__":
    main()
