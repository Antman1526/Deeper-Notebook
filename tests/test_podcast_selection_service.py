from __future__ import annotations

from dataclasses import dataclass

import pytest

from deeper_notebook.podcasts.selection_contracts import (
    GraphSelection,
    KnowledgeDocumentSelection,
)
from deeper_notebook.podcasts.selection_service import (
    PodcastSelectionService,
    ResolvedSelectionItem,
)


@dataclass
class FakeResolver:
    calls: list[object]

    async def resolve(self, selection):
        self.calls.append(selection)
        if selection.kind == "graph_selection":
            return [
                ResolvedSelectionItem(
                    stable_id=document_id,
                    title=document_id.rsplit(":", 1)[1],
                    authority_kind="app_owned",
                    relative_locator="overlay.md",
                    revision_id="knowledge_engine_revision:app",
                    fingerprint="same-fingerprint",
                    content="app-owned context",
                )
                for document_id in selection.document_ids
            ]
        return [
            ResolvedSelectionItem(
                stable_id=selection.document_id,
                title="External note",
                authority_kind="external_read_only",
                relative_locator="Research/Note.md",
                revision_id="knowledge_engine_revision:external",
                fingerprint="external-fingerprint",
                content="external context",
            )
        ]


@pytest.mark.asyncio
async def test_selection_preview_normalizes_graph_ids_and_deduplicates_content():
    resolver = FakeResolver(calls=[])
    service = PodcastSelectionService(resolver=resolver)

    preview = await service.preview(
        [
            GraphSelection(
                document_ids=[
                    "knowledge_engine_document:zeta",
                    "knowledge_engine_document:alpha",
                    "knowledge_engine_document:zeta",
                ]
            )
        ]
    )

    assert [entry.stable_id for entry in preview.entries] == [
        "knowledge_engine_document:alpha",
        "knowledge_engine_document:zeta",
    ]
    assert [entry.state for entry in preview.entries] == ["included", "duplicate"]
    assert preview.entries[1].reason == "duplicate_content_fingerprint"
    assert preview.selection_fingerprint
    assert resolver.calls[0].document_ids == [
        "knowledge_engine_document:alpha",
        "knowledge_engine_document:zeta",
    ]


@pytest.mark.asyncio
async def test_external_selection_remains_read_only_and_never_exposes_content():
    resolver = FakeResolver(calls=[])
    service = PodcastSelectionService(resolver=resolver)

    preview = await service.preview(
        [
            KnowledgeDocumentSelection(
                document_id="knowledge_engine_document:external",
                expected_revision_id="knowledge_engine_revision:external",
            )
        ]
    )

    entry = preview.entries[0]
    assert entry.authority_kind == "external_read_only"
    assert entry.relative_locator == "Research/Note.md"
    assert "content" not in entry.model_dump()
    assert "write" not in entry.model_dump_json()
