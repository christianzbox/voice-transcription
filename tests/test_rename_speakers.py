import json

from voice_transcription.rename_speakers import _load_profile_suggestions


def test_load_profile_suggestions_returns_saved_suggestions(tmp_path):
    suggestions_path = tmp_path / "02f_speaker_profile_suggestions.json"
    suggestions_path.write_text(
        json.dumps(
            {
                "status": "success",
                "suggestions": {
                    "Speaker A": {
                        "profile_id": "christian",
                        "suggested_name": "Christian",
                        "confidence": "medium",
                    }
                },
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )

    loaded = _load_profile_suggestions(tmp_path)

    assert loaded["status"] == "success"
    assert loaded["suggestions"]["Speaker A"]["suggested_name"] == "Christian"


def test_load_profile_suggestions_skips_missing_file(tmp_path):
    loaded = _load_profile_suggestions(tmp_path)

    assert loaded == {"status": "skipped", "suggestions": {}, "warnings": []}


def test_load_profile_suggestions_does_not_break_on_bad_json(tmp_path):
    suggestions_path = tmp_path / "02f_speaker_profile_suggestions.json"
    suggestions_path.write_text("{not json", encoding="utf-8")

    loaded = _load_profile_suggestions(tmp_path)

    assert loaded["status"] == "failed"
    assert loaded["suggestions"] == {}
    assert "Could not read" in loaded["warnings"][0]
