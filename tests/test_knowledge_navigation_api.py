"""Canonical, redacted HTTP contracts for knowledge navigation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient

from api.routers.knowledge_navigation import (
    MAX_NAVIGATION_JSON_BYTES,
    _BoundedNavigationRequest,
    _map_exception,
    router,
)
from deeper_notebook.knowledge_engine.navigation_contracts import (
    Bookmark,
    BookmarkFolder,
    HydratedBookmarkPage,
)
from deeper_notebook.knowledge_engine.navigation_repository import (
    KnowledgeNavigationRepositoryError,
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

    async def list_bookmarks(self, *_args) -> HydratedBookmarkPage:
        return HydratedBookmarkPage()


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


def _folder_chain(depth: int) -> list[BookmarkFolder]:
    timestamp = datetime(2026, 7, 31, tzinfo=timezone.utc)
    folders: list[BookmarkFolder] = []
    for index in range(1, depth + 1):
        folder_id = f"knowledge_bookmark_folder:level{index}"
        folders.append(
            BookmarkFolder(
                id=folder_id,
                name=f"Level {index}",
                name_key=f"level {index}",
                parent_folder_id=(
                    None
                    if index == 1
                    else f"knowledge_bookmark_folder:level{index - 1}"
                ),
                position=0,
                revision=1,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    return folders


@pytest.mark.asyncio
@pytest.mark.parametrize(("depth", "expected_status"), [(15, 200), (16, 200), (17, 503)])
async def test_folder_tree_has_an_inclusive_sixteen_level_bound(
    api_client: AsyncClient, depth: int, expected_status: int
) -> None:
    api_client._transport.app.state.knowledge_navigation_service.folders = _folder_chain(depth)

    async with api_client:
        response = await api_client.get(
            "/api/deeper-notebook/knowledge/bookmark-folders"
        )

    assert response.status_code == expected_status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/deeper-notebook/knowledge/bookmarks",
            {
                "operation_id": "book-create-limit",
                "target": {"kind": "search", "query": "research"},
                "display_label": "Research",
            },
        ),
        (
            "/api/deeper-notebook/knowledge/bookmarks/knowledge_bookmark:one",
            {"operation_id": "book-update-limit", "expected_revision": 1},
        ),
        (
            "/api/deeper-notebook/knowledge/bookmarks/knowledge_bookmark:one",
            {"operation_id": "book-delete-limit", "expected_revision": 1},
        ),
        (
            "/api/deeper-notebook/knowledge/bookmark-folders",
            {"operation_id": "folder-create-limit", "name": "Research"},
        ),
        (
            "/api/deeper-notebook/knowledge/bookmark-folders/knowledge_bookmark_folder:one",
            {"operation_id": "folder-update-limit", "expected_revision": 1},
        ),
        (
            "/api/deeper-notebook/knowledge/bookmark-folders/knowledge_bookmark_folder:one",
            {"operation_id": "folder-delete-limit", "expected_revision": 1},
        ),
    ],
)
async def test_all_mutation_routes_reject_json_larger_than_one_mib(
    api_client: AsyncClient, path: str, payload: dict[str, object]
) -> None:
    method = (
        "post"
        if path.endswith(("/bookmarks", "/bookmark-folders"))
        else "patch"
        if "update" in payload["operation_id"]
        else "delete"
    )
    content = json.dumps(payload) + " " * MAX_NAVIGATION_JSON_BYTES
    async with api_client:
        response = await api_client.request(
            method,
            path,
            content=content,
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {"code": "knowledge_navigation_request_invalid"}
    }


@pytest.mark.asyncio
async def test_chunked_body_limit_is_enforced_without_a_content_length() -> None:
    chunks = iter([b"{", b" " * MAX_NAVIGATION_JSON_BYTES])

    async def receive():
        try:
            return {"type": "http.request", "body": next(chunks), "more_body": True}
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}

    request = _BoundedNavigationRequest(
        {"type": "http", "method": "POST", "path": "/", "headers": []}, receive
    )
    with pytest.raises(HTTPException) as error:
        await request.body()

    assert error.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["limit=0", "limit=101", "cursor=not-a-cursor"])
async def test_bookmark_pagination_validation_is_strict_and_scrubbed(
    api_client: AsyncClient, query: str
) -> None:
    async with api_client:
        response = await api_client.get(
            f"/api/deeper-notebook/knowledge/bookmarks?{query}"
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {"code": "knowledge_navigation_request_invalid"}
    }


@pytest.mark.parametrize(
    ("exception", "expected_status"),
    [
        (LookupError("private"), status.HTTP_404_NOT_FOUND),
        (KnowledgeNavigationRepositoryError("not_found"), status.HTTP_404_NOT_FOUND),
        (KnowledgeNavigationRepositoryError("folder_parent_not_found"), status.HTTP_404_NOT_FOUND),
        (KnowledgeNavigationRepositoryError("operation_conflict"), status.HTTP_409_CONFLICT),
        (KnowledgeNavigationRepositoryError("revision_conflict"), status.HTTP_409_CONFLICT),
        (KnowledgeNavigationRepositoryError("folder_cycle"), status.HTTP_409_CONFLICT),
        (KnowledgeNavigationRepositoryError("folder_depth_exceeded"), status.HTTP_409_CONFLICT),
        (ValueError("private"), status.HTTP_422_UNPROCESSABLE_CONTENT),
        (KnowledgeNavigationRepositoryError("knowledge_navigation_repository_unavailable"), status.HTTP_503_SERVICE_UNAVAILABLE),
    ],
)
def test_declared_navigation_error_mapping_matrix_is_stable(
    exception: Exception, expected_status: int
) -> None:
    error = _map_exception(exception)

    assert error.status_code == expected_status
    assert "private" not in str(error.detail)
