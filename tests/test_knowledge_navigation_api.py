"""Canonical, redacted HTTP contracts for knowledge navigation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routers.knowledge_navigation import router
from deeper_notebook.knowledge_engine.navigation_contracts import (
    Bookmark,
    BookmarkFolder,
)


class _NavigationService:
    def __init__(self) -> None:
        self.folders: list[BookmarkFolder] = []

    async def create_bookmark(self, command):
        timestamp = datetime(2026, 7, 31, tzinfo=timezone.utc)
        return Bookmark(
            id="knowledge_bookmark:plan",
            target_kind=command.target.kind,
            target=command.target,
            display_label=command.display_label,
            authority_kind=command.authority_kind,
            space_id=command.space_id,
            folder_id=command.folder_id,
            tags=command.tags,
            position=command.position,
            revision=1,
            created_at=timestamp,
            updated_at=timestamp,
        )

    async def list_folders(self) -> list[BookmarkFolder]:
        return self.folders


@pytest.fixture()
def api_client() -> AsyncClient:
    app = FastAPI()
    app.state.knowledge_navigation_service = _NavigationService()
    app.include_router(router, prefix="/api/deeper-notebook/knowledge")
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_create_bookmark_is_revisioned_and_redacted(
    api_client: AsyncClient,
) -> None:
    async with api_client:
        response = await api_client.post(
            "/api/deeper-notebook/knowledge/bookmarks",
            json={
                "operation_id": "bookmark-create-api-1",
                "target": {
                    "kind": "document",
                    "document_id": "knowledge_engine_document:plan",
                },
                "display_label": "Research plan",
                "folder_id": None,
                "tags": ["Research"],
                "position": 0,
            },
        )

    assert response.status_code == 201
    assert response.json()["revision"] == 1
    assert "/Users/" not in response.text
    assert "normalized_body" not in response.text


@pytest.mark.asyncio
async def test_missing_mutation_body_uses_the_stable_validation_envelope(
    api_client: AsyncClient,
) -> None:
    async with api_client:
        response = await api_client.patch(
            "/api/deeper-notebook/knowledge/bookmarks/knowledge_bookmark:plan"
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {"code": "knowledge_navigation_request_invalid"}
    }


def test_openapi_uses_only_canonical_deeper_notebook_navigation_paths(
    api_client: AsyncClient,
) -> None:
    paths = api_client._transport.app.openapi()["paths"]
    navigation_paths = {
        path: set(methods)
        for path, methods in paths.items()
        if "/knowledge/" in path
    }

    assert navigation_paths == {
        "/api/deeper-notebook/knowledge/bookmarks": {"get", "post"},
        "/api/deeper-notebook/knowledge/bookmarks/{bookmark_id}": {
            "patch",
            "delete",
        },
        "/api/deeper-notebook/knowledge/bookmark-folders": {"get", "post"},
        "/api/deeper-notebook/knowledge/bookmark-folders/{folder_id}": {
            "patch",
            "delete",
        },
    }


@pytest.mark.asyncio
async def test_corrupt_folder_cycle_is_not_silently_omitted(
    api_client: AsyncClient,
) -> None:
    timestamp = datetime(2026, 7, 31, tzinfo=timezone.utc)
    service = api_client._transport.app.state.knowledge_navigation_service
    service.folders = [
        BookmarkFolder(
            id="knowledge_bookmark_folder:first",
            name="First",
            name_key="first",
            parent_folder_id="knowledge_bookmark_folder:second",
            position=0,
            revision=1,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        BookmarkFolder(
            id="knowledge_bookmark_folder:second",
            name="Second",
            name_key="second",
            parent_folder_id="knowledge_bookmark_folder:first",
            position=0,
            revision=1,
            created_at=timestamp,
            updated_at=timestamp,
        ),
    ]

    async with api_client:
        response = await api_client.get(
            "/api/deeper-notebook/knowledge/bookmark-folders"
        )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "knowledge_navigation_unavailable"}}
