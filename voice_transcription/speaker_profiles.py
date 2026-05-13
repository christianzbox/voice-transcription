from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from .audio import format_ts
from .config import BASE_DIR, NOTES_MODEL
from .openai_workflow import response_text

PROFILE_STORE_PATH = BASE_DIR / "speaker_profiles.json"
MAX_PROFILE_EXAMPLES = 12


def _clean_text(value: Any, *, limit: int = 500) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit].strip()


def _profile_id(display_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")
    return normalized or "speaker"


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

    profiles = profiles_data.setdefault("profiles", {})
    if not isinstance(profiles, dict):
        profiles_data["profiles"] = {}
        profiles = profiles_data["profiles"]

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
            },
        )

        profile["display_name"] = display_name
        profile["updated_at"] = now
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
    try:
        raw = json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                raw = json.loads(text[start : end + 1])
            except Exception as exc:
                return {
                    "status": "failed",
                    "suggestions": {},
                    "warnings": [f"Could not parse profile suggestions: {exc}"],
                }
        else:
            return {"status": "failed", "suggestions": {}, "warnings": ["Profile suggestion response was not JSON."]}

    known_profile_ids = set(profiles)
    known_speakers = {str(utterance.get("global_speaker_id")) for utterance in utterances}
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
