from voice_transcription.run_artifacts import best_transcript_path, read_text_if_exists


def test_best_transcript_path_prefers_named_then_reconciled_then_original(tmp_path):
    original = tmp_path / "02_full_merged_speaker_transcript.txt"
    reconciled = tmp_path / "02c_reconciled_speaker_transcript.txt"
    named = tmp_path / "02e_named_speaker_transcript.txt"

    original.write_text("original", encoding="utf-8")
    assert best_transcript_path(tmp_path) == original

    reconciled.write_text("reconciled", encoding="utf-8")
    assert best_transcript_path(tmp_path) == reconciled

    named.write_text("named", encoding="utf-8")
    assert best_transcript_path(tmp_path) == named


def test_read_text_if_exists_returns_empty_string_for_missing_file(tmp_path):
    assert read_text_if_exists(tmp_path / "missing.txt") == ""
