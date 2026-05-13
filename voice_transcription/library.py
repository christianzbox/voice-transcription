from __future__ import annotations

import argparse
from pathlib import Path

from .run_index import INDEX_PATH, load_run_index


def _short_path(value: str) -> str:
    try:
        return Path(value).name
    except Exception:
        return value


def main() -> None:
    parser = argparse.ArgumentParser(description="List indexed voice transcription runs.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of runs to show.")
    args = parser.parse_args()

    data = load_run_index()
    runs = data.get("runs") or []

    if not runs:
        print(f"No indexed runs found. The index is created at {INDEX_PATH} after a run completes.")
        return

    print("")
    print(f"{'Created':19}  {'Run':34}  {'Speakers':24}  {'Actions':7}")
    print("-" * 92)
    for entry in runs[: max(0, args.limit)]:
        if not isinstance(entry, dict):
            continue
        created = str(entry.get("created_at") or "")[:19]
        run_name = _short_path(str(entry.get("run_name") or ""))[:34]
        speakers = ", ".join(entry.get("speakers") or [])[:24]
        action_count = str(entry.get("action_item_count") or 0)
        print(f"{created:19}  {run_name:34}  {speakers:24}  {action_count:7}")
    print("")


if __name__ == "__main__":
    main()
