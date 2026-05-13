from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from openai import OpenAI

from .audio import format_ts
from .config import NOTES_MODEL
from .openai_workflow import response_text


VALID_CONFIDENCE = {"high", "medium", "low"}
ALLOWED_NAME_EVIDENCE = {
    "self_identification",
    "direct_address",
    "strong_transcript_evidence",
}


def _speaker_letter(index: int) -> str:
    letters: list[str] = []
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def _speaker_id(index: int) -> str:
    return f"Speaker {_speaker_letter(index)}"


def _normalize_confidence(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_CONFIDENCE:
        return normalized
    return "low"


def _normalize_global_speaker_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None

    match = re.fullmatch(r"(?i)speaker\s+([a-z]+)", text)
    if match:
        return f"Speaker {match.group(1).upper()}"

    match = re.fullmatch(r"(?i)([a-z]+)", text)
    if match:
        return f"Speaker {match.group(1).upper()}"

    return None


def _clean_text(value: Any, *, limit: int = 500) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit].strip()


def _clean_possible_name(value: Any) -> str | None:
    text = _clean_text(value, limit=120)
    if not text or text.lower() in {"none", "null", "unknown", "unclear", "n/a"}:
        return None
    return text


def _md_cell(value: Any) -> str:
    return _clean_text(value, limit=500).replace("|", "\\|") or "None"


def _safe_json_loads(text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed, None
        return None, "Model returned JSON, but the root value was not an object."
    except Exception:
        pass

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)

    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed, None
        return None, "Model returned JSON, but the root value was not an object."
    except Exception:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        candidate = stripped[start : end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed, None
            return None, "Model returned JSON, but the root value was not an object."
        except Exception as exc:
            return None, f"Could not parse JSON object from model response: {exc}"

    return None, "Model response did not contain a JSON object."


def extract_utterances(raw_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    utterances: list[dict[str, Any]] = []

    for raw_record in raw_records:
        chunk_index = int(raw_record.get("chunk_index", 0) or 0)
        chunk_name = str(raw_record.get("chunk_name") or f"Chunk {chunk_index + 1}")
        offset_seconds = float(raw_record.get("offset_seconds", 0) or 0)
        transcription = raw_record.get("transcription") or {}
        segments = transcription.get("segments") or []

        if segments:
            for segment_index, segment in enumerate(segments):
                text = _clean_text(segment.get("text"), limit=2000)
                if not text:
                    continue

                local_speaker = _clean_text(segment.get("speaker") or "Unknown Speaker", limit=80)
                start = float(segment.get("start", 0) or 0)
                end = float(segment.get("end", start) or start)

                utterances.append(
                    {
                        "chunk_index": chunk_index,
                        "chunk_name": chunk_name,
                        "segment_index": segment_index,
                        "local_speaker": local_speaker,
                        "start_seconds": offset_seconds + start,
                        "end_seconds": offset_seconds + end,
                        "text": text,
                    }
                )
        else:
            text = _clean_text(transcription.get("text"), limit=4000)
            if text:
                utterances.append(
                    {
                        "chunk_index": chunk_index,
                        "chunk_name": chunk_name,
                        "segment_index": 0,
                        "local_speaker": "Unknown Speaker",
                        "start_seconds": offset_seconds,
                        "end_seconds": offset_seconds,
                        "text": text,
                    }
                )

    return utterances


def _quote(text: str, *, limit: int = 180) -> str:
    text = _clean_text(text, limit=limit)
    if len(text) == limit:
        text = text.rstrip() + "..."
    return text.replace('"', "'")


def _speaker_stats(utterances: list[dict[str, Any]], label_key: str) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}

    for utterance in utterances:
        label = str(utterance.get(label_key) or "Unknown Speaker")
        if label not in stats:
            stats[label] = {
                "label": label,
                "first_appearance_seconds": float(utterance.get("start_seconds", 0) or 0),
                "utterance_count": 0,
                "speaking_seconds": 0.0,
                "representative_quotes": [],
            }

        item = stats[label]
        item["utterance_count"] += 1
        start = float(utterance.get("start_seconds", 0) or 0)
        end = float(utterance.get("end_seconds", start) or start)
        item["speaking_seconds"] += max(0.0, end - start)

        quotes = item["representative_quotes"]
        text = str(utterance.get("text") or "").strip()
        if text and len(quotes) < 3 and len(text.split()) >= 4:
            quotes.append(_quote(text))

    return stats


def _build_evidence(utterances: list[dict[str, Any]]) -> str:
    by_chunk_speaker: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    chunks: dict[int, str] = {}

    for utterance in utterances:
        chunk_index = int(utterance["chunk_index"])
        chunks[chunk_index] = str(utterance["chunk_name"])
        by_chunk_speaker[(chunk_index, str(utterance["local_speaker"]))].append(utterance)

    sections: list[str] = []

    for chunk_index in sorted(chunks):
        sections.append(f"## {chunks[chunk_index]} (chunk_index {chunk_index})")
        local_speakers = sorted(
            speaker for (speaker_chunk, speaker) in by_chunk_speaker if speaker_chunk == chunk_index
        )

        for local_speaker in local_speakers:
            speaker_utterances = by_chunk_speaker[(chunk_index, local_speaker)]
            first = speaker_utterances[0]
            last = speaker_utterances[-1]
            sections.append(
                f"- {local_speaker}: {len(speaker_utterances)} utterances, "
                f"{format_ts(first['start_seconds'])}-{format_ts(last['end_seconds'])}"
            )
            for utterance in speaker_utterances[:5]:
                sections.append(
                    f"  - [{format_ts(utterance['start_seconds'])}-{format_ts(utterance['end_seconds'])}] "
                    f"{_quote(utterance['text'])}"
                )

    if len(chunks) > 1:
        sections.append("## Adjacent chunk boundary evidence")
        by_chunk: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for utterance in utterances:
            by_chunk[int(utterance["chunk_index"])].append(utterance)

        for chunk_index in sorted(chunks)[:-1]:
            sections.append(f"### Boundary after {chunks[chunk_index]}")
            for utterance in by_chunk[chunk_index][-4:] + by_chunk[chunk_index + 1][:4]:
                sections.append(
                    f"- {utterance['chunk_name']} | {utterance['local_speaker']} "
                    f"[{format_ts(utterance['start_seconds'])}-{format_ts(utterance['end_seconds'])}]: "
                    f"{_quote(utterance['text'])}"
                )

    return "\n".join(sections)


def build_reconciliation_prompt(raw_records: list[dict[str, Any]], chunk_transcript_text: str) -> str:
    utterances = extract_utterances(raw_records)
    evidence = _build_evidence(utterances)

    return f"""
You are reconciling diarized speaker labels across overlapping audio chunks.

Goal:
Map chunk-local speakers such as "Chunk 1 | Speaker 1" and "Chunk 2 | Speaker 2"
to stable meeting-wide generic labels such as "Speaker A", "Speaker B", and "Speaker C".

Rules:
- Be conservative. Prefer generic labels when identity is uncertain.
- Speaker labels can reset between chunks.
- Use overlap, conversational continuity, explicit self-identification, direct address, and repeated context as evidence.
- Do not merge speakers only because they share a local label number.
- Do not assign real names from vibe, role, job title, topic, file name, or user account name.
- A name mentioned in the meeting is not enough by itself.
- If a possible real name is supported, explain the exact transcript evidence.
- If the evidence is weak, set possible_real_name to null and keep the global label generic.
- Return only valid JSON. Do not wrap it in markdown.

JSON schema:
{{
  "global_speakers": [
    {{
      "global_speaker_id": "Speaker A",
      "display_name": "Speaker A",
      "possible_real_name": null,
      "name_evidence": "none",
      "confidence": "medium",
      "reasoning": "Why these local speakers appear to be the same person."
    }}
  ],
  "mappings": [
    {{
      "chunk_index": 0,
      "chunk_name": "Chunk 1",
      "local_speaker": "Speaker 1",
      "global_speaker_id": "Speaker A",
      "confidence": "high",
      "reasoning": "Specific evidence for this mapping."
    }}
  ],
  "warnings": [
    "Speaker labels may be uncertain in Chunk 3 due to short utterances."
  ]
}}

Allowed confidence values: high, medium, low.
Allowed name_evidence values: none, self_identification, direct_address, strong_transcript_evidence.

Chunk speaker evidence:
{evidence}

Full merged transcript text for additional context:
{chunk_transcript_text}
""".strip()


def _known_chunk_speakers(utterances: list[dict[str, Any]]) -> set[tuple[int, str]]:
    return {
        (int(utterance["chunk_index"]), str(utterance["local_speaker"]))
        for utterance in utterances
    }


def validate_reconciliation_result(
    raw_result: dict[str, Any],
    raw_records: list[dict[str, Any]],
) -> dict[str, Any]:
    utterances = extract_utterances(raw_records)
    known_speakers = _known_chunk_speakers(utterances)
    validation_warnings: list[str] = []

    global_speakers: dict[str, dict[str, Any]] = {}
    next_speaker_index = 0

    raw_global_speakers = raw_result.get("global_speakers") or []
    if not isinstance(raw_global_speakers, list):
        raw_global_speakers = []
        validation_warnings.append("global_speakers was not a list and was ignored.")

    for raw_speaker in raw_global_speakers:
        if not isinstance(raw_speaker, dict):
            validation_warnings.append("Ignored a non-object global_speakers entry.")
            continue

        global_speaker_id = _normalize_global_speaker_id(raw_speaker.get("global_speaker_id"))
        if not global_speaker_id:
            validation_warnings.append("Ignored a global speaker with an invalid global_speaker_id.")
            continue

        confidence = _normalize_confidence(raw_speaker.get("confidence"))
        possible_name = _clean_possible_name(raw_speaker.get("possible_real_name"))
        name_evidence = _clean_text(raw_speaker.get("name_evidence"), limit=80).lower() or "none"

        if possible_name and (confidence != "high" or name_evidence not in ALLOWED_NAME_EVIDENCE):
            validation_warnings.append(
                f"Downgraded possible real name for {global_speaker_id}; evidence was not high-confidence."
            )
            possible_name = None
            name_evidence = "none"

        global_speakers[global_speaker_id] = {
            "global_speaker_id": global_speaker_id,
            "display_name": global_speaker_id,
            "possible_real_name": possible_name,
            "name_evidence": name_evidence,
            "confidence": confidence,
            "reasoning": _clean_text(raw_speaker.get("reasoning"), limit=1000),
        }

    raw_mappings = raw_result.get("mappings") or []
    if not isinstance(raw_mappings, list):
        raw_mappings = []
        validation_warnings.append("mappings was not a list and was ignored.")

    mappings_by_key: dict[tuple[int, str], dict[str, Any]] = {}

    for raw_mapping in raw_mappings:
        if not isinstance(raw_mapping, dict):
            validation_warnings.append("Ignored a non-object mapping entry.")
            continue

        try:
            chunk_index = int(raw_mapping.get("chunk_index"))
        except Exception:
            validation_warnings.append("Ignored a mapping with an invalid chunk_index.")
            continue

        local_speaker = _clean_text(raw_mapping.get("local_speaker"), limit=120)
        if (chunk_index, local_speaker) not in known_speakers:
            validation_warnings.append(
                f"Ignored mapping for unknown speaker: chunk_index={chunk_index}, local_speaker={local_speaker!r}."
            )
            continue

        global_speaker_id = _normalize_global_speaker_id(raw_mapping.get("global_speaker_id"))
        if not global_speaker_id:
            validation_warnings.append(
                f"Ignored mapping for {local_speaker} in chunk {chunk_index}; global_speaker_id was invalid."
            )
            continue

        confidence = _normalize_confidence(raw_mapping.get("confidence"))
        mappings_by_key[(chunk_index, local_speaker)] = {
            "chunk_index": chunk_index,
            "chunk_name": _clean_text(raw_mapping.get("chunk_name"), limit=120) or f"Chunk {chunk_index + 1}",
            "local_speaker": local_speaker,
            "global_speaker_id": global_speaker_id,
            "confidence": confidence,
            "reasoning": _clean_text(raw_mapping.get("reasoning"), limit=1000),
            "source": "model",
        }

        if global_speaker_id not in global_speakers:
            global_speakers[global_speaker_id] = {
                "global_speaker_id": global_speaker_id,
                "display_name": global_speaker_id,
                "possible_real_name": None,
                "name_evidence": "none",
                "confidence": "low",
                "reasoning": "Referenced by a valid mapping, but omitted from global_speakers.",
            }
            validation_warnings.append(
                f"Added missing global speaker definition for {global_speaker_id}."
            )

    used_global_ids = set(global_speakers)

    def next_unused_global_id() -> str:
        nonlocal next_speaker_index
        while True:
            candidate = _speaker_id(next_speaker_index)
            next_speaker_index += 1
            if candidate not in used_global_ids:
                used_global_ids.add(candidate)
                return candidate

    for chunk_index, local_speaker in sorted(known_speakers):
        if (chunk_index, local_speaker) in mappings_by_key:
            continue

        global_speaker_id = next_unused_global_id()
        global_speakers[global_speaker_id] = {
            "global_speaker_id": global_speaker_id,
            "display_name": global_speaker_id,
            "possible_real_name": None,
            "name_evidence": "none",
            "confidence": "low",
            "reasoning": "Deterministic fallback for an unmapped chunk-local speaker.",
        }
        mappings_by_key[(chunk_index, local_speaker)] = {
            "chunk_index": chunk_index,
            "chunk_name": f"Chunk {chunk_index + 1}",
            "local_speaker": local_speaker,
            "global_speaker_id": global_speaker_id,
            "confidence": "low",
            "reasoning": "The model did not provide a valid mapping for this chunk-local speaker.",
            "source": "deterministic_fallback",
        }
        validation_warnings.append(
            f"Assigned deterministic fallback {global_speaker_id} to chunk {chunk_index + 1} {local_speaker}."
        )

    warnings = raw_result.get("warnings") or []
    if not isinstance(warnings, list):
        warnings = [str(warnings)]

    return {
        "status": "success",
        "global_speakers": sorted(global_speakers.values(), key=lambda item: item["global_speaker_id"]),
        "mappings": sorted(
            mappings_by_key.values(),
            key=lambda item: (int(item["chunk_index"]), str(item["local_speaker"])),
        ),
        "warnings": [_clean_text(warning, limit=1000) for warning in warnings if _clean_text(warning)],
        "validation_warnings": validation_warnings,
    }


def reconcile_speakers(
    client: OpenAI,
    raw_records: list[dict[str, Any]],
    full_transcript: str,
) -> dict[str, Any]:
    if not raw_records:
        return {
            "status": "failed",
            "error": "No raw transcription records were available.",
            "global_speakers": [],
            "mappings": [],
            "warnings": [],
            "validation_warnings": [],
        }

    prompt = build_reconciliation_prompt(raw_records, full_transcript)

    try:
        response = client.responses.create(
            model=NOTES_MODEL,
            reasoning={"effort": "high"},
            input=prompt,
        )
    except Exception as exc:
        return {
            "status": "failed",
            "error": f"Speaker reconciliation request failed: {exc}",
            "global_speakers": [],
            "mappings": [],
            "warnings": [],
            "validation_warnings": [],
        }

    model_text = response_text(response)
    parsed, parse_error = _safe_json_loads(model_text)
    if parsed is None:
        return {
            "status": "failed",
            "error": parse_error or "Could not parse model response as JSON.",
            "model_response_excerpt": model_text[:2000],
            "global_speakers": [],
            "mappings": [],
            "warnings": [],
            "validation_warnings": [],
        }

    result = validate_reconciliation_result(parsed, raw_records)
    result["model"] = NOTES_MODEL
    return result


def _mapping_lookup(reconciliation: dict[str, Any]) -> dict[tuple[int, str], str]:
    lookup: dict[tuple[int, str], str] = {}
    for mapping in reconciliation.get("mappings") or []:
        try:
            chunk_index = int(mapping["chunk_index"])
        except Exception:
            continue
        local_speaker = str(mapping.get("local_speaker") or "")
        global_speaker_id = str(mapping.get("global_speaker_id") or "")
        if local_speaker and global_speaker_id:
            lookup[(chunk_index, local_speaker)] = global_speaker_id
    return lookup


def apply_reconciliation_to_utterances(
    raw_records: list[dict[str, Any]],
    reconciliation: dict[str, Any],
) -> list[dict[str, Any]]:
    utterances = extract_utterances(raw_records)
    lookup = _mapping_lookup(reconciliation)

    for utterance in utterances:
        key = (int(utterance["chunk_index"]), str(utterance["local_speaker"]))
        utterance["global_speaker_id"] = lookup.get(key, str(utterance["local_speaker"]))

    return utterances


def render_transcript(
    utterances: list[dict[str, Any]],
    name_map: dict[str, str] | None = None,
) -> str:
    name_map = name_map or {}
    lines: list[str] = []

    for utterance in utterances:
        global_speaker_id = str(utterance.get("global_speaker_id") or utterance.get("local_speaker") or "Unknown Speaker")
        display_name = name_map.get(global_speaker_id, global_speaker_id)
        lines.append(
            f"[{format_ts(utterance['start_seconds'])}-{format_ts(utterance['end_seconds'])}] "
            f"{display_name}: {utterance['text']}"
        )

    return "\n".join(lines)


def render_reconciliation_report(
    reconciliation: dict[str, Any],
    utterances: list[dict[str, Any]],
) -> str:
    if reconciliation.get("status") != "success":
        return f"""
# Speaker Reconciliation Report

Speaker reconciliation failed.

Reason:

{reconciliation.get("error") or "Unknown failure."}

The app preserved the original merged transcript and continued without stable cross-chunk speaker labels.
""".strip()

    stats = _speaker_stats(utterances, "global_speaker_id")
    speaker_by_id = {
        str(speaker.get("global_speaker_id")): speaker
        for speaker in reconciliation.get("global_speakers") or []
    }

    lines: list[str] = [
        "# Speaker Reconciliation Report",
        "",
        "This report explains the conservative mapping from chunk-local speaker labels to stable meeting-wide generic speakers.",
        "",
        "## Global Speakers",
        "",
        "| Speaker | First appearance | Utterances | Approx. speaking time | Possible real name | Confidence | Evidence |",
        "| --- | --- | ---: | ---: | --- | --- | --- |",
    ]

    for global_speaker_id in sorted(stats):
        speaker = speaker_by_id.get(global_speaker_id, {})
        item = stats[global_speaker_id]
        possible_name = speaker.get("possible_real_name") or "None"
        lines.append(
            f"| {_md_cell(global_speaker_id)} | {format_ts(item['first_appearance_seconds'])} | "
            f"{item['utterance_count']} | {format_ts(item['speaking_seconds'])} | "
            f"{_md_cell(possible_name)} | {_md_cell(speaker.get('confidence', 'low'))} | "
            f"{_md_cell(speaker.get('name_evidence', 'none'))} |"
        )

    lines.extend(["", "## Mapping Table", ""])
    lines.extend(
        [
            "| Chunk | Local speaker | Global speaker | Confidence | Source | Reasoning |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )

    for mapping in reconciliation.get("mappings") or []:
        chunk_name = mapping.get("chunk_name") or f"Chunk {int(mapping.get('chunk_index', 0)) + 1}"
        lines.append(
            f"| {_md_cell(chunk_name)} | "
            f"{_md_cell(mapping.get('local_speaker'))} | {_md_cell(mapping.get('global_speaker_id'))} | "
            f"{_md_cell(mapping.get('confidence'))} | {_md_cell(mapping.get('source', 'model'))} | "
            f"{_md_cell(mapping.get('reasoning'))} |"
        )

    lines.extend(["", "## Representative Quotes", ""])
    for global_speaker_id in sorted(stats):
        lines.append(f"### {global_speaker_id}")
        quotes = stats[global_speaker_id]["representative_quotes"] or ["No representative quotes available."]
        for index, quote in enumerate(quotes, start=1):
            lines.append(f"{index}. \"{quote}\"")
        lines.append("")

    warnings = list(reconciliation.get("warnings") or []) + list(reconciliation.get("validation_warnings") or [])
    lines.extend(["## Warnings And Uncertainties", ""])
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- None reported.")

    lines.extend(
        [
            "",
            "## Naming Policy",
            "",
            "- Generic speaker labels are used by default.",
            "- Real names are only treated as possible names when supported by explicit transcript evidence.",
            "- User-entered names, if provided, are saved separately in `02d_speaker_name_map.json` and applied to `02e_named_speaker_transcript.txt`.",
        ]
    )

    return "\n".join(lines).strip()


def prompt_for_speaker_names(
    reconciliation: dict[str, Any],
    utterances: list[dict[str, Any]],
    existing_name_map: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if reconciliation.get("status") != "success":
        return None

    if not sys.stdin.isatty():
        print("Skipping interactive speaker naming because stdin is not interactive.")
        return None

    stats = _speaker_stats(utterances, "global_speaker_id")
    speaker_by_id = {
        str(speaker.get("global_speaker_id")): speaker
        for speaker in reconciliation.get("global_speakers") or []
    }

    print("")
    print("Speaker naming")
    print("Enter a name for any speaker you recognize, or press Enter to keep the generic label.")
    print("")

    entries: dict[str, dict[str, Any]] = {}
    any_user_names = False
    existing_speakers = (existing_name_map or {}).get("speakers") or {}

    for global_speaker_id in sorted(stats):
        item = stats[global_speaker_id]
        speaker = speaker_by_id.get(global_speaker_id, {})
        possible_name = speaker.get("possible_real_name")
        confidence = speaker.get("confidence") or "low"
        existing_entry = existing_speakers.get(global_speaker_id)
        existing_display_name = ""
        if isinstance(existing_entry, dict):
            existing_display_name = _clean_text(existing_entry.get("display_name"), limit=120)

        print(global_speaker_id)
        print(f"- First appearance: {format_ts(item['first_appearance_seconds'])}")
        print(f"- Approximate utterances: {item['utterance_count']}")
        print(f"- Approximate speaking time: {format_ts(item['speaking_seconds'])}")
        if existing_display_name and existing_display_name != global_speaker_id:
            print(f"- Current name: {existing_display_name}")
        if possible_name:
            print(f"- Possible name: {possible_name}, {confidence} confidence")
        else:
            print("- Possible name: None")
        print("- Representative quotes:")
        quotes = item["representative_quotes"] or ["No representative quotes available."]
        for index, quote in enumerate(quotes[:3], start=1):
            print(f"  {index}. \"{quote}\"")

        try:
            if existing_display_name and existing_display_name != global_speaker_id:
                prompt = f"Name for {global_speaker_id}, or press Enter to keep {existing_display_name}: "
            else:
                prompt = f"Name for {global_speaker_id}, or press Enter to keep generic: "
            entered_name = input(prompt).strip()
        except EOFError:
            print("Skipping remaining speaker naming because input ended.")
            entered_name = ""

        if entered_name:
            any_user_names = True
            entries[global_speaker_id] = {
                "display_name": entered_name,
                "source": "user",
            }
        elif existing_display_name and existing_display_name != global_speaker_id:
            any_user_names = True
            entries[global_speaker_id] = {
                "display_name": existing_display_name,
                "source": "user",
            }
        else:
            entries[global_speaker_id] = {
                "display_name": global_speaker_id,
                "source": "generic",
            }

        print("")

    return {
        "has_user_names": any_user_names,
        "speakers": entries,
    }


def name_map_to_display_names(name_map: dict[str, Any] | None) -> dict[str, str]:
    if not name_map:
        return {}

    display_names: dict[str, str] = {}
    for global_speaker_id, entry in (name_map.get("speakers") or {}).items():
        if not isinstance(entry, dict):
            continue
        display_name = _clean_text(entry.get("display_name"), limit=120)
        if display_name and display_name != global_speaker_id:
            display_names[str(global_speaker_id)] = display_name

    return display_names
