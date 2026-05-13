from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from .config import NOTES_MODEL
from .openai_workflow import response_text


def _clean_text(value: Any, *, limit: int = 1000) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit].strip()


def _safe_json_loads(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    return {
        "title": "Meeting Mind Map",
        "topics": [],
        "warnings": ["The model response could not be parsed as JSON."],
        "raw_response_excerpt": text[:2000],
    }


def create_mind_map(
    client: OpenAI,
    *,
    final_notes: str,
    all_chunk_summaries: str,
    rolling_context: str,
    speaker_reconciliation_report: str,
) -> dict[str, Any]:
    prompt = f"""
Create a structured mind map for a completed meeting.

Rules:
- Return only valid JSON.
- Do not invent facts, names, decisions, dates, or owners.
- Use reconciled or user-confirmed speaker labels when available.
- Preserve uncertainty.
- Avoid duplicate items caused by overlapping audio chunks.

JSON schema:
{{
  "title": "Short meeting title",
  "topics": [
    {{
      "topic": "Topic name",
      "summary": "One-sentence summary",
      "speakers": ["Speaker A"],
      "key_points": ["Point"],
      "decisions": ["Decision"],
      "action_items": [
        {{
          "owner": "Owner or Unclear",
          "task": "Task",
          "due_date": "Due date or Unclear"
        }}
      ],
      "open_questions": ["Question"],
      "risks": ["Risk"]
    }}
  ],
  "warnings": []
}}

Final meeting notes:
{final_notes or "Not available."}

Chunk summaries:
{all_chunk_summaries or "Not available."}

Final rolling context:
{rolling_context or "Not available."}

Speaker reconciliation report:
{speaker_reconciliation_report or "Not available."}
""".strip()

    response = client.responses.create(
        model=NOTES_MODEL,
        reasoning={"effort": "medium"},
        input=prompt,
    )
    return _safe_json_loads(response_text(response))


def render_mind_map_markdown(mind_map: dict[str, Any]) -> str:
    lines: list[str] = [f"# {_clean_text(mind_map.get('title')) or 'Meeting Mind Map'}", ""]

    topics = mind_map.get("topics") or []
    if not isinstance(topics, list) or not topics:
        lines.append("No topics were generated.")
    else:
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            lines.append(f"## {_clean_text(topic.get('topic')) or 'Untitled Topic'}")
            summary = _clean_text(topic.get("summary"))
            if summary:
                lines.append("")
                lines.append(summary)

            speakers = topic.get("speakers") or []
            if speakers:
                lines.append("")
                lines.append(f"Speakers: {', '.join(_clean_text(speaker, limit=120) for speaker in speakers)}")

            for heading, key in (
                ("Key Points", "key_points"),
                ("Decisions", "decisions"),
                ("Action Items", "action_items"),
                ("Open Questions", "open_questions"),
                ("Risks", "risks"),
            ):
                values = topic.get(key) or []
                if not values:
                    continue
                lines.extend(["", f"### {heading}"])
                for value in values:
                    if isinstance(value, dict):
                        owner = _clean_text(value.get("owner"), limit=120) or "Unclear"
                        task = _clean_text(value.get("task")) or "Unclear"
                        due_date = _clean_text(value.get("due_date"), limit=120) or "Unclear"
                        lines.append(f"- {owner}: {task} (Due: {due_date})")
                    else:
                        lines.append(f"- {_clean_text(value)}")
            lines.append("")

    warnings = mind_map.get("warnings") or []
    if warnings:
        lines.extend(["## Warnings", ""])
        for warning in warnings:
            lines.append(f"- {_clean_text(warning)}")

    return "\n".join(lines).strip() + "\n"
