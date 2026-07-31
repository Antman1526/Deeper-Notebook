"""Hydration behavior for global, content-free navigation metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from deeper_notebook.knowledge_engine.navigation_contracts import (
    BlockTarget,
    Bookmark,
    BookmarkFilters,
    BookmarkPage,
    DocumentTarget,
    GraphTarget,
    KnowledgeOpenDescriptor,
)
from deeper_notebook.knowledge_engine.navigation_repository import (
    KnowledgeNavigationRepositoryError,
)
from deeper_notebook.knowledge_engine.navigation_service import (
    KnowledgeNavigationService,
)


class _MetadataRepository:
    async def list_bookmarks(self, _filters, _cursor, _limit):
        timestamp = datetime(2026, 7, 31, tzinfo=timezone.utc)
        return BookmarkPage(
            items=[
                Bookmark(
                    id="knowledge_bookmark:plan",
                    target_kind="document",
                    target={
                        "kind": "document",
                        "document_id": "knowledge_engine_document:plan",
                    },
                    display_label="Research plan",
                    tags=["Research"],
                    position=0,
                    revision=1,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            ]
        )


class UnavailableEngineRepository:
    async def get_document(self, _document_id):
        raise KnowledgeNavigationRepositoryError("knowledge_engine_unavailable")


class _Engine:
    def __init__(self) -> None:
        self.document: object | Exception = SimpleNamespace(
            source_revision_id="knowledge_engine_revision:current"
        )
        self.descriptor: object | Exception | None = KnowledgeOpenDescriptor(
            document_id="knowledge_engine_document:plan",
            space_id="knowledge_engine_space:primary",
            authority_kind="external_read_only",
            source_kind="markdown",
            title="Plan",
            relative_locator="Plans/Research.md",
            legacy_note_id="note:plan",
            legacy_container_id="vault_mount:primary",
        )
        self.current_block: object | Exception | None = SimpleNamespace(
            block_id="knowledge_engine_block:plan",
            document_id="knowledge_engine_document:plan",
            source_revision_id="knowledge_engine_revision:current",
        )

    async def get_document(self, _document_id: str):
        if isinstance(self.document, Exception):
            raise self.document
        return self.document

    async def open_descriptor(self, _document_id: str):
        if isinstance(self.descriptor, Exception):
            raise self.descriptor
        return self.descriptor

    async def get_current_block(self, **_kwargs):
        if isinstance(self.current_block, Exception):
            raise self.current_block
        return self.current_block


@pytest.fixture()
def service() -> KnowledgeNavigationService:
    return KnowledgeNavigationService(metadata_repository=_MetadataRepository())


@pytest.mark.asyncio
async def test_bookmark_collection_keeps_unavailable_metadata(
    service: KnowledgeNavigationService,
) -> None:
    service.engine_repository = UnavailableEngineRepository()

    page = await service.list_bookmarks(BookmarkFilters(), cursor=None, limit=50)

    assert page.items[0].display_label == "Research plan"
    assert page.items[0].target_state == "unavailable"
    assert page.items[0].target_document is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("document", "current_block", "revision_hint", "expected"),
    [
        ("current", "matching", None, "available"),
        ("current", None, None, "stale"),
        ("current", "wrong-document", None, "stale"),
        ("current", "wrong-revision", None, "stale"),
        ("current", "matching", "knowledge_engine_revision:stale", "stale"),
        ("missing", "matching", None, "missing"),
        ("unavailable", "matching", None, "unavailable"),
    ],
)
async def test_block_hydration_has_a_complete_current_revision_state_matrix(
    service: KnowledgeNavigationService,
    document: str,
    current_block: str | None,
    revision_hint: str | None,
    expected: str,
) -> None:
    engine = _Engine()
    if document == "missing":
        engine.document = LookupError("private document detail")
    elif document == "unavailable":
        engine.document = KnowledgeNavigationRepositoryError("private repository detail")
    engine.current_block = (
        engine.current_block if current_block == "matching" else None
    )
    if current_block == "wrong-document":
        engine.current_block = SimpleNamespace(
            document_id="knowledge_engine_document:other",
            source_revision_id="knowledge_engine_revision:current",
        )
    elif current_block == "wrong-revision":
        engine.current_block = SimpleNamespace(
            document_id="knowledge_engine_document:plan",
            source_revision_id="knowledge_engine_revision:stale",
        )
    service.engine_repository = engine

    hydrated = await service.hydrate_target(
        BlockTarget(
            document_id="knowledge_engine_document:plan",
            block_id="knowledge_engine_block:plan",
            source_revision_id=revision_hint,
        )
    )

    assert hydrated.state == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("descriptor", "document", "expected"),
    [
        ("present", "current", "available"),
        ("missing", "current", "stale"),
        ("present", "missing", "missing"),
        ("present", "unavailable", "unavailable"),
    ],
)
async def test_rooted_graph_hydration_preserves_the_graph_target_and_root_state(
    service: KnowledgeNavigationService,
    descriptor: str,
    document: str,
    expected: str,
) -> None:
    engine = _Engine()
    engine.descriptor = None if descriptor == "missing" else engine.descriptor
    if document == "missing":
        engine.document = LookupError("private document detail")
    elif document == "unavailable":
        engine.document = KnowledgeNavigationRepositoryError("private repository detail")
    service.engine_repository = engine

    graph = GraphTarget(root_document_id="knowledge_engine_document:plan")
    hydrated = await service.hydrate_target(graph)

    assert hydrated.target == graph
    assert hydrated.state == expected


@pytest.mark.asyncio
async def test_global_graph_is_available_without_engine_hydration(
    service: KnowledgeNavigationService,
) -> None:
    assert (await service.hydrate_target(GraphTarget())).state == "available"


@pytest.mark.asyncio
async def test_rooted_graph_uses_a_real_document_target(
    service: KnowledgeNavigationService,
) -> None:
    graph = GraphTarget(root_document_id="knowledge_engine_document:plan")

    async def hydrate_document(target):
        assert isinstance(target, DocumentTarget)
        return await KnowledgeNavigationService._hydrate_document(service, target)

    service.engine_repository = _Engine()
    service._hydrate_document = hydrate_document  # type: ignore[method-assign]

    assert (await service.hydrate_target(graph)).state == "available"


@pytest.mark.asyncio
async def test_one_hydration_failure_does_not_poison_other_bookmark_metadata(
    service: KnowledgeNavigationService,
) -> None:
    timestamp = datetime(2026, 7, 31, tzinfo=timezone.utc)

    async def list_bookmarks(*_args):
        return BookmarkPage(
            items=[
                Bookmark(
                    id="knowledge_bookmark:unavailable",
                    target_kind="document",
                    target={"kind": "document", "document_id": "knowledge_engine_document:plan"},
                    display_label="Unavailable",
                    position=0,
                    revision=1,
                    created_at=timestamp,
                    updated_at=timestamp,
                ),
                Bookmark(
                    id="knowledge_bookmark:available",
                    target_kind="search",
                    target={"kind": "search", "query": "research"},
                    display_label="Available",
                    position=1,
                    revision=1,
                    created_at=timestamp,
                    updated_at=timestamp,
                ),
            ]
        )

    service.metadata_repository.list_bookmarks = list_bookmarks  # type: ignore[method-assign]
    service.engine_repository = UnavailableEngineRepository()

    page = await service.list_bookmarks(BookmarkFilters(), cursor=None, limit=50)

    assert [item.target_state for item in page.items] == ["unavailable", "available"]
