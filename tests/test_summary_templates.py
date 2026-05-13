from voice_transcription.summary_templates import available_template_names, get_summary_template


def test_get_summary_template_returns_known_template():
    name, instructions = get_summary_template("engineering")

    assert name == "engineering"
    assert "technical decisions" in instructions


def test_get_summary_template_falls_back_to_meeting():
    name, instructions = get_summary_template("does-not-exist")

    assert name == "meeting"
    assert "meeting-notes" in instructions


def test_available_template_names_are_sorted():
    names = available_template_names()

    assert names == sorted(names)
    assert "sales" in names
