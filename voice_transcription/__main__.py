import json
import sys
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from .audio import format_ts, get_duration_seconds, is_audio_file, make_chunks
from .config import (
    AUDIO_BITRATE,
    AUDIO_SAMPLE_RATE,
    BASE_DIR,
    CHUNK_OVERLAP_SECONDS,
    CHUNK_SECONDS,
    CREATE_MIND_MAP,
    INPUT_DIR,
    INTERACTIVE_SPEAKER_NAMING,
    NOTES_MODEL,
    RUNS_DIR,
    SPEAKER_PROFILE_SUGGESTIONS,
    SUMMARY_TEMPLATE,
    TRANSCRIBE_MODEL,
)
from .mind_map import create_mind_map, render_mind_map_markdown
from .openai_workflow import (
    build_chunk_transcript,
    create_final_notes,
    summarize_chunk,
    transcribe_chunk,
    update_rolling_context,
)
from .run_index import build_run_index_entry, upsert_run_index_entry
from .secrets import get_api_key
from .speaker_profiles import (
    load_speaker_profiles,
    save_speaker_profiles,
    suggest_profile_matches,
    update_profiles_from_user_names,
)
from .speaker_reconciliation import (
    apply_reconciliation_to_utterances,
    name_map_to_display_names,
    prompt_for_speaker_names,
    reconcile_speakers,
    render_reconciliation_report,
    render_transcript,
)


def pick_audio_file() -> Path:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    candidates = sorted(
        [path for path in INPUT_DIR.iterdir() if is_audio_file(path)],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not candidates:
        print("")
        print("No audio files found.")
        print("Drop a .m4a/.mp3/.wav/.mp4/.webm file into:")
        print(INPUT_DIR)
        print("")
        manual = input("Or drag an audio file here, then press Enter: ").strip().strip('"').strip("'")
        if not manual:
            sys.exit(1)
        return Path(manual).expanduser()

    print("")
    print("Audio files found in input/:")
    print("")

    for i, path in enumerate(candidates, start=1):
        size_mb = path.stat().st_size / (1024 * 1024)
        duration = get_duration_seconds(path)
        duration_text = format_ts(duration) if duration else "unknown duration"
        print(f"{i}. {path.name} — {size_mb:.1f} MB — {duration_text}")

    print("")
    choice = input("Pick a number, or press Enter for the newest file: ").strip()

    if choice == "":
        return candidates[0]

    if choice.isdigit() and 1 <= int(choice) <= len(candidates):
        return candidates[int(choice) - 1]

    print("Invalid choice.")
    sys.exit(1)


def main() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    api_key = get_api_key()
    client = OpenAI(api_key=api_key)

    audio_path = pick_audio_file()

    if not audio_path.exists():
        print(f"File not found: {audio_path}")
        sys.exit(1)

    run_name = f"{audio_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = RUNS_DIR / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    print("")
    print("Selected file:")
    print(audio_path)
    print("")
    print("Output folder:")
    print(run_dir)
    print("")

    original_duration = get_duration_seconds(audio_path)
    original_size_mb = audio_path.stat().st_size / (1024 * 1024)

    metadata = {
        "app_base_dir": str(BASE_DIR),
        "input_file": str(audio_path),
        "input_size_mb": original_size_mb,
        "input_duration_seconds": original_duration,
        "chunk_seconds": CHUNK_SECONDS,
        "chunk_overlap_seconds": CHUNK_OVERLAP_SECONDS,
        "audio_bitrate": AUDIO_BITRATE,
        "audio_sample_rate": AUDIO_SAMPLE_RATE,
        "create_mind_map": CREATE_MIND_MAP,
        "interactive_speaker_naming": INTERACTIVE_SPEAKER_NAMING,
        "speaker_profile_suggestions": SPEAKER_PROFILE_SUGGESTIONS,
        "summary_template": SUMMARY_TEMPLATE,
        "transcribe_model": TRANSCRIBE_MODEL,
        "notes_model": NOTES_MODEL,
        "created_at": datetime.now().isoformat(),
    }

    (run_dir / "00_run_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    chunks = make_chunks(audio_path, run_dir)

    all_raw: list[dict] = []
    full_transcript_parts: list[str] = []
    chunk_summaries: list[str] = []

    raw_dir = run_dir / "raw_chunk_json"
    raw_dir.mkdir(exist_ok=True)

    transcript_dir = run_dir / "chunk_transcripts"
    transcript_dir.mkdir(exist_ok=True)

    summary_dir = run_dir / "chunk_summaries"
    summary_dir.mkdir(exist_ok=True)

    rolling_context = ""

    for index, chunk in enumerate(chunks):
        chunk_path = Path(chunk["path"])
        chunk_start = float(chunk["start_seconds"])
        chunk_duration = float(chunk["duration_seconds"])
        chunk_name = f"Chunk {index + 1}"

        data = transcribe_chunk(client, chunk_path, index, len(chunks))

        raw_record = {
            "chunk_index": index,
            "chunk_name": chunk_name,
            "chunk_file": str(chunk_path),
            "offset_seconds": chunk_start,
            "duration_seconds": chunk_duration,
            "requested_duration_seconds": chunk.get("requested_duration_seconds"),
            "overlap_seconds": chunk.get("overlap_seconds", 0),
            "transcription": data,
        }

        all_raw.append(raw_record)

        raw_path = raw_dir / f"chunk_{index + 1:03d}.json"
        raw_path.write_text(json.dumps(raw_record, indent=2, ensure_ascii=False), encoding="utf-8")

        chunk_transcript = build_chunk_transcript(data, chunk_start, chunk_name)

        chunk_transcript_path = transcript_dir / f"chunk_{index + 1:03d}_transcript.txt"
        chunk_transcript_path.write_text(chunk_transcript, encoding="utf-8")

        overlap_note = ""
        if index > 0 and CHUNK_OVERLAP_SECONDS > 0:
            overlap_note = (
                f"This chunk starts at {format_ts(chunk_start)} and overlaps approximately "
                f"{CHUNK_OVERLAP_SECONDS} seconds with the previous chunk. "
                "Repeated content near the beginning is likely boundary context, not a new decision."
            )

        full_transcript_parts.append(
            f"\n\n# {chunk_name} — starts at {format_ts(chunk_start)}"
            f" — overlap with previous: {chunk.get('overlap_seconds', 0)}s\n\n{chunk_transcript}"
        )

        print(f"Summarizing chunk {index + 1}/{len(chunks)} with rolling context...")
        chunk_summary = summarize_chunk(
            client=client,
            transcript_text=chunk_transcript,
            chunk_name=chunk_name,
            previous_context=rolling_context,
            overlap_notice=overlap_note,
        )

        chunk_summary_path = summary_dir / f"chunk_{index + 1:03d}_summary.md"
        chunk_summary_path.write_text(chunk_summary, encoding="utf-8")

        chunk_summaries.append(chunk_summary)

        print(f"Updating rolling context after chunk {index + 1}/{len(chunks)}...")
        rolling_context = update_rolling_context(
            client=client,
            previous_context=rolling_context,
            new_chunk_summary=chunk_summary,
            chunk_name=chunk_name,
        )

        rolling_context_path = run_dir / "03a_rolling_context.md"
        rolling_context_path.write_text(rolling_context, encoding="utf-8")

    full_raw_path = run_dir / "01_full_raw_diarized_chunks.json"
    full_raw_path.write_text(json.dumps(all_raw, indent=2, ensure_ascii=False), encoding="utf-8")

    full_transcript = "\n".join(full_transcript_parts).strip()

    full_transcript_path = run_dir / "02_full_merged_speaker_transcript.txt"
    full_transcript_path.write_text(full_transcript, encoding="utf-8")

    print("")
    print("Reconciling speakers across chunks...")

    reconciliation = reconcile_speakers(
        client=client,
        raw_records=all_raw,
        full_transcript=full_transcript,
    )

    reconciliation_path = run_dir / "02a_speaker_reconciliation.json"
    reconciliation_path.write_text(
        json.dumps(reconciliation, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if reconciliation.get("status") == "success":
        reconciled_utterances = apply_reconciliation_to_utterances(all_raw, reconciliation)
        reconciled_transcript = render_transcript(reconciled_utterances)
    else:
        reconciled_utterances = []
        reconciled_transcript = full_transcript

    reconciliation_report = render_reconciliation_report(reconciliation, reconciled_utterances)

    reconciliation_report_path = run_dir / "02b_speaker_reconciliation_report.md"
    reconciliation_report_path.write_text(reconciliation_report, encoding="utf-8")

    reconciled_transcript_path = run_dir / "02c_reconciled_speaker_transcript.txt"
    reconciled_transcript_path.write_text(reconciled_transcript, encoding="utf-8")

    speaker_name_map = None
    speaker_name_map_path = None
    named_transcript_path = None
    profile_suggestions = {"status": "skipped", "suggestions": {}, "warnings": []}

    if reconciliation.get("status") == "success" and SPEAKER_PROFILE_SUGGESTIONS:
        speaker_profiles = load_speaker_profiles()
        profile_suggestions = suggest_profile_matches(
            client=client,
            profiles_data=speaker_profiles,
            utterances=reconciled_utterances,
        )
        profile_suggestions_path = run_dir / "02f_speaker_profile_suggestions.json"
        profile_suggestions_path.write_text(
            json.dumps(profile_suggestions, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    elif not SPEAKER_PROFILE_SUGGESTIONS:
        print("Skipping speaker profile suggestions because VOICE_TRANSCRIPTION_SPEAKER_PROFILE_SUGGESTIONS is false.")

    if INTERACTIVE_SPEAKER_NAMING:
        speaker_name_map = prompt_for_speaker_names(
            reconciliation,
            reconciled_utterances,
            profile_suggestions=profile_suggestions,
        )
        if speaker_name_map is not None:
            speaker_name_map_path = run_dir / "02d_speaker_name_map.json"
            speaker_name_map_path.write_text(
                json.dumps(speaker_name_map, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            speaker_profiles = load_speaker_profiles()
            if update_profiles_from_user_names(
                speaker_profiles,
                speaker_name_map,
                reconciled_utterances,
                run_name=run_name,
                input_file=audio_path,
            ):
                save_speaker_profiles(speaker_profiles)
                print("Updated local speaker profiles from user-confirmed names.")

            display_names = name_map_to_display_names(speaker_name_map)
            if display_names:
                named_transcript_path = run_dir / "02e_named_speaker_transcript.txt"
                named_transcript_path.write_text(
                    render_transcript(reconciled_utterances, display_names),
                    encoding="utf-8",
                )
    else:
        print("Skipping interactive speaker naming because VOICE_TRANSCRIPTION_INTERACTIVE_SPEAKER_NAMING is false.")

    all_chunk_summaries = "\n\n---\n\n".join(chunk_summaries)

    all_chunk_summaries_path = run_dir / "03_all_chunk_summaries.md"
    all_chunk_summaries_path.write_text(all_chunk_summaries, encoding="utf-8")

    print("")
    print("Creating final meeting notes...")

    final_notes = create_final_notes(
        client=client,
        all_chunk_summaries=all_chunk_summaries,
        full_transcript_path=full_transcript_path,
        rolling_context=rolling_context,
        speaker_reconciliation_report=reconciliation_report,
        reconciled_transcript_path=reconciled_transcript_path,
        named_transcript_path=named_transcript_path,
        speaker_name_map=speaker_name_map,
    )

    final_notes_path = run_dir / "04_final_meeting_notes.md"
    final_notes_path.write_text(final_notes, encoding="utf-8")

    mind_map_json_path = None
    mind_map_markdown_path = None
    if CREATE_MIND_MAP:
        print("")
        print("Creating mind map...")
        mind_map = create_mind_map(
            client=client,
            final_notes=final_notes,
            all_chunk_summaries=all_chunk_summaries,
            rolling_context=rolling_context,
            speaker_reconciliation_report=reconciliation_report,
        )
        mind_map_json_path = run_dir / "05_mind_map.json"
        mind_map_json_path.write_text(json.dumps(mind_map, indent=2, ensure_ascii=False), encoding="utf-8")
        mind_map_markdown_path = run_dir / "05_mind_map.md"
        mind_map_markdown_path.write_text(render_mind_map_markdown(mind_map), encoding="utf-8")
    else:
        print("Skipping mind map because VOICE_TRANSCRIPTION_CREATE_MIND_MAP is false.")

    run_readme = f"""
# Voice Transcription Run

Input file:

{audio_path}

Output files:

1. `01_full_raw_diarized_chunks.json`
   - Raw JSON for all transcribed chunks.

2. `02_full_merged_speaker_transcript.txt`
   - Original full timestamped transcript with chunk-local speaker labels.

3. `02a_speaker_reconciliation.json`
   - Validated structured speaker reconciliation data.

4. `02b_speaker_reconciliation_report.md`
   - Human-readable speaker mapping report with confidence and uncertainty notes.

5. `02c_reconciled_speaker_transcript.txt`
   - Timestamped transcript with stable meeting-wide generic speaker labels.

6. `02d_speaker_name_map.json`
   - User-entered speaker names, if interactive speaker naming ran.

7. `02e_named_speaker_transcript.txt`
   - Transcript with user-confirmed speaker names, if any names were entered.

8. `02f_speaker_profile_suggestions.json`
   - Conservative known-speaker profile suggestions, if local profiles exist.

9. `03_all_chunk_summaries.md`
   - Summaries for each chunk.

10. `03a_rolling_context.md`
   - Compact context carried forward between chunks.

11. `04_final_meeting_notes.md`
   - Final meeting notes.

11. `05_mind_map.json`
   - Structured topic map, if mind map generation is enabled.

12. `05_mind_map.md`
   - Human-readable topic map, if mind map generation is enabled.

Chunking behavior:

- Chunk length: {CHUNK_SECONDS} seconds
- Overlap: {CHUNK_OVERLAP_SECONDS} seconds

The overlap reduces context loss around boundaries. The summarization prompts are told to treat repeated overlapped content as context, not as new decisions.

Important note about speakers:

Because huge files are split into chunks, speaker labels may reset between chunks. For example, Speaker 1 in Chunk 1 may not always be the same person as Speaker 1 in Chunk 4.

This run includes conservative speaker reconciliation. The app writes stable generic speaker labels first, then optionally asks for user-confirmed names. It does not invent real names when evidence is unclear.

If you enter names, they are saved in a local ignored `speaker_profiles.json` file. Future runs may show those names as suggestions, but the app still requires user confirmation before applying them.
""".strip()

    (run_dir / "README.md").write_text(run_readme, encoding="utf-8")

    index_entry = build_run_index_entry(
        run_dir=run_dir,
        metadata=metadata,
        final_notes=final_notes,
        full_transcript_path=full_transcript_path,
        reconciled_transcript_path=reconciled_transcript_path,
        named_transcript_path=named_transcript_path,
        speaker_name_map=speaker_name_map,
        reconciliation=reconciliation,
    )
    upsert_run_index_entry(index_entry)

    print("")
    print("Done.")
    print("")
    print("Created folder:")
    print(run_dir)
    print("")
    print("Final notes:")
    print(final_notes_path)
    print("")
    print("Full transcript:")
    print(full_transcript_path)
    print("")
    print("Rolling context:")
    print(run_dir / "03a_rolling_context.md")


if __name__ == "__main__":
    main()
