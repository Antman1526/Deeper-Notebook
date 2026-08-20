import pytest

from deeper_notebook.exceptions import InvalidInputError
from deeper_notebook.studio.payloads import (
    artifact_markdown,
    build_structured_payload,
    parse_payload_document,
)
from deeper_notebook.studio.schemas import (
    FlashcardsDocument,
    parse_artifact_document,
)


def _document() -> FlashcardsDocument:
    return parse_artifact_document(
        "flashcards",
        {
            "schema_version": 1,
            "artifact_type": "flashcards",
            "title": "RAG review",
            "cards": [
                {
                    "front": "What is retrieval?",
                    "back": "Finding relevant passages.",
                    "citations": ["[S1]"],
                }
            ],
        },
    )


def test_legacy_content_remains_readable():
    assert artifact_markdown({"content": "# Legacy"}) == "# Legacy"


def test_structured_markdown_takes_precedence_over_content_alias():
    assert (
        artifact_markdown({"markdown": "# Structured", "content": "# Compatibility"})
        == "# Structured"
    )


def test_new_payload_keeps_legacy_content_alias_and_extras():
    payload = build_structured_payload(
        _document(),
        "# Cards",
        extras={"study_progress": {"index": 1}},
    )

    assert payload["schema_version"] == 1
    assert payload["content"] == "# Cards"
    assert payload["markdown"] == "# Cards"
    assert payload["document"]["artifact_type"] == "flashcards"
    assert payload["validation"] == {"status": "valid", "errors": []}
    assert payload["study_progress"] == {"index": 1}


def test_parse_payload_document_returns_typed_document():
    payload = build_structured_payload(_document(), "# Cards")

    parsed = parse_payload_document("flashcards", payload)

    assert isinstance(parsed, FlashcardsDocument)


def test_parse_payload_document_returns_none_for_legacy_payload():
    assert parse_payload_document("report", {"content": "# Legacy"}) is None


def test_parse_payload_document_rejects_missing_document():
    with pytest.raises(InvalidInputError, match="missing document"):
        parse_payload_document(
            "flashcards",
            {"schema_version": 1, "content": "# Broken"},
        )


def test_parse_payload_document_rejects_unknown_schema_version():
    with pytest.raises(InvalidInputError, match="Unsupported artifact schema version"):
        parse_payload_document(
            "flashcards",
            {
                "schema_version": 2,
                "document": {},
                "content": "# Future",
            },
        )


def test_artifact_markdown_ignores_non_string_values():
    assert artifact_markdown({"markdown": {"not": "text"}, "content": 42}) == ""
