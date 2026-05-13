from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import RUNS_DIR
from .speaker_reconciliation import (
    apply_reconciliation_to_utterances,
    name_map_to_display_names,
    prompt_for_speaker_names,
    render_transcript,
)


def _load_json(path: Path) -> dict[str, Any] | list[dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Could not read {path}: {exc}") from exc


def _latest_run_dir() -> Path:
    if not RUNS_DIR.exists():
        raise RuntimeError(f"Runs folder does not exist: {RUNS_DIR}")

    candidates = [path for path in RUNS_DIR.iterdir() if path.is_dir()]
    if not candidates:
        raise RuntimeError(f"No run folders found in {RUNS_DIR}")

    return max(candidates, key=lambda path: path.stat().st_mtime)


def _parse_name_assignments(values: list[str]) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise RuntimeError(f"Invalid --set value {value!r}. Use 'Speaker A=Name'.")
        speaker_id, display_name = value.split("=", 1)
        speaker_id = speaker_id.strip()
        display_name = display_name.strip()
        if not speaker_id or not display_name:
            raise RuntimeError(f"Invalid --set value {value!r}. Use 'Speaker A=Name'.")
        assignments[speaker_id] = display_name
    return assignments


def _name_map_from_assignments(global_speakers: list[str], assignments: dict[str, str]) -> dict[str, Any]:
    unknown = sorted(set(assignments) - set(global_speakers))
    if unknown:
        raise RuntimeError(f"Unknown speaker id(s): {', '.join(unknown)}")

    speakers: dict[str, dict[str, str]] = {}
    for global_speaker_id in global_speakers:
        if global_speaker_id in assignments:
            speakers[global_speaker_id] = {
                "display_name": assignments[global_speaker_id],
                "source": "user",
            }
        else:
            speakers[global_speaker_id] = {
                "display_name": global_speaker_id,
                "source": "generic",
            }

    return {
        "has_user_names": bool(assignments),
        "speakers": speakers,
    }


def rerender_speaker_names(run_dir: Path, assignments: dict[str, str] | None = None) -> Path | None:
    raw_path = run_dir / "01_full_raw_diarized_chunks.json"
    reconciliation_path = run_dir / "02a_speaker_reconciliation.json"
    existing_name_map_path = run_dir / "02d_speaker_name_map.json"

    if not raw_path.exists():
        raise RuntimeError(f"Missing raw transcription file: {raw_path}")
    if not reconciliation_path.exists():
        raise RuntimeError(f"Missing speaker reconciliation file: {reconciliation_path}")

    raw_records = _load_json(raw_path)
    reconciliation = _load_json(reconciliation_path)

    if not isinstance(raw_records, list):
        raise RuntimeError(f"{raw_path} did not contain a list.")
    if not isinstance(reconciliation, dict):
        raise RuntimeError(f"{reconciliation_path} did not contain an object.")
    if reconciliation.get("status") != "success":
        raise RuntimeError("Speaker reconciliation did not succeed for this run.")

    utterances = apply_reconciliation_to_utterances(raw_records, reconciliation)
    global_speakers = sorted(
        {str(utterance.get("global_speaker_id")) for utterance in utterances if utterance.get("global_speaker_id")}
    )

    if assignments is not None:
        speaker_name_map = _name_map_from_assignments(global_speakers, assignments)
    else:
        existing_name_map = None
        if existing_name_map_path.exists():
            loaded = _load_json(existing_name_map_path)
            if isinstance(loaded, dict):
                existing_name_map = loaded
        speaker_name_map = prompt_for_speaker_names(
            reconciliation,
            utterances,
            existing_name_map=existing_name_map,
        )

    if speaker_name_map is None:
        return None

    existing_name_map_path.write_text(
        json.dumps(speaker_name_map, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    display_names = name_map_to_display_names(speaker_name_map)
    named_transcript_path = run_dir / "02e_named_speaker_transcript.txt"

    if display_names:
        named_transcript_path.write_text(
            render_transcript(utterances, display_names),
            encoding="utf-8",
        )
        return named_transcript_path

    if named_transcript_path.exists():
        named_transcript_path.unlink()

    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rename speakers for an existing run and rerender the named transcript without retranscribing audio."
    )
    parser.add_argument(
        "run_dir",
        nargs="?",
        type=Path,
        help="Run folder to update. Defaults to the newest folder in runs/.",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="SPEAKER=NAME",
        help='Set a speaker name non-interactively, for example --set "Speaker A=Christian".',
    )
    args = parser.parse_args()

    run_dir = (args.run_dir or _latest_run_dir()).expanduser().resolve()
    assignments = _parse_name_assignments(args.set) if args.set else None

    try:
        named_transcript_path = rerender_speaker_names(run_dir, assignments)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print("")
    print(f"Updated speaker name map: {run_dir / '02d_speaker_name_map.json'}")
    if named_transcript_path:
        print(f"Updated named transcript: {named_transcript_path}")
    else:
        print("No user names were provided; removed/skipped named transcript.")


if __name__ == "__main__":
    main()
