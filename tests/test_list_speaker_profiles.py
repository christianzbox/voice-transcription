from voice_transcription.list_speaker_profiles import format_speaker_profiles


def test_format_speaker_profiles_lists_counts():
    output = format_speaker_profiles(
        {
            "version": 1,
            "profiles": {
                "christian": {
                    "display_name": "Christian",
                    "updated_at": "2026-05-13T12:00:00",
                    "run_count": 2,
                    "examples": [{"text": "I will handle it."}],
                    "reference_clips": [
                        {"stored_file": "one.m4a", "transcript": "My voice sample."},
                        {"stored_file": "two.m4a", "transcript": ""},
                    ],
                }
            },
        }
    )

    assert "Christian" in output
    assert "- Profile id: christian" in output
    assert "- Runs with user-confirmed examples: 2" in output
    assert "- Stored examples: 1" in output
    assert "- Reference clips: 2" in output
    assert "- Reference clips with transcript text: 1" in output


def test_format_speaker_profiles_handles_empty_store():
    assert format_speaker_profiles({"version": 1, "profiles": {}}) == "No speaker profiles found."
