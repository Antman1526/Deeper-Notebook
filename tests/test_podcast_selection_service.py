from __future__ import annotations

from dataclasses import dataclass

import pytest

from deeper_notebook.podcasts.selection_contracts import (
    AppNoteSelection,
    GraphSelection,
    KnowledgeDocumentSelection,
    NotebookSelection,
)
from deeper_notebook.podcasts.selection_service import (
    AppNotebookPodcastSelectionResolver,
    AppNotePodcastSelectionResolver,
    KnowledgeEnginePodcastSelectionResolver,
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


@pytest.mark.asyncio
async def test_engine_resolver_reads_unified_document_projection_without_path_access():
    class Engine:
        async def get_document(self, document_id):
            assert document_id == "knowledge_engine_document:external"
            return type(
                "Document",
                (),
                {
                    "id": document_id,
                    "title": "External note",
                    "authority_kind": "external_read_only",
                    "relative_locator": "Research/Note.md",
                    "source_revision_id": "knowledge_engine_revision:external",
                    "content_hash": "f" * 64,
                    "normalized_body": "read through projection only",
                },
            )()

    resolver = KnowledgeEnginePodcastSelectionResolver(engine=Engine())

    items = await resolver.resolve(
        KnowledgeDocumentSelection(
            document_id="knowledge_engine_document:external",
            expected_revision_id="knowledge_engine_revision:external",
        )
    )

    assert items[0].authority_kind == "external_read_only"
    assert items[0].relative_locator == "Research/Note.md"
    assert items[0].content == "read through projection only"


@pytest.mark.asyncio
async def test_engine_resolver_marks_stale_revision_changed_before_preview():
    class Engine:
        async def get_document(self, document_id):
            return type(
                "Document",
                (),
                {
                    "id": document_id,
                    "title": "Changed note",
                    "authority_kind": "external_read_only",
                    "relative_locator": "Research/Changed.md",
                    "source_revision_id": "knowledge_engine_revision:current",
                    "content_hash": "a" * 64,
                    "normalized_body": "must not be silently included",
                },
            )()

    preview = await PodcastSelectionService(
        resolver=KnowledgeEnginePodcastSelectionResolver(engine=Engine())
    ).preview(
        [
            KnowledgeDocumentSelection(
                document_id="knowledge_engine_document:changed",
                expected_revision_id="knowledge_engine_revision:expected",
            )
        ]
    )

    assert preview.entries[0].state == "changed"
    assert preview.entries[0].reason == "source_revision_changed"
    assert preview.included_characters == 0
    assert preview.current_worker_eligible is False


@pytest.mark.asyncio
async def test_preview_fingerprint_includes_resolved_revision_without_source_body():
    @dataclass
    class RevisionResolver:
        revision_id: str
        content_hash: str

        async def resolve(self, selection):
            return [
                ResolvedSelectionItem(
                    stable_id=selection.document_id,
                    title="Revisioned note",
                    authority_kind="external_read_only",
                    relative_locator="Research/Revisioned.md",
                    revision_id=self.revision_id,
                    fingerprint=self.content_hash,
                    content="content that must not be fingerprint input",
                )
            ]

    selection = KnowledgeDocumentSelection(
        document_id="knowledge_engine_document:revisioned"
    )
    initial = await PodcastSelectionService(
        resolver=RevisionResolver(
            revision_id="knowledge_engine_revision:one", content_hash="1" * 64
        )
    ).preview([selection])
    changed = await PodcastSelectionService(
        resolver=RevisionResolver(
            revision_id="knowledge_engine_revision:two", content_hash="2" * 64
        )
    ).preview([selection])

    assert initial.selection_fingerprint != changed.selection_fingerprint
    assert "content that must not be fingerprint input" not in initial.model_dump_json()


@pytest.mark.asyncio
async def test_prepare_keeps_only_current_non_duplicate_content_server_side():
    resolver = FakeResolver(calls=[])
    service = PodcastSelectionService(resolver=resolver)

    preparation = await service.prepare(
        [
            GraphSelection(
                document_ids=[
                    "knowledge_engine_document:alpha",
                    "knowledge_engine_document:zeta",
                ]
            )
        ]
    )

    assert preparation.content == "app-owned context"
    assert "content" not in preparation.model_dump()
    assert preparation.preview.entries[1].state == "duplicate"


@pytest.mark.asyncio
async def test_app_notebook_resolver_uses_context_api_without_external_path_access():
    class Notebook:
        id = "notebook:research"
        name = "Research notebook"

        async def get_context(self):
            return "app-owned notebook context"

    async def load_notebook(notebook_id: str):
        assert notebook_id == "notebook:research"
        return Notebook()

    items = await AppNotebookPodcastSelectionResolver(
        notebook_loader=load_notebook
    ).resolve(NotebookSelection(notebook_id="notebook:research"))

    assert items[0].authority_kind == "app_owned"
    assert items[0].relative_locator is None
    assert items[0].content == "app-owned notebook context"


@pytest.mark.asyncio
async def test_app_note_resolver_keeps_canonical_external_notes_out_of_app_owned_input():
    class Note:
        id = "note:external"
        title = "External note"
        content = "must remain in the unified external path"
        canonical_external = True

    async def load_note(note_id: str):
        assert note_id == "note:external"
        return Note()

    items = await AppNotePodcastSelectionResolver(note_loader=load_note).resolve(
        AppNoteSelection(note_id="note:external")
    )

    assert items[0].authority_kind == "external_read_only"
    assert items[0].state == "unavailable"
    assert items[0].reason == "external_note_requires_knowledge_selection"
    assert items[0].content == ""
