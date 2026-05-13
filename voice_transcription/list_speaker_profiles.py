from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .speaker_profiles import PROFILE_STORE_PATH, load_speaker_profiles


def _count_reference_transcripts(profile: dict[str, Any]) -> int:
    count = 0
    for clip in profile.get("reference_clips") or []:
        if isinstance(clip, dict) and str(clip.get("transcript") or "").strip():
            count += 1
    return count


def format_speaker_profiles(profiles_data: dict[str, Any]) -> str:
    profiles = profiles_data.get("profiles") or {}
    if not isinstance(profiles, dict) or not profiles:
        return "No speaker profiles found."

    lines: list[str] = ["Speaker profiles", ""]
    for profile_id, profile in sorted(
        profiles.items(),
        key=lambda item: str((item[1] or {}).get("display_name") or item[0]).lower(),
    ):
        if not isinstance(profile, dict):
            continue

        display_name = str(profile.get("display_name") or profile_id)
        examples = profile.get("examples") or []
        reference_clips = profile.get("reference_clips") or []
        example_count = len(examples) if isinstance(examples, list) else 0
        reference_clip_count = len(reference_clips) if isinstance(reference_clips, list) else 0
        reference_transcript_count = _count_reference_transcripts(profile)

        lines.append(display_name)
        lines.append(f"- Profile id: {profile_id}")
        lines.append(f"- Runs with user-confirmed examples: {int(profile.get('run_count', 0) or 0)}")
        lines.append(f"- Stored examples: {example_count}")
        lines.append(f"- Reference clips: {reference_clip_count}")
        lines.append(f"- Reference clips with transcript text: {reference_transcript_count}")
        if profile.get("updated_at"):
            lines.append(f"- Updated: {profile['updated_at']}")
        lines.append("")

    return "\n".join(lines).rstrip()


def main() -> None:
    parser = argparse.ArgumentParser(description="List local known-speaker profiles.")
    parser.add_argument(
        "--profile-store",
        type=Path,
        default=PROFILE_STORE_PATH,
        help="Path to speaker_profiles.json. Defaults to the app's local profile store.",
    )
    parser.add_argument("--json", action="store_true", help="Print raw profile JSON.")
    args = parser.parse_args()

    profiles_data = load_speaker_profiles(args.profile_store.expanduser())
    if args.json:
        print(json.dumps(profiles_data, indent=2, ensure_ascii=False))
        return

    print(format_speaker_profiles(profiles_data))


if __name__ == "__main__":
    main()
