from __future__ import annotations

import argparse
import sys
from pathlib import Path

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add a local known-speaker reference clip for future voice-aware speaker matching."
    )
    parser.add_argument("--name", required=True, help="Display name for the speaker profile.")
    parser.add_argument("audio_path", type=Path, help="Short audio clip containing only this speaker.")
    parser.add_argument("--transcript", help="Optional transcript text for the reference clip.")
    parser.add_argument("--transcript-file", type=Path, help="Optional path to transcript text for the reference clip.")
    args = parser.parse_args()

    try:
        transcript_text = _read_transcript_text(args.transcript, args.transcript_file)
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


if __name__ == "__main__":
    main()
