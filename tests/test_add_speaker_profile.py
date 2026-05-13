from voice_transcription.add_speaker_profile import _transcription_to_text


def test_transcription_to_text_prefers_top_level_text():
    assert _transcription_to_text({"text": "Hello from the reference clip."}) == "Hello from the reference clip."


def test_transcription_to_text_falls_back_to_segments():
    data = {
        "segments": [
            {"text": "Hello there."},
            {"text": ""},
            {"text": "This is my reference sample."},
        ]
    }

    assert _transcription_to_text(data) == "Hello there. This is my reference sample."
