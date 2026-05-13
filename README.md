# Voice Transcription

Cross-platform meeting transcription toolkit that turns long audio recordings into speaker-labeled transcripts, summaries, decisions, action items, and polished meeting notes using OpenAI.

## What it does

Voice Transcription takes large meeting recordings, including iPhone Voice Memo `.m4a` files, and produces:

- Raw diarized transcript JSON
- Full timestamped speaker transcript
- Stable cross-chunk speaker reconciliation
- Optional user-confirmed speaker names
- Local speaker profile suggestions
- Chunk-level summaries
- Rolling context across chunks
- Final meeting notes
- Mind map / topic map
- Decisions
- Action items
- Open questions
- Follow-up email draft

Large files are compressed and split locally with `ffmpeg` before being sent to the transcription API.

## Context-aware chunking

The app uses overlapping chunks by default:

- Default chunk size: 10 minutes
- Default overlap: 45 seconds
- Default audio conversion: 48k mono AAC

The overlap helps preserve meaning around boundaries. For example, chunk 2 may start 45 seconds before chunk 1 ended. The summarization prompts are told to treat repeated audio as context, not as new decisions or duplicate action items.

The app also maintains a `03a_rolling_context.md` file while processing. This carries forward active topics, unresolved questions, decisions, action items, names, and important constraints from chunk to chunk.

## Speaker reconciliation

Large recordings are split into chunks, and diarized labels can reset between chunks. For example, `Speaker 1` in chunk 1 may be a different person than `Speaker 1` in chunk 2.

After transcription, the app runs a conservative reconciliation stage that maps chunk-local labels into stable meeting-wide generic speakers:

    Chunk 1 | Speaker 1 -> Speaker A
    Chunk 1 | Speaker 2 -> Speaker B
    Chunk 2 | Speaker 2 -> Speaker A
    Chunk 2 | Speaker 1 -> Speaker B

The app writes both machine-readable JSON and a human-readable report so the mapping is auditable. If the reconciliation model returns invalid JSON, references unknown speakers, or leaves speakers unmapped, the app downgrades or falls back instead of crashing.

The app does not invent real names. Names are only used when:

- You enter them during the optional naming prompt.
- A speaker self-identifies.
- Another speaker explicitly addresses them.
- The transcript contains strong explicit evidence, and the report explains why.

When evidence is unclear, the app keeps labels such as `Speaker A`, `Speaker B`, or `Unknown Speaker`.

## Optional speaker naming

When running from an interactive terminal, the app shows a short card for each reconciled speaker with first appearance, approximate speaking amount, possible explicit-name evidence, confidence, and representative quotes.

You can enter a name or press Enter to keep the generic label:

    Name for Speaker A, or press Enter to keep generic:

User-entered names are saved to `02d_speaker_name_map.json`. If any names are entered, the app also writes `02e_named_speaker_transcript.txt`. If no names are entered, the named transcript is skipped and the reconciled generic transcript remains the best speaker-labeled transcript.

When you enter a name, the app also updates a local `speaker_profiles.json` file with that user-confirmed name and a few representative quotes. That file is ignored by Git. Future runs can use it to show conservative known-speaker suggestions during the naming prompt.

These suggestions are not automatic voice recognition. They are text-based hints for you to confirm, and pressing Enter keeps the generic label.

You can also save local reference clips for known speakers:

macOS/Linux:

    python -m voice_transcription.add_speaker_profile --name Christian path/to/christian-reference.m4a

Windows PowerShell:

    python -m voice_transcription.add_speaker_profile --name Christian .\path\to\christian-reference.m4a

Reference clips are copied into `speaker_reference_clips/`, and metadata is stored in `speaker_profiles.json`. Both are ignored by Git. This establishes a local profile data model for future voice-aware speaker matching, but the app does not auto-assign names from reference clips yet.

To disable interactive naming:

macOS/Linux:

    VOICE_TRANSCRIPTION_INTERACTIVE_SPEAKER_NAMING=false python -m voice_transcription

Windows PowerShell:

    $env:VOICE_TRANSCRIPTION_INTERACTIVE_SPEAKER_NAMING="false"
    python -m voice_transcription

## Rename speakers after a run

You can fix speaker names later without retranscribing audio:

macOS/Linux:

    python -m voice_transcription.rename_speakers runs/<recording-name>_<timestamp>

Windows PowerShell:

    python -m voice_transcription.rename_speakers .\runs\<recording-name>_<timestamp>

If you omit the run folder, the command uses the newest folder in `runs/`.

For non-interactive updates:

    python -m voice_transcription.rename_speakers runs/<recording-name>_<timestamp> --set "Speaker A=Christian" --set "Speaker B=Sarah"

The command updates `02d_speaker_name_map.json` and rerenders `02e_named_speaker_transcript.txt`. It does not call the transcription API.
If the run has `02f_speaker_profile_suggestions.json`, the interactive rename prompt reuses those saved suggestions.

To disable known-speaker profile suggestions while keeping manual naming:

macOS/Linux:

    VOICE_TRANSCRIPTION_SPEAKER_PROFILE_SUGGESTIONS=false python -m voice_transcription

Windows PowerShell:

    $env:VOICE_TRANSCRIPTION_SPEAKER_PROFILE_SUGGESTIONS="false"
    python -m voice_transcription

## Folder layout

- `voice_transcription/` - Python app
- `input/` - Drop audio files here
- `runs/` - Output appears here
- `scripts/` - macOS and Windows launchers
- `requirements.txt` - Python dependencies

## macOS setup

First time:

    scripts/install-macos.command
    scripts/set-api-key-macos.command

Run:

    scripts/run-macos.command

## Windows setup

First time, in PowerShell:

    .\scripts\install-windows.ps1
    .\scripts\set-api-key-windows.ps1

Run:

    .\scripts\run-windows.ps1

## API key storage

Each user stores their own OpenAI API key locally using Python `keyring`.

- macOS: macOS Keychain / Passwords-backed credential system
- Windows: Windows Credential Manager / Credential Vault

The API key is not stored in the repo.

## Usage

1. Put your audio file into `input/`.
2. Run the app.
3. Open the newest folder in `runs/`.
4. The main output is `04_final_meeting_notes.md`.

After each completed run, the app updates an ignored local index at `runs/index.json`.

List recent indexed runs:

    python -m voice_transcription.library

## Ask questions about a run

After a run completes, you can ask follow-up questions without retranscribing audio:

macOS/Linux:

    python -m voice_transcription.ask runs/<recording-name>_<timestamp> --question "What did Christian commit to?"

Windows PowerShell:

    python -m voice_transcription.ask .\runs\<recording-name>_<timestamp> --question "List all deadlines."

If you omit the run folder, the command uses the newest folder in `runs/`. Answers are appended to `05_ask_answers.md` unless you pass `--no-save`.

## Output files

Each run creates a folder like:

    runs/<recording-name>_<timestamp>/

The important files are:

- `01_full_raw_diarized_chunks.json`
- `02_full_merged_speaker_transcript.txt`
- `02a_speaker_reconciliation.json`
- `02b_speaker_reconciliation_report.md`
- `02c_reconciled_speaker_transcript.txt`
- `02d_speaker_name_map.json` if interactive naming ran
- `02e_named_speaker_transcript.txt` if names were entered
- `02f_speaker_profile_suggestions.json` if profile suggestions ran
- `03_all_chunk_summaries.md`
- `03a_rolling_context.md`
- `04_final_meeting_notes.md`
- `05_mind_map.json`
- `05_mind_map.md`
- `05_ask_answers.md` if you use the ask command

The `runs/` folder is ignored by Git except for `runs/.gitkeep`, so generated outputs are not committed.

## Supported audio inputs

Common formats include `.m4a`, `.mp3`, `.mp4`, `.wav`, and `.webm`.

## Development checks

Install runtime and development dependencies:

    python -m pip install -r requirements.txt -r requirements-dev.txt

Run the same checks as CI:

    python -m ruff format --check .
    python -m ruff check .
    python -m py_compile voice_transcription/*.py
    python -m pytest

Format code locally:

    python -m ruff format .

## Tuning

Default chunk length is 10 minutes, default overlap is 45 seconds, and default compressed audio is 48k mono AAC.

macOS/Linux:

    VOICE_TRANSCRIPTION_CHUNK_SECONDS=300 VOICE_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS=30 VOICE_TRANSCRIPTION_AUDIO_BITRATE=32k python -m voice_transcription

Windows PowerShell:

    $env:VOICE_TRANSCRIPTION_CHUNK_SECONDS="300"
    $env:VOICE_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS="30"
    $env:VOICE_TRANSCRIPTION_AUDIO_BITRATE="32k"
    python -m voice_transcription

Mind map generation is enabled by default. To skip it:

macOS/Linux:

    VOICE_TRANSCRIPTION_CREATE_MIND_MAP=false python -m voice_transcription

Windows PowerShell:

    $env:VOICE_TRANSCRIPTION_CREATE_MIND_MAP="false"
    python -m voice_transcription

## Summary templates

The default final notes format is a general meeting-notes template. You can tune chunk summaries and final notes for a specific meeting type:

- `meeting`
- `engineering`
- `sales`
- `interview`
- `executive`
- `legal`

macOS/Linux:

    VOICE_TRANSCRIPTION_SUMMARY_TEMPLATE=engineering python -m voice_transcription

Windows PowerShell:

    $env:VOICE_TRANSCRIPTION_SUMMARY_TEMPLATE="engineering"
    python -m voice_transcription

You can also create local custom templates. Add a Markdown file under `templates/`:

    templates/customer-retro.md

Then run:

macOS/Linux:

    VOICE_TRANSCRIPTION_SUMMARY_TEMPLATE=customer-retro python -m voice_transcription

Windows PowerShell:

    $env:VOICE_TRANSCRIPTION_SUMMARY_TEMPLATE="customer-retro"
    python -m voice_transcription

The `templates/` folder is ignored by Git except for `templates/.gitkeep`, so personal or customer-specific prompts are not committed. `VOICE_TRANSCRIPTION_SUMMARY_TEMPLATE` can also point directly to a `.md` file path.

## Notes about speakers

Speaker reconciliation is useful but not perfect. Review `02b_speaker_reconciliation_report.md` when speaker identity matters. The final notes prompt uses user-confirmed names first, then reconciled generic speaker labels, then the original merged transcript if reconciliation was unavailable. It also preserves uncertainty and avoids duplicating action items caused by overlap.
