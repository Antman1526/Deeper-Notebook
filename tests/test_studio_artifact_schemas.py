import pytest
from pydantic import ValidationError

from deeper_notebook.exceptions import InvalidInputError
from deeper_notebook.studio.schemas import (
    CoursePackDocument,
    FlashcardsDocument,
    SlideDeckDocument,
    parse_artifact_document,
    schema_for_artifact_type,
)


def _flashcards_payload() -> dict:
    return {
        "schema_version": 1,
        "artifact_type": "flashcards",
        "title": "RAG review",
        "cards": [
            {
                "front": "What is retrieval?",
                "back": "Finding relevant source passages.",
                "citations": ["[S1]"],
            }
        ],
    }


def test_registry_resolves_supported_artifact_schemas():
    assert schema_for_artifact_type("slide_deck") is SlideDeckDocument
    assert schema_for_artifact_type("course_pack") is CoursePackDocument
    assert schema_for_artifact_type("training_guide") is CoursePackDocument


def test_registry_rejects_podcast_audio_generation():
    with pytest.raises(InvalidInputError, match="podcast_audio"):
        schema_for_artifact_type("podcast_audio")


def test_parse_flashcards_document_returns_typed_model():
    document = parse_artifact_document("flashcards", _flashcards_payload())

    assert isinstance(document, FlashcardsDocument)
    assert document.cards[0].back == "Finding relevant source passages."


def test_parse_flashcards_document_rejects_missing_back():
    payload = _flashcards_payload()
    del payload["cards"][0]["back"]

    with pytest.raises(ValidationError):
        parse_artifact_document("flashcards", payload)


def test_parse_artifact_document_rejects_type_mismatch():
    payload = _flashcards_payload()
    payload["artifact_type"] = "quiz"

    with pytest.raises(ValidationError):
        parse_artifact_document("flashcards", payload)


def test_quiz_rejects_answer_id_not_present_in_options():
    payload = {
        "schema_version": 1,
        "artifact_type": "quiz",
        "title": "RAG quiz",
        "questions": [
            {
                "prompt": "What happens first?",
                "options": [
                    {"id": "a", "text": "Retrieve evidence"},
                    {"id": "b", "text": "Write an unsupported answer"},
                ],
                "correct_option_id": "c",
                "explanation": "Retrieval grounds the answer.",
                "citations": ["[S1]"],
            }
        ],
    }

    with pytest.raises(ValidationError, match="correct_option_id"):
        parse_artifact_document("quiz", payload)


def test_data_table_rejects_row_with_unknown_column():
    payload = {
        "schema_version": 1,
        "artifact_type": "data_table",
        "title": "Evidence",
        "columns": ["Topic", "Evidence"],
        "rows": [
            {
                "values": {
                    "Topic": "RAG",
                    "Evidence": "Retrieval improves grounding.",
                    "Unknown": "not declared",
                },
                "citations": ["[S1]"],
            }
        ],
    }

    with pytest.raises(ValidationError, match="columns"):
        parse_artifact_document("data_table", payload)


def test_course_pack_accepts_legacy_training_guide_discriminator():
    payload = {
        "schema_version": 1,
        "artifact_type": "training_guide",
        "title": "Facilitator guide",
        "audience": "New operators",
        "learning_outcomes": ["Explain the workflow"],
        "modules": [
            {
                "title": "Foundation",
                "summary": "Learn the core workflow.",
                "lessons": [
                    {
                        "title": "Grounding",
                        "content": "Use source evidence.",
                        "citations": ["[S1]"],
                    }
                ],
            }
        ],
    }

    document = parse_artifact_document("training_guide", payload)

    assert isinstance(document, CoursePackDocument)
    assert document.artifact_type == "training_guide"


def test_mind_map_rejects_nodes_deeper_than_eight_levels():
    node = {"label": "level-9", "citations": ["[S1]"], "children": []}
    for level in range(8, 0, -1):
        node = {
            "label": f"level-{level}",
            "citations": ["[S1]"],
            "children": [node],
        }
    payload = {
        "schema_version": 1,
        "artifact_type": "mind_map",
        "title": "Too deep",
        "root": node,
    }

    with pytest.raises(ValidationError, match="depth"):
        parse_artifact_document("mind_map", payload)
