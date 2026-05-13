import json
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from .audio import format_ts
from .config import NOTES_MODEL, TRANSCRIBE_MODEL


def object_to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    try:
        return json.loads(str(obj))
    except Exception:
        return {"text": str(obj), "segments": []}


def response_text(resp: Any) -> str:
    if hasattr(resp, "output_text") and resp.output_text:
        return resp.output_text

    parts: list[str] = []
    for item in getattr(resp, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                parts.append(text)

    return "\n".join(parts).strip()


def transcribe_chunk(client: OpenAI, chunk_path: Path, chunk_index: int, total_chunks: int) -> dict[str, Any]:
    print(f"Transcribing chunk {chunk_index + 1}/{total_chunks}: {chunk_path.name}")

    last_error: Exception | None = None

    for attempt in range(1, 4):
        try:
            with chunk_path.open("rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model=TRANSCRIBE_MODEL,
                    file=audio_file,
                    response_format="diarized_json",
                    chunking_strategy="auto",
                    language="en",
                )

            return object_to_dict(transcription)

        except Exception as exc:
            last_error = exc
            print(f"  Attempt {attempt} failed: {exc}")
            if attempt < 3:
                time.sleep(2 * attempt)

    raise RuntimeError(f"Failed to transcribe {chunk_path.name}: {last_error}")


def build_chunk_transcript(data: dict[str, Any], offset_seconds: float, chunk_name: str) -> str:
    segments = data.get("segments") or []
    lines: list[str] = []

    if segments:
        for segment in segments:
            speaker = str(segment.get("speaker", "Speaker")).strip()
            start = float(segment.get("start", 0) or 0)
            end = float(segment.get("end", start) or start)
            text = (segment.get("text") or "").strip()

            global_start = offset_seconds + start
            global_end = offset_seconds + end

            if text:
                lines.append(
                    f"[{format_ts(global_start)}-{format_ts(global_end)}] "
                    f"{chunk_name} | {speaker}: {text}"
                )
    else:
        text = (data.get("text") or "").strip()
        if text:
            lines.append(f"[{format_ts(offset_seconds)}] {chunk_name} | Transcript: {text}")

    return "\n".join(lines)


def summarize_chunk(
    client: OpenAI,
    transcript_text: str,
    chunk_name: str,
    previous_context: str = "",
    overlap_notice: str = "",
) -> str:
    previous_context_section = previous_context.strip() or "None yet."
    overlap_section = overlap_notice.strip() or "No special overlap note."

    prompt = f"""
You are summarizing one chunk of a longer meeting transcript.

This app uses overlapping audio chunks. The beginning of this chunk may repeat the
end of the previous chunk. Treat overlap as context. Do not duplicate action items,
decisions, or notes just because repeated audio appears again.

Previous rolling context:
{previous_context_section}

Overlap note:
{overlap_section}

Important:
- This is only one chunk of a longer meeting.
- Speaker labels may reset between chunks.
- Do not assume Speaker 1 in this chunk is the same person as Speaker 1 in another chunk.
- Preserve exact names when people say names out loud.
- Capture every concrete decision, action item, date, number, requirement, concern, and follow-up.
- If a pronoun like "that" or "it" depends on prior context, resolve it only if the previous context supports it.
- If ownership or meaning is unclear, write "Unclear".

Output:

## {chunk_name} Summary

### What happened
Concise but complete.

### Decisions
Bullet list. Use "None stated" if none.

### Action Items
Use bullets with Owner / Task / Due date / Evidence. Use "Unclear" when unclear.

### Open Questions
Bullet list.

### Risks / Blockers
Bullet list.

### Notable Details
Bullet list of specific details that may matter later.

### Context Carry-Forward
Short bullet list of context that the next chunk should know.

Transcript chunk:

{transcript_text}
""".strip()

    response = client.responses.create(
        model=NOTES_MODEL,
        reasoning={"effort": "medium"},
        input=prompt,
    )

    return response_text(response)


def update_rolling_context(
    client: OpenAI,
    previous_context: str,
    new_chunk_summary: str,
    chunk_name: str,
) -> str:
    prompt = f"""
Maintain a compact rolling context for a long meeting.

Goal:
Create context that helps summarize the NEXT chunk without having to reread the entire meeting.

Keep:
- active topics
- unresolved references
- decisions already made
- action items already identified
- names/roles inferred from explicit mentions only
- important numbers, dates, requirements, constraints
- unresolved questions

Rules:
- Do not invent details.
- Keep it compact.
- Remove old details that are no longer useful.
- If speaker identity is uncertain, say uncertain.

Previous rolling context:
{previous_context or "None yet."}

New chunk summary from {chunk_name}:
{new_chunk_summary}

Return only the updated rolling context.
""".strip()

    response = client.responses.create(
        model=NOTES_MODEL,
        reasoning={"effort": "low"},
        input=prompt,
    )

    return response_text(response)


def create_final_notes(
    client: OpenAI,
    all_chunk_summaries: str,
    full_transcript_path: Path,
    rolling_context: str,
    speaker_reconciliation_report: str = "",
    reconciled_transcript_path: Path | None = None,
    named_transcript_path: Path | None = None,
    speaker_name_map: dict[str, Any] | None = None,
) -> str:
    speaker_report_section = speaker_reconciliation_report.strip() or "No speaker reconciliation report was available."
    best_transcript_path = named_transcript_path or reconciled_transcript_path or full_transcript_path
    reconciled_path_section = str(reconciled_transcript_path) if reconciled_transcript_path else "No reconciled transcript was available."
    named_path_section = str(named_transcript_path) if named_transcript_path else "No user-named transcript was available."
    name_map_section = (
        json.dumps(speaker_name_map, indent=2, ensure_ascii=False)
        if speaker_name_map
        else "No user-confirmed speaker name map was available."
    )

    prompt = f"""
You are creating final meeting notes from chunk-level meeting summaries.

Goal:
Create practical, accurate meeting notes.

Important:
- Audio chunks may overlap, so repeated content may appear near chunk boundaries.
- Do not duplicate action items or decisions from overlapped content.
- Speaker labels may reset between chunks.
- Do not invent names, owners, deadlines, decisions, or dates.
- If ownership is unclear, write "Unclear".
- If something was only discussed but not decided, do not label it as a decision.
- Merge duplicate action items.
- Keep the notes direct and useful.
- Use reconciled or user-confirmed speaker labels when available.
- Do not invent real names.
- If speaker identity is uncertain, say unclear.
- Preserve uncertainty from the speaker reconciliation report.

Final rolling context:
{rolling_context or "None."}

Speaker reconciliation report:
{speaker_report_section}

Reconciled transcript path:
{reconciled_path_section}

User-named transcript path:
{named_path_section}

User-confirmed speaker name map:
{name_map_section}

Output:

# Meeting Notes

## Executive Summary
A short useful summary of the whole meeting.

## Key Decisions
Bullet list. Include evidence/context when useful.

## Action Items
Use a markdown table with:
| Owner | Task | Due date | Evidence / context |

## Open Questions
Bullet list.

## Risks / Blockers
Bullet list.

## Important Details
Bullet list of concrete details, requirements, numbers, constraints, or context that should not be lost.

## Follow-Up Email Draft
Write a concise email that could be sent to meeting attendees.

## Transcript Reference
Mention that the best available transcript for speaker labels is saved at:
{best_transcript_path}

Also mention that the original full merged transcript is saved at:
{full_transcript_path}

Chunk summaries:

{all_chunk_summaries}
""".strip()

    response = client.responses.create(
        model=NOTES_MODEL,
        reasoning={"effort": "medium"},
        input=prompt,
    )

    return response_text(response)
