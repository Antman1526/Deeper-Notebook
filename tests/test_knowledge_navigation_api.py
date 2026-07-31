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
    WORKSPACE_CAPACITY_ALLOCATOR_ID,
    Bookmark,
    BookmarkFolder,
    BookmarkPage,
    HydratedBookmarkPage,
    KnowledgeOpenDescriptor,
    NamedKnowledgeWorkspace,
    NamedKnowledgeWorkspaceSummary,
    NavigationReceipt,
    RandomNoteResult,
    WorkspaceRestorePlan,
)
from deeper_notebook.knowledge_engine.navigation_repository import (
    KnowledgeNavigationRepositoryError,
)
from deeper_notebook.knowledge_engine.navigation_service import (
    KnowledgeNavigationService,
    KnowledgeNavigationServiceError,
)


class _NavigationService:
    def __init__(self) -> None:
        self.folders: list[BookmarkFolder] = []
        timestamp = datetime(2026, 7, 31, tzinfo=timezone.utc)
        self.workspace = NamedKnowledgeWorkspace.model_validate(
            {
                "id": "named_knowledge_workspace:desk",
                "name": "Desk",
                "name_key": "desk",
                "capacity_slot": 0,
                "revision": 3,
                "created_at": timestamp,
                "updated_at": timestamp,
                "snapshot": {
                    "active_pane_id": "pane-one",
                    "next_id": 2,
                    "panes": {
                        "pane-one": {
                            "id": "pane-one",
                            "active_tab_id": "tab-search",
                            "tabs": [
                                {
                                    "id": "tab-search",
                                    "display_label": "Research",
                                    "target": {"kind": "search", "query": "research"},
                                }
                            ],
                        }
                    },
                    "layout": {"type": "pane", "pane_id": "pane-one"},
                },
            }
        )
        self.workspaces = {self.workspace.id: self.workspace}
        self.collection_overflow = False
        self.random_note_error: Exception | None = None
        self.random_note_result = RandomNoteResult(state="empty", document=None)

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

    async def random_note(self, _filters) -> RandomNoteResult:
        if self.random_note_error is not None:
            raise self.random_note_error
        return self.random_note_result

    async def list_workspaces(self) -> list[NamedKnowledgeWorkspaceSummary]:
        if self.collection_overflow:
            raise KnowledgeNavigationRepositoryError("workspace_collection_too_large")
        return [
            NamedKnowledgeWorkspaceSummary(
                id=workspace.id,
                name=workspace.name,
                revision=workspace.revision,
                updated_at=workspace.updated_at,
            )
            for workspace in self.workspaces.values()
        ]

    async def create_workspace(self, command) -> NamedKnowledgeWorkspace:
        timestamp = datetime(2026, 7, 31, tzinfo=timezone.utc)
        workspace = NamedKnowledgeWorkspace(
            id=f"named_knowledge_workspace:created_{len(self.workspaces)}",
            name=command.name,
            name_key=command.name_key,
            snapshot=command.snapshot,
            capacity_slot=len(self.workspaces),
            revision=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.workspaces[workspace.id] = workspace
        return workspace

    async def get_workspace(self, workspace_id: str) -> NamedKnowledgeWorkspace:
        try:
            return self.workspaces[workspace_id]
        except KeyError:
            raise LookupError(workspace_id) from None

    async def update_workspace(
        self, workspace_id: str, command
    ) -> NamedKnowledgeWorkspace:
        existing = await self.get_workspace(workspace_id)
        if command.expected_revision != existing.revision:
            raise KnowledgeNavigationRepositoryError("revision_conflict")
        has_name = "name" in command.model_fields_set
        has_snapshot = "snapshot" in command.model_fields_set
        if has_name == has_snapshot:
            raise ValueError("workspace updates must rename or replace a snapshot")
        data = existing.model_dump(mode="python")
        if has_name:
            data.update(name=command.name, name_key=command.name_key)
        else:
            data["snapshot"] = command.snapshot
        data["revision"] = existing.revision + 1
        workspace = NamedKnowledgeWorkspace.model_validate(data)
        self.workspaces[workspace_id] = workspace
        if workspace_id == self.workspace.id:
            self.workspace = workspace
        return workspace

    async def duplicate_workspace(
        self, workspace_id: str, command
    ) -> NamedKnowledgeWorkspace:
        source = await self.get_workspace(workspace_id)
        timestamp = datetime(2026, 7, 31, tzinfo=timezone.utc)
        workspace = NamedKnowledgeWorkspace(
            id=f"named_knowledge_workspace:copy_{len(self.workspaces)}",
            name=command.name,
            name_key=command.name_key,
            snapshot=source.snapshot,
            capacity_slot=len(self.workspaces),
            revision=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.workspaces[workspace.id] = workspace
        return workspace

    async def delete_workspace(self, workspace_id: str, command) -> NavigationReceipt:
        existing = await self.get_workspace(workspace_id)
        if command.expected_revision != existing.revision:
            raise KnowledgeNavigationRepositoryError("revision_conflict")
        del self.workspaces[workspace_id]
        timestamp = datetime(2026, 7, 31, tzinfo=timezone.utc)
        return NavigationReceipt(
            operation_id=command.operation_id,
            operation_kind="delete_workspace",
            entity_kind="workspace",
            entity_id=workspace_id,
            payload_hash="0" * 64,
            result_status="succeeded",
            result_revision=existing.revision,
            result_code="deleted",
            created_at=timestamp,
            completed_at=timestamp,
        )

    async def workspace_restore_plan(
        self, workspace_id: str, revision: int
    ) -> WorkspaceRestorePlan:
        if workspace_id != self.workspace.id:
            raise LookupError(workspace_id)
        if revision != self.workspace.revision:
            raise KnowledgeNavigationRepositoryError("workspace_revision_conflict")
        snapshot = self.workspace.snapshot
        return WorkspaceRestorePlan.model_validate(
            {
                "workspace_id": self.workspace.id,
                "revision": self.workspace.revision,
                "active_pane_id": snapshot.active_pane_id,
                "next_id": snapshot.next_id,
                "panes": {
                    "pane-one": {
                        "id": "pane-one",
                        "active_tab_id": "tab-search",
                        "tabs": [
                            {
                                "id": "tab-search",
                                "display_label": "Research",
                                "view_mode": "reading",
                                "target": {"kind": "search", "query": "research"},
                                "target_state": "available",
                            }
                        ],
                    }
                },
                "layout": snapshot.layout.model_dump(),
                "navigation": snapshot.navigation.model_dump(),
                "summary": {
                    "available": 1,
                    "stale": 0,
                    "unavailable": 0,
                    "missing": 0,
                },
            }
        )


class _DisabledEngineMetadataRepository:
    def __init__(self) -> None:
        self.random_count_calls = 0

    async def random_candidate_count(self, _filters):
        self.random_count_calls += 1
        raise AssertionError("disabled engine must not query random candidates")

    async def list_bookmarks(self, *_args) -> BookmarkPage:
        return BookmarkPage()

    async def list_workspaces(self) -> list[NamedKnowledgeWorkspaceSummary]:
        return []


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
        path: set(methods) for path, methods in paths.items() if "/knowledge/" in path
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
        "/api/deeper-notebook/knowledge/random-note": {"post"},
        "/api/deeper-notebook/knowledge/workspaces": {"get", "post"},
        "/api/deeper-notebook/knowledge/workspaces/{workspace_id}": {
            "get",
            "patch",
            "delete",
        },
        "/api/deeper-notebook/knowledge/workspaces/{workspace_id}/restore-plan": {
            "post"
        },
        "/api/deeper-notebook/knowledge/workspaces/{workspace_id}/duplicate": {"post"},
    }


@pytest.mark.asyncio
async def test_random_note_empty_is_200_and_no_store(api_client: AsyncClient) -> None:
    async with api_client:
        response = await api_client.post(
            "/api/deeper-notebook/knowledge/random-note",
            json={"space_ids": [], "authority_kinds": [], "tags": ["missing"]},
        )

    assert response.status_code == 200
    assert response.json() == {"state": "empty", "document": None}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["seed", "offset"])
async def test_random_note_rejects_public_selector_input_without_detail(
    api_client: AsyncClient,
    field: str,
) -> None:
    async with api_client:
        response = await api_client.post(
            "/api/deeper-notebook/knowledge/random-note",
            json={field: 42},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {"code": "knowledge_navigation_request_invalid"}
    }


@pytest.mark.asyncio
async def test_random_note_is_unavailable_without_engine_while_metadata_lists_work(
    api_client: AsyncClient,
) -> None:
    repository = _DisabledEngineMetadataRepository()
    api_client._transport.app.state.knowledge_navigation_service = (
        KnowledgeNavigationService(metadata_repository=repository)
    )

    async with api_client:
        random_note = await api_client.post(
            "/api/deeper-notebook/knowledge/random-note", json={}
        )
        bookmarks = await api_client.get("/api/deeper-notebook/knowledge/bookmarks")
        workspaces = await api_client.get("/api/deeper-notebook/knowledge/workspaces")

    assert random_note.status_code == 503
    assert random_note.json() == {
        "detail": {"code": "knowledge_navigation_unavailable"}
    }
    assert bookmarks.json() == {"items": [], "next_cursor": None}
    assert workspaces.json() == {"items": []}
    assert repository.random_count_calls == 0


@pytest.mark.asyncio
async def test_random_note_selected_response_is_safe_and_not_cached(
    api_client: AsyncClient,
) -> None:
    service = api_client._transport.app.state.knowledge_navigation_service
    service.random_note_result = RandomNoteResult(
        state="selected",
        document=KnowledgeOpenDescriptor(
            document_id="knowledge_engine_document:plan",
            space_id="knowledge_engine_space:research",
            authority_kind="external_read_only",
            source_kind="markdown",
            title="Plan",
            relative_locator="Research/Plan.md",
            legacy_note_id="note:plan",
            legacy_container_id="vault_mount:research",
        ),
    )

    async with api_client:
        response = await api_client.post(
            "/api/deeper-notebook/knowledge/random-note", json={}
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "state": "selected",
        "document": {
            "document_id": "knowledge_engine_document:plan",
            "space_id": "knowledge_engine_space:research",
            "authority_kind": "external_read_only",
            "source_kind": "markdown",
            "title": "Plan",
            "relative_locator": "Research/Plan.md",
            "legacy_note_id": "note:plan",
            "legacy_container_id": "vault_mount:research",
        },
    }
    assert "normalized_body" not in response.text
    assert "/Users/" not in response.text


@pytest.mark.asyncio
async def test_random_note_reuses_the_locked_one_mib_body_limit(
    api_client: AsyncClient,
) -> None:
    content = b"{" + b" " * MAX_NAVIGATION_JSON_BYTES
    async with api_client:
        response = await api_client.post(
            "/api/deeper-notebook/knowledge/random-note",
            content=content,
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {"code": "knowledge_navigation_request_invalid"}
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error, expected_status",
    [
        (KnowledgeNavigationServiceError("random_selector_invalid"), 422),
        (KnowledgeNavigationServiceError("knowledge_engine_unavailable"), 503),
        (KnowledgeNavigationRepositoryError("knowledge_engine_unavailable"), 503),
    ],
)
async def test_random_note_scrubs_selector_and_projection_failures(
    api_client: AsyncClient, error: Exception, expected_status: int
) -> None:
    api_client._transport.app.state.knowledge_navigation_service.random_note_error = (
        error
    )

    async with api_client:
        response = await api_client.post(
            "/api/deeper-notebook/knowledge/random-note", json={}
        )

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": {
            "code": "knowledge_navigation_request_invalid"
            if expected_status == 422
            else "knowledge_navigation_unavailable"
        }
    }


@pytest.mark.asyncio
async def test_workspace_list_excludes_snapshot_and_restore_plan_is_read_only(
    api_client: AsyncClient,
) -> None:
    service = api_client._transport.app.state.knowledge_navigation_service
    before = service.workspace.model_dump(mode="json")

    async with api_client:
        listed = await api_client.get("/api/deeper-notebook/knowledge/workspaces")
        restored = await api_client.post(
            "/api/deeper-notebook/knowledge/workspaces/"
            "named_knowledge_workspace%3Adesk/restore-plan",
            json={"revision": 3},
        )

    assert listed.status_code == 200
    assert listed.json() == {
        "items": [
            {
                "id": "named_knowledge_workspace:desk",
                "name": "Desk",
                "revision": 3,
                "updated_at": "2026-07-31T00:00:00Z",
            }
        ]
    }
    assert restored.status_code == 200
    assert restored.json()["summary"] == {
        "available": 1,
        "stale": 0,
        "unavailable": 0,
        "missing": 0,
    }
    assert service.workspace.model_dump(mode="json") == before


@pytest.mark.asyncio
async def test_restore_revision_conflict_returns_409_and_no_snapshot(
    api_client: AsyncClient,
) -> None:
    service = api_client._transport.app.state.knowledge_navigation_service
    before = service.workspace.model_dump(mode="json")

    async with api_client:
        response = await api_client.post(
            "/api/deeper-notebook/knowledge/workspaces/"
            "named_knowledge_workspace%3Adesk/restore-plan",
            json={"revision": 2},
        )

    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "knowledge_workspace_revision_conflict"}
    }
    assert service.workspace.model_dump(mode="json") == before


@pytest.mark.asyncio
async def test_workspace_crud_preserves_snapshot_and_current_session(
    api_client: AsyncClient, tmp_path
) -> None:
    current_session_path = tmp_path / "knowledge-workspace-v1.json"
    current_session_path.write_bytes(b'{"synthetic":true}')
    before = current_session_path.read_bytes()
    snapshot = {
        "active_pane_id": "pane-one",
        "next_id": 2,
        "panes": {
            "pane-one": {
                "id": "pane-one",
                "active_tab_id": "tab-search",
                "tabs": [
                    {
                        "id": "tab-search",
                        "display_label": "Research",
                        "target": {"kind": "search", "query": "research"},
                    }
                ],
            }
        },
        "layout": {"type": "pane", "pane_id": "pane-one"},
    }

    async with api_client:
        created = await api_client.post(
            "/api/deeper-notebook/knowledge/workspaces",
            json={
                "operation_id": "api-workspace-create",
                "name": "Desk",
                "snapshot": snapshot,
            },
        )
        workspace_id = created.json()["id"]
        fetched = await api_client.get(
            f"/api/deeper-notebook/knowledge/workspaces/{workspace_id}"
        )
        renamed = await api_client.patch(
            f"/api/deeper-notebook/knowledge/workspaces/{workspace_id}",
            json={
                "operation_id": "api-workspace-rename",
                "expected_revision": 1,
                "name": "  Research Desk  ",
            },
        )
        replaced = await api_client.patch(
            f"/api/deeper-notebook/knowledge/workspaces/{workspace_id}",
            json={
                "operation_id": "api-workspace-replace",
                "expected_revision": 2,
                "snapshot": {**snapshot, "next_id": 7},
            },
        )
        revision_conflict = await api_client.patch(
            f"/api/deeper-notebook/knowledge/workspaces/{workspace_id}",
            json={
                "operation_id": "api-workspace-stale",
                "expected_revision": 1,
                "name": "Stale",
            },
        )
        rejected = await api_client.patch(
            f"/api/deeper-notebook/knowledge/workspaces/{workspace_id}",
            json={
                "operation_id": "api-workspace-both",
                "expected_revision": 3,
                "name": "Both",
                "snapshot": snapshot,
            },
        )
        copied = await api_client.post(
            f"/api/deeper-notebook/knowledge/workspaces/{workspace_id}/duplicate",
            json={"operation_id": "api-workspace-copy", "name": "Copy"},
        )
        deleted = await api_client.request(
            "DELETE",
            f"/api/deeper-notebook/knowledge/workspaces/{workspace_id}",
            json={
                "operation_id": "api-workspace-delete",
                "expected_revision": 3,
            },
        )
        missing = await api_client.get(
            f"/api/deeper-notebook/knowledge/workspaces/{workspace_id}"
        )

    assert created.status_code == 201
    fetched_snapshot = fetched.json()["snapshot"]
    assert fetched.status_code == 200
    assert (
        renamed.status_code,
        renamed.json()["name"],
        renamed.json()["name_key"],
    ) == (
        200,
        "Research Desk",
        "research desk",
    )
    assert renamed.json()["snapshot"] == fetched_snapshot
    assert replaced.status_code == 200
    assert replaced.json()["name"] == "Research Desk"
    assert replaced.json()["snapshot"]["next_id"] == 7
    assert revision_conflict.status_code == 409
    assert revision_conflict.json() == {
        "detail": {"code": "knowledge_navigation_conflict"}
    }
    assert rejected.status_code == 422
    assert copied.status_code == 201
    assert copied.json()["id"] != workspace_id
    assert copied.json()["revision"] == 1
    assert deleted.status_code == 200
    assert missing.status_code == 404
    assert current_session_path.read_bytes() == before


@pytest.mark.asyncio
async def test_workspace_collection_overflow_is_a_scrubbed_server_failure(
    api_client: AsyncClient,
) -> None:
    api_client._transport.app.state.knowledge_navigation_service.collection_overflow = (
        True
    )

    async with api_client:
        response = await api_client.get("/api/deeper-notebook/knowledge/workspaces")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "knowledge_navigation_unavailable"}}


@pytest.mark.asyncio
async def test_allocator_workspace_routes_are_scrubbed_not_found_and_read_only(
    api_client: AsyncClient,
) -> None:
    service = api_client._transport.app.state.knowledge_navigation_service
    before = {
        key: value.model_dump(mode="json") for key, value in service.workspaces.items()
    }
    path = "/api/deeper-notebook/knowledge/workspaces/" + (
        "named_knowledge_workspace%3Acapacity_allocator"
    )

    async with api_client:
        responses = [
            await api_client.get(path),
            await api_client.patch(
                path,
                json={
                    "operation_id": "api-allocator-update",
                    "expected_revision": 1,
                    "name": "Nope",
                },
            ),
            await api_client.post(
                path + "/duplicate",
                json={"operation_id": "api-allocator-copy", "name": "Nope"},
            ),
            await api_client.request(
                "DELETE",
                path,
                json={"operation_id": "api-allocator-delete", "expected_revision": 1},
            ),
            await api_client.post(path + "/restore-plan", json={"revision": 1}),
        ]

    assert WORKSPACE_CAPACITY_ALLOCATOR_ID.endswith(":capacity_allocator")
    assert [response.status_code for response in responses] == [404, 404, 404, 404, 404]
    assert all(
        response.json() == {"detail": {"code": "knowledge_navigation_not_found"}}
        for response in responses
    )
    assert {
        key: value.model_dump(mode="json") for key, value in service.workspaces.items()
    } == before


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
@pytest.mark.parametrize(
    ("depth", "expected_status"), [(15, 200), (16, 200), (17, 503)]
)
async def test_folder_tree_has_an_inclusive_sixteen_level_bound(
    api_client: AsyncClient, depth: int, expected_status: int
) -> None:
    api_client._transport.app.state.knowledge_navigation_service.folders = (
        _folder_chain(depth)
    )

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
        (
            KnowledgeNavigationRepositoryError("folder_parent_not_found"),
            status.HTTP_404_NOT_FOUND,
        ),
        (
            KnowledgeNavigationRepositoryError("operation_conflict"),
            status.HTTP_409_CONFLICT,
        ),
        (
            KnowledgeNavigationRepositoryError("revision_conflict"),
            status.HTTP_409_CONFLICT,
        ),
        (KnowledgeNavigationRepositoryError("folder_cycle"), status.HTTP_409_CONFLICT),
        (
            KnowledgeNavigationRepositoryError("folder_depth_exceeded"),
            status.HTTP_409_CONFLICT,
        ),
        (ValueError("private"), status.HTTP_422_UNPROCESSABLE_CONTENT),
        (
            KnowledgeNavigationRepositoryError(
                "knowledge_navigation_repository_unavailable"
            ),
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ),
    ],
)
def test_declared_navigation_error_mapping_matrix_is_stable(
    exception: Exception, expected_status: int
) -> None:
    error = _map_exception(exception)

    assert error.status_code == expected_status
    assert "private" not in str(error.detail)
