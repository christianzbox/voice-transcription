from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from .audio import format_ts
from .config import AUDIO_EXTENSIONS, BASE_DIR, NOTES_MODEL
from .openai_workflow import response_text

PROFILE_STORE_PATH = BASE_DIR / "speaker_profiles.json"
REFERENCE_CLIPS_DIR = BASE_DIR / "speaker_reference_clips"
MAX_PROFILE_EXAMPLES = 12
MAX_REFERENCE_CLIPS = 20


def _clean_text(value: Any, *, limit: int = 500) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit].strip()


def _profile_id(display_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")
    return normalized or "speaker"


def profile_id_for_display_name(display_name: str) -> str:
    return _profile_id(display_name)


def _quote(text: str, *, limit: int = 180) -> str:
    text = _clean_text(text, limit=limit)
    if len(text) == limit:
        text = text.rstrip() + "..."
    return text.replace('"', "'")


def load_speaker_profiles(path: Path = PROFILE_STORE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "profiles": {}}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "profiles": {}}

    if not isinstance(data, dict):
        return {"version": 1, "profiles": {}}

    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        data["profiles"] = {}

    data.setdefault("version", 1)
    return data


def save_speaker_profiles(data: dict[str, Any], path: Path = PROFILE_STORE_PATH) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _ensure_profiles_dict(profiles_data: dict[str, Any]) -> dict[str, Any]:
    profiles = profiles_data.setdefault("profiles", {})
    if not isinstance(profiles, dict):
        profiles_data["profiles"] = {}
        profiles = profiles_data["profiles"]
    return profiles


def _profile_for_name(profiles_data: dict[str, Any], display_name: str, now: str) -> dict[str, Any]:
    profiles = _ensure_profiles_dict(profiles_data)
    profile_id = _profile_id(display_name)
    profile = profiles.setdefault(
        profile_id,
        {
            "profile_id": profile_id,
            "display_name": display_name,
            "created_at": now,
            "updated_at": now,
            "run_count": 0,
            "examples": [],
            "reference_clips": [],
        },
    )
    profile["display_name"] = display_name
    profile["updated_at"] = now
    profile.setdefault("examples", [])
    profile.setdefault("reference_clips", [])
    return profile


def _utterances_by_global_speaker(utterances: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for utterance in utterances:
        speaker_id = _clean_text(utterance.get("global_speaker_id"), limit=80)
        if speaker_id:
            grouped.setdefault(speaker_id, []).append(utterance)
    return grouped


def update_profiles_from_user_names(
    profiles_data: dict[str, Any],
    speaker_name_map: dict[str, Any] | None,
    utterances: list[dict[str, Any]],
    *,
    run_name: str,
    input_file: Path,
) -> bool:
    if not speaker_name_map:
        return False

    grouped = _utterances_by_global_speaker(utterances)
    changed = False
    now = datetime.now().isoformat()

    for global_speaker_id, entry in (speaker_name_map.get("speakers") or {}).items():
        if not isinstance(entry, dict) or entry.get("source") != "user":
            continue

        display_name = _clean_text(entry.get("display_name"), limit=120)
        if not display_name or display_name == global_speaker_id:
            continue

        speaker_utterances = grouped.get(str(global_speaker_id), [])
        if not speaker_utterances:
            continue

        profile = _profile_for_name(profiles_data, display_name, now)

        profile["run_count"] = int(profile.get("run_count", 0) or 0) + 1

        examples = profile.setdefault("examples", [])
        if not isinstance(examples, list):
            profile["examples"] = []
            examples = profile["examples"]

        for utterance in speaker_utterances[:4]:
            examples.append(
                {
                    "run_name": run_name,
                    "input_file": str(input_file),
                    "timestamp": format_ts(float(utterance.get("start_seconds", 0) or 0)),
                    "text": _quote(utterance.get("text")),
                }
            )

        profile["examples"] = examples[-MAX_PROFILE_EXAMPLES:]
        changed = True

    return changed


def add_reference_clip_to_profile(
    profiles_data: dict[str, Any],
    *,
    display_name: str,
    source_audio_path: Path,
    transcript_text: str = "",
    clips_dir: Path = REFERENCE_CLIPS_DIR,
) -> dict[str, Any]:
    display_name = _clean_text(display_name, limit=120)
    if not display_name:
        raise ValueError("display_name is required.")

    source_audio_path = source_audio_path.expanduser()
    if not source_audio_path.exists() or not source_audio_path.is_file():
        raise FileNotFoundError(f"Reference clip not found: {source_audio_path}")

    suffix = source_audio_path.suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        raise ValueError(f"Unsupported reference clip extension: {suffix or '(none)'}")

    now = datetime.now().isoformat()
    profile = _profile_for_name(profiles_data, display_name, now)
    profile_id = str(profile["profile_id"])
    profile_clip_dir = clips_dir / profile_id
    profile_clip_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = profile_clip_dir / f"reference_{timestamp}{suffix}"
    counter = 1
    while destination.exists():
        destination = profile_clip_dir / f"reference_{timestamp}_{counter}{suffix}"
        counter += 1

    shutil.copy2(source_audio_path, destination)

    reference_clips = profile.setdefault("reference_clips", [])
    if not isinstance(reference_clips, list):
        profile["reference_clips"] = []
        reference_clips = profile["reference_clips"]

    clip_record = {
        "added_at": now,
        "source_file": str(source_audio_path),
        "stored_file": str(destination),
        "transcript": _clean_text(transcript_text, limit=4000),
    }
    reference_clips.append(clip_record)
    profile["reference_clips"] = reference_clips[-MAX_REFERENCE_CLIPS:]
    profile["reference_clip_count"] = len(profile["reference_clips"])

    return {
        "profile_id": profile_id,
        "display_name": display_name,
        "stored_file": str(destination),
        "reference_clip_count": profile["reference_clip_count"],
    }


def _build_profile_suggestion_prompt(
    profiles_data: dict[str, Any],
    utterances: list[dict[str, Any]],
) -> str:
    profiles = profiles_data.get("profiles") or {}
    profile_sections: list[str] = []

    for profile_id, profile in sorted(profiles.items()):
        if not isinstance(profile, dict):
            continue
        profile_sections.append(f"## {profile.get('display_name')} ({profile_id})")
        for example in (profile.get("examples") or [])[-5:]:
            if isinstance(example, dict):
                profile_sections.append(f"- {example.get('timestamp')}: {_quote(example.get('text'))}")

    speaker_sections: list[str] = []
    grouped = _utterances_by_global_speaker(utterances)
    for global_speaker_id, speaker_utterances in sorted(grouped.items()):
        speaker_sections.append(f"## {global_speaker_id}")
        for utterance in speaker_utterances[:8]:
            speaker_sections.append(
                f"- [{format_ts(float(utterance.get('start_seconds', 0) or 0))}] {_quote(utterance.get('text'))}"
            )

    return f"""
You are comparing current meeting speakers with local user-confirmed speaker profiles.

Important:
- This is text-only evidence, not voice recognition.
- Be conservative. Suggest a profile only when the current speaker's wording, self-identification, or direct address strongly supports it.
- Do not suggest a known speaker merely because a name was mentioned.
- Do not auto-assign names. Return suggestions for the user to confirm.
- Return only valid JSON.

JSON schema:
{{
  "suggestions": [
    {{
      "global_speaker_id": "Speaker A",
      "profile_id": "christian",
      "suggested_name": "Christian",
      "confidence": "low",
      "reasoning": "Why this profile may match, or why evidence is weak."
    }}
  ],
  "warnings": []
}}

Allowed confidence values: high, medium, low.

Known profiles:
{chr(10).join(profile_sections) or "No known profiles."}

Current run speakers:
{chr(10).join(speaker_sections) or "No current speakers."}
""".strip()


def _known_speaker_ids(utterances: list[dict[str, Any]]) -> set[str]:
    return {str(utterance.get("global_speaker_id")) for utterance in utterances if utterance.get("global_speaker_id")}


def validate_profile_match_suggestions(
    raw: dict[str, Any],
    profiles_data: dict[str, Any],
    utterances: list[dict[str, Any]],
) -> dict[str, Any]:
    profiles = profiles_data.get("profiles") or {}
    known_profile_ids = set(profiles)
    known_speakers = _known_speaker_ids(utterances)
    suggestions: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    raw_suggestions = raw.get("suggestions") or []
    if not isinstance(raw_suggestions, list):
        raw_suggestions = []
        warnings.append("suggestions was not a list and was ignored.")

    for suggestion in raw_suggestions:
        if not isinstance(suggestion, dict):
            continue

        global_speaker_id = _clean_text(suggestion.get("global_speaker_id"), limit=80)
        profile_id = _clean_text(suggestion.get("profile_id"), limit=120)
        confidence = _clean_text(suggestion.get("confidence"), limit=20).lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"

        if global_speaker_id not in known_speakers:
            warnings.append(f"Ignored profile suggestion for unknown speaker {global_speaker_id}.")
            continue

        if profile_id not in known_profile_ids:
            warnings.append(f"Ignored profile suggestion for unknown profile {profile_id}.")
            continue

        profile = profiles[profile_id]
        suggestions[global_speaker_id] = {
            "profile_id": profile_id,
            "suggested_name": profile.get("display_name") or suggestion.get("suggested_name") or profile_id,
            "confidence": confidence,
            "reasoning": _clean_text(suggestion.get("reasoning"), limit=800),
        }

    raw_warnings = raw.get("warnings") or []
    if isinstance(raw_warnings, list):
        warnings.extend(_clean_text(warning, limit=500) for warning in raw_warnings if _clean_text(warning))

    return {"status": "success", "suggestions": suggestions, "warnings": warnings}


def _parse_json_response(text: str) -> dict[str, Any] | None:
    try:
        raw = json.loads(text)
        if isinstance(raw, dict):
            return raw
        return None
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                raw = json.loads(text[start : end + 1])
                if isinstance(raw, dict):
                    return raw
            except Exception:
                return None
    return None


def suggest_profile_matches(
    client: OpenAI,
    profiles_data: dict[str, Any],
    utterances: list[dict[str, Any]],
) -> dict[str, Any]:
    profiles = profiles_data.get("profiles") or {}
    if not profiles or not utterances:
        return {"status": "skipped", "suggestions": {}, "warnings": []}

    prompt = _build_profile_suggestion_prompt(profiles_data, utterances)

    try:
        response = client.responses.create(
            model=NOTES_MODEL,
            reasoning={"effort": "low"},
            input=prompt,
        )
    except Exception as exc:
        return {"status": "failed", "suggestions": {}, "warnings": [f"Profile suggestion request failed: {exc}"]}

    text = response_text(response)
    raw = _parse_json_response(text)
    if raw is None:
        return {"status": "failed", "suggestions": {}, "warnings": ["Profile suggestion response was not JSON."]}

    return validate_profile_match_suggestions(raw, profiles_data, utterances)


def _reference_profiles_with_transcripts(profiles_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profiles = profiles_data.get("profiles") or {}
    reference_profiles: dict[str, dict[str, Any]] = {}

    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict):
            continue

        reference_clips = []
        for clip in profile.get("reference_clips") or []:
            if not isinstance(clip, dict):
                continue
            transcript = _clean_text(clip.get("transcript"), limit=1200)
            if transcript:
                reference_clips.append(
                    {
                        "stored_file": clip.get("stored_file"),
                        "transcript": transcript,
                    }
                )

        if reference_clips:
            reference_profiles[profile_id] = {
                "profile_id": profile_id,
                "display_name": profile.get("display_name") or profile_id,
                "reference_clips": reference_clips,
            }

    return reference_profiles


def _build_reference_match_prompt(
    profiles_data: dict[str, Any],
    utterances: list[dict[str, Any]],
) -> str:
    reference_profiles = _reference_profiles_with_transcripts(profiles_data)
    profile_sections: list[str] = []

    for profile_id, profile in sorted(reference_profiles.items()):
        profile_sections.append(f"## {profile.get('display_name')} ({profile_id})")
        for clip in profile["reference_clips"][-4:]:
            profile_sections.append(f"- Reference transcript: {_quote(clip.get('transcript'), limit=320)}")

    speaker_sections: list[str] = []
    grouped = _utterances_by_global_speaker(utterances)
    for global_speaker_id, speaker_utterances in sorted(grouped.items()):
        speaker_sections.append(f"## {global_speaker_id}")
        for utterance in speaker_utterances[:10]:
            speaker_sections.append(
                f"- [{format_ts(float(utterance.get('start_seconds', 0) or 0))}] {_quote(utterance.get('text'))}"
            )

    return f"""
You are comparing current meeting speakers with known-speaker reference clip transcripts.

Important:
- This is transcript/reference-text matching, not biometric voice recognition.
- Be conservative. Suggest a profile only when reference transcript evidence and current speaker evidence strongly align.
- Direct self-identification or distinctive repeated first-person context is stronger than generic wording.
- Do not suggest a known speaker merely because their name was mentioned by someone else.
- Do not auto-assign names. Return suggestions for the user to confirm.
- Return only valid JSON.

JSON schema:
{{
  "suggestions": [
    {{
      "global_speaker_id": "Speaker A",
      "profile_id": "christian",
      "suggested_name": "Christian",
      "confidence": "medium",
      "reasoning": "Specific transcript evidence supporting or limiting this suggestion."
    }}
  ],
  "warnings": []
}}

Allowed confidence values: high, medium, low.

Known speaker reference transcripts:
{chr(10).join(profile_sections) or "No known reference transcripts."}

Current run speakers:
{chr(10).join(speaker_sections) or "No current speakers."}
""".strip()


def suggest_reference_clip_matches(
    client: OpenAI,
    profiles_data: dict[str, Any],
    utterances: list[dict[str, Any]],
) -> dict[str, Any]:
    if not utterances:
        return {"status": "skipped", "suggestions": {}, "warnings": []}

    reference_profiles = _reference_profiles_with_transcripts(profiles_data)
    if not reference_profiles:
        return {
            "status": "skipped",
            "suggestions": {},
            "warnings": ["No speaker reference clips with transcript text were available."],
        }

    prompt = _build_reference_match_prompt(profiles_data, utterances)

    try:
        response = client.responses.create(
            model=NOTES_MODEL,
            reasoning={"effort": "low"},
            input=prompt,
        )
    except Exception as exc:
        return {
            "status": "failed",
            "suggestions": {},
            "warnings": [f"Reference match suggestion request failed: {exc}"],
        }

    text = response_text(response)
    raw = _parse_json_response(text)
    if raw is None:
        return {
            "status": "failed",
            "suggestions": {},
            "warnings": ["Reference match suggestion response was not JSON."],
        }

    return validate_profile_match_suggestions(raw, profiles_data, utterances)
