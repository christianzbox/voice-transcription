from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from .config import NOTES_MODEL
from .openai_workflow import response_text
from .run_artifacts import best_transcript_path, latest_run_dir, read_text_if_exists
from .secrets import get_api_key


def answer_question(client: OpenAI, run_dir: Path, question: str) -> str:
    transcript_path = best_transcript_path(run_dir)
    transcript = read_text_if_exists(transcript_path)
    final_notes = read_text_if_exists(run_dir / "04_final_meeting_notes.md")
    reconciliation_report = read_text_if_exists(run_dir / "02b_speaker_reconciliation_report.md")
    rolling_context = read_text_if_exists(run_dir / "03a_rolling_context.md")

    prompt = f"""
You are answering a user's question about a completed voice transcription run.

Rules:
- Answer only from the provided run artifacts.
- Prefer user-confirmed speaker names, then reconciled speaker labels.
- Do not invent names, dates, owners, decisions, or details.
- If the artifacts do not answer the question, say that clearly.
- Preserve uncertainty from the notes and speaker reconciliation report.
- When useful, cite the transcript timestamp or section name.

Question:
{question}

Final meeting notes:
{final_notes or "Not available."}

Rolling context:
{rolling_context or "Not available."}

Speaker reconciliation report:
{reconciliation_report or "Not available."}

Transcript source:
{transcript_path}

Transcript:
{transcript}
""".strip()

    response = client.responses.create(
        model=NOTES_MODEL,
        reasoning={"effort": "medium"},
        input=prompt,
    )
    return response_text(response)


def append_answer(run_dir: Path, question: str, answer: str) -> Path:
    path = run_dir / "05_ask_answers.md"
    timestamp = datetime.now().isoformat(timespec="seconds")
    existing = read_text_if_exists(path)
    entry = f"""
## {timestamp}

### Question

{question}

### Answer

{answer}
""".strip()

    content = f"{existing.rstrip()}\n\n---\n\n{entry}\n" if existing else f"# Ask Answers\n\n{entry}\n"
    path.write_text(content, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask a question about a completed transcription run.")
    parser.add_argument(
        "run_dir",
        nargs="?",
        type=Path,
        help="Run folder to query. Defaults to the newest folder in runs/.",
    )
    parser.add_argument(
        "-q",
        "--question",
        help="Question to ask. If omitted, the command prompts interactively.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Print the answer without appending it to 05_ask_answers.md.",
    )
    args = parser.parse_args()

    run_dir = (args.run_dir or latest_run_dir()).expanduser().resolve()
    question = (args.question or "").strip()
    if not question:
        if not sys.stdin.isatty():
            print("Error: provide --question when stdin is not interactive.", file=sys.stderr)
            sys.exit(1)
        question = input("Question: ").strip()
    if not question:
        print("Error: question is required.", file=sys.stderr)
        sys.exit(1)

    try:
        client = OpenAI(api_key=get_api_key())
        answer = answer_question(client, run_dir, question)
        print("")
        print(answer)
        print("")
        if not args.no_save:
            saved_path = append_answer(run_dir, question, answer)
            print(f"Saved answer: {saved_path}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
