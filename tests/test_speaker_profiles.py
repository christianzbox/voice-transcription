from pathlib import Path

from voice_transcription.speaker_profiles import (
    add_reference_clip_to_profile,
    load_speaker_profiles,
    profile_id_for_display_name,
    save_speaker_profiles,
    suggest_reference_clip_matches,
    update_profiles_from_user_names,
    validate_profile_match_suggestions,
)


def test_update_profiles_from_user_confirmed_names(tmp_path):
    profile_path = tmp_path / "speaker_profiles.json"
    data = load_speaker_profiles(profile_path)

    changed = update_profiles_from_user_names(
        data,
        {"speakers": {"Speaker A": {"display_name": "Christian", "source": "user"}}},
        [{"global_speaker_id": "Speaker A", "start_seconds": 4, "text": "I will handle the pull request."}],
        run_name="demo_run",
        input_file=Path("input/demo.m4a"),
    )
    save_speaker_profiles(data, profile_path)
    loaded = load_speaker_profiles(profile_path)

    assert changed is True
    assert loaded["profiles"]["christian"]["display_name"] == "Christian"
    assert loaded["profiles"]["christian"]["run_count"] == 1
    assert loaded["profiles"]["christian"]["examples"][0]["timestamp"] == "00:00:04"


def test_ignores_generic_or_non_user_names(tmp_path):
    data = load_speaker_profiles(tmp_path / "missing.json")

    changed = update_profiles_from_user_names(
        data,
        {
            "speakers": {
                "Speaker A": {"display_name": "Speaker A", "source": "generic"},
                "Speaker B": {"display_name": "Boss", "source": "model"},
            }
        },
        [{"global_speaker_id": "Speaker A", "start_seconds": 1, "text": "Hello there."}],
        run_name="demo_run",
        input_file=Path("input/demo.m4a"),
    )

    assert changed is False
    assert data["profiles"] == {}


def test_add_reference_clip_to_profile_copies_audio_and_updates_metadata(tmp_path):
    source = tmp_path / "christian.m4a"
    source.write_bytes(b"fake audio")
    clips_dir = tmp_path / "speaker_reference_clips"
    data = load_speaker_profiles(tmp_path / "missing.json")

    result = add_reference_clip_to_profile(
        data,
        display_name="Christian",
        source_audio_path=source,
        transcript_text="This is my reference sample.",
        clips_dir=clips_dir,
    )

    stored_file = Path(result["stored_file"])
    profile = data["profiles"]["christian"]

    assert result["profile_id"] == "christian"
    assert stored_file.exists()
    assert stored_file.read_bytes() == b"fake audio"
    assert profile["reference_clip_count"] == 1
    assert profile["reference_clips"][0]["transcript"] == "This is my reference sample."


def test_add_reference_clip_rejects_unsupported_file_type(tmp_path):
    source = tmp_path / "christian.txt"
    source.write_text("not audio", encoding="utf-8")
    data = load_speaker_profiles(tmp_path / "missing.json")

    try:
        add_reference_clip_to_profile(data, display_name="Christian", source_audio_path=source)
    except ValueError as exc:
        assert "Unsupported reference clip extension" in str(exc)
    else:
        raise AssertionError("Expected unsupported file type to raise ValueError.")


def test_profile_id_for_display_name_is_stable():
    assert profile_id_for_display_name("Christian Zbox") == "christian-zbox"


def test_validate_profile_match_suggestions_rejects_unknown_profile_and_speaker():
    profiles = {
        "profiles": {
            "christian": {
                "display_name": "Christian",
            }
        }
    }
    utterances = [{"global_speaker_id": "Speaker A", "text": "I will handle the pull request."}]

    result = validate_profile_match_suggestions(
        {
            "suggestions": [
                {
                    "global_speaker_id": "Speaker A",
                    "profile_id": "christian",
                    "confidence": "certain",
                    "reasoning": "Supported by text.",
                },
                {
                    "global_speaker_id": "Speaker B",
                    "profile_id": "christian",
                    "confidence": "high",
                    "reasoning": "Unknown speaker.",
                },
                {
                    "global_speaker_id": "Speaker A",
                    "profile_id": "missing",
                    "confidence": "high",
                    "reasoning": "Unknown profile.",
                },
            ],
            "warnings": ["Review manually."],
        },
        profiles,
        utterances,
    )

    assert result["status"] == "success"
    assert result["suggestions"]["Speaker A"]["suggested_name"] == "Christian"
    assert result["suggestions"]["Speaker A"]["confidence"] == "low"
    assert any("unknown speaker" in warning for warning in result["warnings"])
    assert any("unknown profile" in warning for warning in result["warnings"])
    assert "Review manually." in result["warnings"]


def test_reference_clip_matching_skips_without_reference_transcripts():
    result = suggest_reference_clip_matches(
        client=object(),
        profiles_data={"profiles": {"christian": {"display_name": "Christian", "reference_clips": []}}},
        utterances=[{"global_speaker_id": "Speaker A", "text": "Hello."}],
    )

    assert result["status"] == "skipped"
    assert "No speaker reference clips" in result["warnings"][0]
