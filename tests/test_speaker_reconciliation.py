from voice_transcription.speaker_reconciliation import (
    apply_reconciliation_to_utterances,
    name_map_to_display_names,
    render_transcript,
    validate_reconciliation_result,
)


def raw_records():
    return [
        {
            "chunk_index": 0,
            "chunk_name": "Chunk 1",
            "offset_seconds": 0,
            "transcription": {
                "segments": [
                    {"speaker": "Speaker 1", "start": 1, "end": 4, "text": "I will handle the pull request."},
                    {"speaker": "Speaker 2", "start": 5, "end": 7, "text": "That works for me."},
                ]
            },
        },
        {
            "chunk_index": 1,
            "chunk_name": "Chunk 2",
            "offset_seconds": 600,
            "transcription": {
                "segments": [
                    {"speaker": "Speaker 2", "start": 1, "end": 3, "text": "I handled the pull request."},
                    {"speaker": "Speaker 1", "start": 4, "end": 6, "text": "Thanks for doing that."},
                ]
            },
        },
    ]


def test_validation_downgrades_weak_real_name_and_fills_missing_mappings():
    result = validate_reconciliation_result(
        {
            "global_speakers": [
                {
                    "global_speaker_id": "Speaker A",
                    "confidence": "high",
                    "possible_real_name": "Christian",
                    "name_evidence": "none",
                    "reasoning": "Weak evidence.",
                }
            ],
            "mappings": [
                {
                    "chunk_index": 0,
                    "chunk_name": "Chunk 1",
                    "local_speaker": "Speaker 1",
                    "global_speaker_id": "Speaker A",
                    "confidence": "definitely",
                    "reasoning": "Same PR ownership.",
                },
                {
                    "chunk_index": 99,
                    "chunk_name": "Missing",
                    "local_speaker": "Speaker 9",
                    "global_speaker_id": "Speaker Z",
                    "confidence": "high",
                    "reasoning": "Invalid.",
                },
            ],
            "warnings": "single warning",
        },
        raw_records(),
    )

    assert result["status"] == "success"
    assert result["global_speakers"][0]["possible_real_name"] is None
    assert any("Downgraded possible real name" in warning for warning in result["validation_warnings"])
    assert any("unknown speaker" in warning for warning in result["validation_warnings"])
    assert result["warnings"] == ["single warning"]
    assert len(result["mappings"]) == 4

    model_mapping = next(mapping for mapping in result["mappings"] if mapping["source"] == "model")
    assert model_mapping["confidence"] == "low"

    fallback_mappings = [mapping for mapping in result["mappings"] if mapping["source"] == "deterministic_fallback"]
    assert len(fallback_mappings) == 3


def test_reconciled_and_named_transcript_rendering():
    reconciliation = validate_reconciliation_result(
        {
            "global_speakers": [
                {"global_speaker_id": "Speaker A", "confidence": "high"},
                {"global_speaker_id": "Speaker B", "confidence": "medium"},
            ],
            "mappings": [
                {
                    "chunk_index": 0,
                    "chunk_name": "Chunk 1",
                    "local_speaker": "Speaker 1",
                    "global_speaker_id": "Speaker A",
                    "confidence": "high",
                },
                {
                    "chunk_index": 1,
                    "chunk_name": "Chunk 2",
                    "local_speaker": "Speaker 2",
                    "global_speaker_id": "Speaker A",
                    "confidence": "high",
                },
            ],
        },
        raw_records(),
    )

    utterances = apply_reconciliation_to_utterances(raw_records(), reconciliation)
    transcript = render_transcript(utterances)

    assert "[00:00:01-00:00:04] Speaker A: I will handle the pull request." in transcript
    assert "[00:10:01-00:10:03] Speaker A: I handled the pull request." in transcript

    name_map = {"speakers": {"Speaker A": {"display_name": "Christian", "source": "user"}}}
    named = render_transcript(utterances, name_map_to_display_names(name_map))

    assert "Christian: I will handle the pull request." in named
