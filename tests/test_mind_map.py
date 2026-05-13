from voice_transcription.mind_map import render_mind_map_markdown


def test_render_mind_map_markdown_with_topic_sections():
    markdown = render_mind_map_markdown(
        {
            "title": "Planning Call",
            "topics": [
                {
                    "topic": "Workflow",
                    "summary": "The workflow was reviewed.",
                    "speakers": ["Speaker A", "Speaker B"],
                    "key_points": ["Keep the process simple."],
                    "decisions": ["Use the existing branch order."],
                    "action_items": [{"owner": "Speaker A", "task": "Update the PR", "due_date": "Unclear"}],
                    "open_questions": ["Who reviews it?"],
                    "risks": ["Speaker identity is uncertain."],
                }
            ],
            "warnings": ["Review speaker labels."],
        }
    )

    assert markdown.startswith("# Planning Call")
    assert "## Workflow" in markdown
    assert "Speakers: Speaker A, Speaker B" in markdown
    assert "- Speaker A: Update the PR (Due: Unclear)" in markdown
    assert "## Warnings" in markdown


def test_render_empty_mind_map():
    markdown = render_mind_map_markdown({"title": "Empty", "topics": []})

    assert "No topics were generated." in markdown
