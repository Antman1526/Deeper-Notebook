"""Hydration behavior for global, content-free navigation metadata."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from deeper_notebook.knowledge_engine.navigation_contracts import (
    Bookmark,
    BookmarkFilters,
    BookmarkPage,
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
