from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from deeper_notebook.podcasts.selection_contracts import PodcastSelection

selection_adapter = TypeAdapter(PodcastSelection)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "notebook", "notebook_id": "notebook:research"},
        {"kind": "app_note", "note_id": "note:brief"},
        {
            "kind": "app_source",
            "source_id": "source:paper",
            "inclusion_mode": "insights",
        },
        {
            "kind": "knowledge_document",
            "document_id": "knowledge_engine_document:external_note",
            "expected_revision_id": "knowledge_engine_revision:r1",
        },
        {
            "kind": "knowledge_block",
            "document_id": "knowledge_engine_document:external_note",
            "block_id": "knowledge_engine_block:claim",
            "expected_revision_id": "knowledge_engine_revision:r1",
            "source_start": 2,
            "source_end": 12,
        },
        {
            "kind": "knowledge_collection",
            "collection_kind": "bookmark",
            "collection_id": "knowledge_bookmark:research",
        },
        {
            "kind": "saved_search",
            "query": "local research",
            "search_mode": "semantic",
            "space_ids": ["knowledge_engine_space:overlay"],
            "authority_kinds": ["app_owned", "external_read_only"],
        },
        {
            "kind": "graph_selection",
            "document_ids": [
                "knowledge_engine_document:one",
                "knowledge_engine_document:two",
            ],
        },
    ],
)
def test_selection_variants_accept_stable_references_only(payload):
    selection = selection_adapter.validate_python(payload)

    assert selection.kind == payload["kind"]
    assert "/" not in str(selection.model_dump())


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "notebook", "notebook_id": "/private/notebook"},
        {"kind": "app_note", "note_id": "C:/private/note"},
        {"kind": "app_source", "source_id": "../private/source"},
        {
            "kind": "knowledge_document",
            "document_id": "knowledge_engine_document:one",
            "expected_revision_id": "/private/revision",
        },
        {
            "kind": "knowledge_block",
            "document_id": "knowledge_engine_document:one",
            "block_id": "knowledge_engine_block:two",
            "source_start": 8,
            "source_end": 3,
        },
        {
            "kind": "saved_search",
            "query": "research",
            "search_mode": "text",
            "space_ids": ["/private/space"],
            "authority_kinds": [],
        },
        {"kind": "graph_selection", "document_ids": []},
    ],
)
def test_selection_variants_reject_paths_and_invalid_ranges(payload):
    with pytest.raises(ValidationError):
        selection_adapter.validate_python(payload)


def test_selection_contract_rejects_unknown_fields_and_wrong_collection_id():
    with pytest.raises(ValidationError):
        selection_adapter.validate_python(
            {
                "kind": "notebook",
                "notebook_id": "notebook:research",
                "canonical_path": "/private/source.md",
            }
        )
    with pytest.raises(ValidationError):
        selection_adapter.validate_python(
            {
                "kind": "knowledge_collection",
                "collection_kind": "workspace",
                "collection_id": "knowledge_bookmark:research",
            }
        )


@pytest.mark.parametrize(
    "query",
    [
        "Read /Users/Antman/Private.md before recording.",
        r"Read C:\Users\Antman\Private.md before recording.",
        r"Read \\server\share\Private.md before recording.",
        "Read //server/share/Private.md before recording.",
        "Read file:///Users/Antman/Private.md before recording.",
    ],
)
def test_saved_search_rejects_embedded_absolute_paths(query: str):
    with pytest.raises(ValidationError):
        selection_adapter.validate_python(
            {
                "kind": "saved_search",
                "query": query,
                "search_mode": "text",
                "space_ids": ["knowledge_engine_space:overlay"],
                "authority_kinds": ["external_read_only"],
            }
        )


def test_saved_search_preserves_slash_prose_and_https_urls():
    query = "Compare pros/cons and/or 1/2 at https://example.com/guide."
    selection = selection_adapter.validate_python(
        {
            "kind": "saved_search",
            "query": query,
            "search_mode": "text",
            "space_ids": ["knowledge_engine_space:overlay"],
            "authority_kinds": ["external_read_only"],
        }
    )

    assert selection.query == query


def test_selection_contract_bounds_graph_and_search_scopes():
    graph_ids = [f"knowledge_engine_document:{index}" for index in range(129)]
    with pytest.raises(ValidationError):
        selection_adapter.validate_python(
            {"kind": "graph_selection", "document_ids": graph_ids}
        )

    space_ids = [f"knowledge_engine_space:{index}" for index in range(33)]
    with pytest.raises(ValidationError):
        selection_adapter.validate_python(
            {
                "kind": "saved_search",
                "query": "research",
                "search_mode": "text",
                "space_ids": space_ids,
                "authority_kinds": [],
            }
        )
