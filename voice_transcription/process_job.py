from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

INPUT_FILE_ENV = "MEETING_TRANSCRIPTION_INPUT_FILE"
OUTPUT_DIR_ENV = "MEETING_TRANSCRIPTION_OUTPUT_DIR"
INTERACTIVE_NAMING_ENV = "VOICE_TRANSCRIPTION_INTERACTIVE_SPEAKER_NAMING"


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run voice transcription non-interactively for an external processing job.",
    )
    parser.add_argument(
        "--input-file",
        default=os.environ.get(INPUT_FILE_ENV),
        help=f"Path to the staged audio file. Defaults to {INPUT_FILE_ENV}.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get(OUTPUT_DIR_ENV),
        help=f"Directory where top-level run artifacts should be written. Defaults to {OUTPUT_DIR_ENV}.",
    )
    return parser.parse_args(argv)


def _copy_top_level_artifacts(source_run_dir: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []

    for path in sorted(source_run_dir.iterdir()):
        if not path.is_file():
            continue
        destination = output_dir / path.name
        shutil.copy2(path, destination)
        copied.append(destination)

    return copied


def _latest_run_dir(runs_dir: Path) -> Path:
    candidates = [path for path in runs_dir.iterdir() if path.is_dir()]
    if not candidates:
        raise RuntimeError(f"No run folder was created in {runs_dir}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def run_process_job(input_file: Path, output_dir: Path) -> list[Path]:
    if not input_file.exists() or not input_file.is_file():
        raise FileNotFoundError(f"Input audio file not found: {input_file}")

    with tempfile.TemporaryDirectory(prefix="voice-transcription-runs-") as temp_dir:
        temp_runs_dir = Path(temp_dir)

        from . import __main__ as cli

        cli.RUNS_DIR = temp_runs_dir
        cli.pick_audio_file = lambda: input_file
        cli.upsert_run_index_entry = lambda entry: None
        cli.INTERACTIVE_SPEAKER_NAMING = _env_bool(INTERACTIVE_NAMING_ENV, False)

        cli.main()

        run_dir = _latest_run_dir(temp_runs_dir)
        copied = _copy_top_level_artifacts(run_dir, output_dir)
        if not copied:
            raise RuntimeError(f"No top-level artifacts were created in {run_dir}")
        return copied


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if not args.input_file:
        print(f"Missing required input file. Set {INPUT_FILE_ENV} or pass --input-file.", file=sys.stderr)
        sys.exit(2)
    if not args.output_dir:
        print(f"Missing required output directory. Set {OUTPUT_DIR_ENV} or pass --output-dir.", file=sys.stderr)
        sys.exit(2)

    copied = run_process_job(
        input_file=Path(args.input_file).expanduser().resolve(),
        output_dir=Path(args.output_dir).expanduser().resolve(),
    )

    print("")
    print("Copied top-level artifacts:")
    for path in copied:
        print(path)


if __name__ == "__main__":
    main()
