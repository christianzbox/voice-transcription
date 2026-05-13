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


def test_get_summary_template_reads_custom_template_by_name(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "customer-retro.md").write_text("Focus on blockers and follow-up themes.", encoding="utf-8")

    name, instructions = get_summary_template("customer-retro", template_dir=template_dir)

    assert name == "customer-retro"
    assert instructions == "Focus on blockers and follow-up themes."


def test_get_summary_template_reads_custom_template_by_path(tmp_path):
    template_path = tmp_path / "exec-review.md"
    template_path.write_text("Prioritize decisions and owner-level risks.", encoding="utf-8")

    name, instructions = get_summary_template(str(template_path))

    assert name == "exec-review"
    assert "owner-level risks" in instructions


def test_available_template_names_includes_custom_templates(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "README.md").write_text("ignored", encoding="utf-8")
    (template_dir / "support-call.md").write_text("Support call instructions.", encoding="utf-8")

    names = available_template_names(template_dir=template_dir)

    assert "support-call" in names
    assert "README" not in names
