from pathlib import Path

from voice_transcription.speaker_profiles import (
    load_speaker_profiles,
    save_speaker_profiles,
    update_profiles_from_user_names,
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
