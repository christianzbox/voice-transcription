# Voice Transcription

Cross-platform meeting transcription toolkit that turns long audio recordings into speaker-labeled transcripts, summaries, decisions, action items, and polished meeting notes using OpenAI.

## What it does

Voice Transcription takes large meeting recordings, including iPhone Voice Memo `.m4a` files, and produces:

- Raw diarized transcript JSON
- Full timestamped speaker transcript
- Chunk-level summaries
- Rolling context across chunks
- Final meeting notes
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

## Output files

Each run creates a folder like:

    runs/<recording-name>_<timestamp>/

The important files are:

- `01_full_raw_diarized_chunks.json`
- `02_full_merged_speaker_transcript.txt`
- `03_all_chunk_summaries.md`
- `03a_rolling_context.md`
- `04_final_meeting_notes.md`

## Supported audio inputs

Common formats include `.m4a`, `.mp3`, `.mp4`, `.wav`, and `.webm`.

## Tuning

Default chunk length is 10 minutes, default overlap is 45 seconds, and default compressed audio is 48k mono AAC.

macOS/Linux:

    VOICE_TRANSCRIPTION_CHUNK_SECONDS=300 VOICE_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS=30 VOICE_TRANSCRIPTION_AUDIO_BITRATE=32k python -m voice_transcription

Windows PowerShell:

    $env:VOICE_TRANSCRIPTION_CHUNK_SECONDS="300"
    $env:VOICE_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS="30"
    $env:VOICE_TRANSCRIPTION_AUDIO_BITRATE="32k"
    python -m voice_transcription

## Notes about speakers

Large files are split into chunks. Speaker labels can reset between chunks, so `Speaker 1` in chunk 1 may not always be the same person as `Speaker 1` in chunk 4. The final notes prompt avoids inventing owners when identity is unclear.
