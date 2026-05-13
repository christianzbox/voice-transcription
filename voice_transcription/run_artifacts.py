from __future__ import annotations

from pathlib import Path

from .config import RUNS_DIR


def latest_run_dir() -> Path:
    if not RUNS_DIR.exists():
        raise RuntimeError(f"Runs folder does not exist: {RUNS_DIR}")

    candidates = [path for path in RUNS_DIR.iterdir() if path.is_dir()]
    if not candidates:
        raise RuntimeError(f"No run folders found in {RUNS_DIR}")

    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def best_transcript_path(run_dir: Path) -> Path:
    for name in (
        "02e_named_speaker_transcript.txt",
        "02c_reconciled_speaker_transcript.txt",
        "02_full_merged_speaker_transcript.txt",
    ):
        path = run_dir / name
        if path.exists():
            return path
    raise RuntimeError(f"No transcript file found in {run_dir}")
