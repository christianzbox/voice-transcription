from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import RUNS_DIR

INDEX_PATH = RUNS_DIR / "index.json"


def _clean_text(value: Any, *, limit: int = 500) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit].strip()


def load_run_index(path: Path = INDEX_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "runs": []}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "runs": []}

    if not isinstance(data, dict):
        return {"version": 1, "runs": []}
    if not isinstance(data.get("runs"), list):
        data["runs"] = []
    data.setdefault("version", 1)
    return data


def save_run_index(data: dict[str, Any], path: Path = INDEX_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _extract_title(final_notes: str, fallback: str) -> str:
    for line in final_notes.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            if title and title.lower() != "meeting notes":
                return title
    return fallback


def _count_action_rows(final_notes: str) -> int:
    in_action_section = False
    count = 0

    for line in final_notes.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_action_section = stripped.lower().startswith("## action")
            continue
        if not in_action_section:
            continue
        if stripped.startswith("|") and "---" not in stripped and "Owner" not in stripped:
            count += 1
        elif stripped.startswith("- "):
            count += 1

    return count


def _speaker_names(speaker_name_map: dict[str, Any] | None, reconciliation: dict[str, Any] | None) -> list[str]:
    names: list[str] = []
    for entry in ((speaker_name_map or {}).get("speakers") or {}).values():
        if isinstance(entry, dict):
            display_name = _clean_text(entry.get("display_name"), limit=120)
            if display_name and display_name not in names:
                names.append(display_name)

    if names:
        return names

    for speaker in (reconciliation or {}).get("global_speakers") or []:
        if isinstance(speaker, dict):
            speaker_id = _clean_text(speaker.get("global_speaker_id"), limit=120)
            if speaker_id and speaker_id not in names:
                names.append(speaker_id)

    return names


def build_run_index_entry(
    *,
    run_dir: Path,
    metadata: dict[str, Any],
    final_notes: str,
    full_transcript_path: Path,
    reconciled_transcript_path: Path | None,
    named_transcript_path: Path | None,
    speaker_name_map: dict[str, Any] | None,
    reconciliation: dict[str, Any] | None,
) -> dict[str, Any]:
    best_transcript = named_transcript_path or reconciled_transcript_path or full_transcript_path
    run_name = run_dir.name

    return {
        "run_name": run_name,
        "run_dir": str(run_dir),
        "created_at": metadata.get("created_at"),
        "title": _extract_title(final_notes, run_name),
        "input_file": metadata.get("input_file"),
        "input_duration_seconds": metadata.get("input_duration_seconds"),
        "input_size_mb": metadata.get("input_size_mb"),
        "speakers": _speaker_names(speaker_name_map, reconciliation),
        "action_item_count": _count_action_rows(final_notes),
        "final_notes_path": str(run_dir / "04_final_meeting_notes.md"),
        "best_transcript_path": str(best_transcript),
    }


def upsert_run_index_entry(entry: dict[str, Any], path: Path = INDEX_PATH) -> None:
    data = load_run_index(path)
    runs = data["runs"]
    run_name = entry.get("run_name")

    replaced = False
    for index, existing in enumerate(runs):
        if isinstance(existing, dict) and existing.get("run_name") == run_name:
            runs[index] = entry
            replaced = True
            break

    if not replaced:
        runs.append(entry)

    runs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    save_run_index(data, path)
