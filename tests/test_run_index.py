from pathlib import Path

from voice_transcription.run_index import build_run_index_entry, load_run_index, upsert_run_index_entry


def test_build_run_index_entry_extracts_speakers_and_action_count(tmp_path):
    run_dir = tmp_path / "demo_20260513_120000"
    run_dir.mkdir()

    entry = build_run_index_entry(
        run_dir=run_dir,
        metadata={
            "created_at": "2026-05-13T12:00:00",
            "input_file": "input/demo.m4a",
            "input_duration_seconds": 60,
            "input_size_mb": 1.2,
        },
        final_notes=(
            "# Customer Planning\n\n"
            "## Action Items\n"
            "| Owner | Task | Due date | Evidence / context |\n"
            "| --- | --- | --- | --- |\n"
            "| Christian | Update the PR | Unclear | Said it |\n"
        ),
        full_transcript_path=run_dir / "02_full_merged_speaker_transcript.txt",
        reconciled_transcript_path=run_dir / "02c_reconciled_speaker_transcript.txt",
        named_transcript_path=None,
        speaker_name_map={"speakers": {"Speaker A": {"display_name": "Christian", "source": "user"}}},
        reconciliation={"global_speakers": [{"global_speaker_id": "Speaker A"}]},
    )

    assert entry["title"] == "Customer Planning"
    assert entry["speakers"] == ["Christian"]
    assert entry["action_item_count"] == 1
    assert entry["best_transcript_path"].endswith("02c_reconciled_speaker_transcript.txt")


def test_upsert_run_index_entry_replaces_existing_entry(tmp_path):
    index_path = tmp_path / "index.json"
    entry = {
        "run_name": "demo",
        "created_at": "2026-05-13T12:00:00",
        "title": "First",
    }
    updated = {
        "run_name": "demo",
        "created_at": "2026-05-13T12:01:00",
        "title": "Updated",
    }

    upsert_run_index_entry(entry, index_path)
    upsert_run_index_entry(updated, index_path)
    loaded = load_run_index(index_path)

    assert len(loaded["runs"]) == 1
    assert loaded["runs"][0]["title"] == "Updated"


def test_build_run_index_entry_falls_back_to_generic_speakers(tmp_path):
    run_dir = tmp_path / "demo"
    run_dir.mkdir()

    entry = build_run_index_entry(
        run_dir=run_dir,
        metadata={},
        final_notes="# Meeting Notes",
        full_transcript_path=Path("original.txt"),
        reconciled_transcript_path=None,
        named_transcript_path=None,
        speaker_name_map=None,
        reconciliation={"global_speakers": [{"global_speaker_id": "Speaker A"}]},
    )

    assert entry["title"] == "demo"
    assert entry["speakers"] == ["Speaker A"]
