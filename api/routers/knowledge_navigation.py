"""Canonical global bookmark and folder routes with stable error envelopes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import ValidationError

from api.schemas.knowledge_navigation import (
    BookmarkCreateRequest,
    BookmarkDeleteRequest,
    BookmarkFolderCreateRequest,
    BookmarkFolderDeleteRequest,
    BookmarkFolderNode,
    BookmarkFolderTreeResponse,
    BookmarkFolderUpdateRequest,
    BookmarkListResponse,
    BookmarkResponse,
    BookmarkUpdateRequest,
    KnowledgeNavigationErrorResponse,
    KnowledgeWorkspaceCreateRequest,
    KnowledgeWorkspaceDeleteRequest,
    KnowledgeWorkspaceDuplicateRequest,
    KnowledgeWorkspaceListResponse,
    KnowledgeWorkspaceResponse,
    KnowledgeWorkspaceRestorePlanRequest,
    KnowledgeWorkspaceRestorePlanResponse,
    KnowledgeWorkspaceUpdateRequest,
    NavigationReceiptResponse,
    RandomNoteRequest,
    RandomNoteResponse,
)
from deeper_notebook.knowledge_engine.navigation_contracts import (
    BookmarkCursor,
    BookmarkFilters,
)
from deeper_notebook.knowledge_engine.navigation_repository import (
    KnowledgeNavigationRepositoryError,
)
from deeper_notebook.knowledge_engine.navigation_service import (
    KnowledgeNavigationServiceError,
)

MAX_NAVIGATION_JSON_BYTES = 1024 * 1024
MAX_FOLDER_TREE_ITEMS = 256
_ERROR_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {"model": KnowledgeNavigationErrorResponse},
    status.HTTP_409_CONFLICT: {"model": KnowledgeNavigationErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": KnowledgeNavigationErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": KnowledgeNavigationErrorResponse},
}
_CONFLICT_CODES = frozenset(
    {
        "operation_conflict",
        "revision_conflict",
        "folder_cycle",
        "folder_depth_exceeded",
    }
)
_NOT_FOUND_CODES = frozenset({"not_found", "folder_parent_not_found"})


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


class _BoundedNavigationRequest(Request):
    async def body(self) -> bytes:
        if hasattr(self, "_body"):
            return self._body
        content_length = self.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_NAVIGATION_JSON_BYTES:
                    raise _error(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        "knowledge_navigation_request_invalid",
                    )
            except ValueError:
                pass
        chunks: list[bytes] = []
        size = 0
        async for chunk in self.stream():
            size += len(chunk)
            if size > MAX_NAVIGATION_JSON_BYTES:
                raise _error(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "knowledge_navigation_request_invalid",
                )
            chunks.append(chunk)
        self._body = b"".join(chunks)
        return self._body


class _BoundedNavigationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original_route_handler = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            bounded_request = _BoundedNavigationRequest(request.scope, request.receive)
            try:
                return await original_route_handler(bounded_request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content={
                        "detail": {"code": "knowledge_navigation_request_invalid"}
                    },
                )

        return route_handler


router = APIRouter(route_class=_BoundedNavigationRoute)


def _service(request: Request) -> Any:
    service = getattr(request.app.state, "knowledge_navigation_service", None)
    if service is None:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "knowledge_navigation_unavailable",
        )
    return service


def _map_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return _error(status.HTTP_404_NOT_FOUND, "knowledge_navigation_not_found")
    if isinstance(exc, KnowledgeNavigationServiceError):
        if exc.code == "random_selector_invalid":
            return _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "knowledge_navigation_request_invalid",
            )
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "knowledge_navigation_unavailable",
        )
    if isinstance(exc, (ValidationError, ValueError)):
        return _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "knowledge_navigation_request_invalid",
        )
    if isinstance(exc, KnowledgeNavigationRepositoryError):
        if exc.code == "workspace_revision_conflict":
            return _error(
                status.HTTP_409_CONFLICT,
                "knowledge_workspace_revision_conflict",
            )
        if exc.code == "workspace_limit_reached":
            return _error(
                status.HTTP_409_CONFLICT,
                "knowledge_workspace_limit_reached",
            )
        if exc.code in _NOT_FOUND_CODES:
            return _error(status.HTTP_404_NOT_FOUND, "knowledge_navigation_not_found")
        if exc.code in _CONFLICT_CODES or exc.code.endswith("_name_conflict"):
            return _error(status.HTTP_409_CONFLICT, "knowledge_navigation_conflict")
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "knowledge_navigation_unavailable",
        )
    return _error(
        status.HTTP_503_SERVICE_UNAVAILABLE, "knowledge_navigation_unavailable"
    )


def _folder_tree(folders: list[Any]) -> BookmarkFolderTreeResponse:
    if len(folders) > MAX_FOLDER_TREE_ITEMS:
        raise KnowledgeNavigationRepositoryError(
            "knowledge_navigation_repository_unavailable"
        )
    children: dict[str | None, list[Any]] = {}
    known_ids = {folder.id for folder in folders}
    for folder in folders:
        if (
            folder.parent_folder_id is not None
            and folder.parent_folder_id not in known_ids
        ):
            raise KnowledgeNavigationRepositoryError(
                "knowledge_navigation_repository_unavailable"
            )
        children.setdefault(folder.parent_folder_id, []).append(folder)

    visited: set[str] = set()

    def build(parent_id: str | None, depth: int) -> list[BookmarkFolderNode]:
        nodes: list[BookmarkFolderNode] = []
        for folder in children.get(parent_id, []):
            if depth >= 16:
                raise KnowledgeNavigationRepositoryError(
                    "knowledge_navigation_repository_unavailable"
                )
            if folder.id in visited:
                raise KnowledgeNavigationRepositoryError(
                    "knowledge_navigation_repository_unavailable"
                )
            visited.add(folder.id)
            nodes.append(
                BookmarkFolderNode(
                    **folder.model_dump(),
                    children=build(folder.id, depth + 1),
                )
            )
        return nodes

    tree = BookmarkFolderTreeResponse(items=build(None, 0))
    if len(visited) != len(folders):
        raise KnowledgeNavigationRepositoryError(
            "knowledge_navigation_repository_unavailable"
        )
    return tree


@router.get(
    "/bookmarks", response_model=BookmarkListResponse, responses=_ERROR_RESPONSES
)
async def list_bookmarks(
    request: Request,
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    folder_id: str | None = Query(default=None, max_length=128),
    tag: list[str] = Query(default=[]),
    target_kind: list[str] = Query(default=[]),
    space_id: list[str] = Query(default=[]),
    authority_kind: list[str] = Query(default=[]),
) -> BookmarkListResponse:
    try:
        filters = BookmarkFilters(
            folder_id=folder_id,
            tags=tag,
            target_kinds=target_kind,
            space_ids=space_id,
            authority_kinds=authority_kind,
        )
        if cursor is not None:
            BookmarkCursor.decode(cursor)
        return await _service(request).list_bookmarks(filters, cursor, limit)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.post(
    "/random-note",
    response_model=RandomNoteResponse,
    responses=_ERROR_RESPONSES,
)
async def random_note(request: Request, filters: RandomNoteRequest) -> Response:
    try:
        result = await _service(request).random_note(filters)
        return JSONResponse(
            content=result.model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.post(
    "/bookmarks",
    status_code=status.HTTP_201_CREATED,
    response_model=BookmarkResponse,
    responses=_ERROR_RESPONSES,
)
async def create_bookmark(
    request: Request, command: BookmarkCreateRequest
) -> BookmarkResponse:
    try:
        return await _service(request).create_bookmark(command)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.patch(
    "/bookmarks/{bookmark_id}",
    response_model=BookmarkResponse,
    responses=_ERROR_RESPONSES,
)
async def update_bookmark(
    request: Request,
    command: BookmarkUpdateRequest,
    bookmark_id: str = Path(
        pattern=r"^knowledge_bookmark:[A-Za-z0-9_-]+$", max_length=128
    ),
) -> BookmarkResponse:
    try:
        return await _service(request).update_bookmark(bookmark_id, command)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.delete(
    "/bookmarks/{bookmark_id}",
    response_model=NavigationReceiptResponse,
    responses=_ERROR_RESPONSES,
)
async def delete_bookmark(
    request: Request,
    command: BookmarkDeleteRequest,
    bookmark_id: str = Path(
        pattern=r"^knowledge_bookmark:[A-Za-z0-9_-]+$", max_length=128
    ),
) -> NavigationReceiptResponse:
    try:
        return await _service(request).delete_bookmark(bookmark_id, command)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.get(
    "/bookmark-folders",
    response_model=BookmarkFolderTreeResponse,
    responses=_ERROR_RESPONSES,
)
async def list_bookmark_folders(request: Request) -> BookmarkFolderTreeResponse:
    try:
        return _folder_tree(await _service(request).list_folders())
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.post(
    "/bookmark-folders",
    status_code=status.HTTP_201_CREATED,
    response_model=BookmarkFolderNode,
    responses=_ERROR_RESPONSES,
)
async def create_bookmark_folder(
    request: Request, command: BookmarkFolderCreateRequest
) -> BookmarkFolderNode:
    try:
        return BookmarkFolderNode(
            **(await _service(request).create_folder(command)).model_dump()
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.patch(
    "/bookmark-folders/{folder_id}",
    response_model=BookmarkFolderNode,
    responses=_ERROR_RESPONSES,
)
async def update_bookmark_folder(
    request: Request,
    command: BookmarkFolderUpdateRequest,
    folder_id: str = Path(
        pattern=r"^knowledge_bookmark_folder:[A-Za-z0-9_-]+$", max_length=128
    ),
) -> BookmarkFolderNode:
    try:
        return BookmarkFolderNode(
            **(await _service(request).update_folder(folder_id, command)).model_dump()
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.delete(
    "/bookmark-folders/{folder_id}",
    response_model=NavigationReceiptResponse,
    responses=_ERROR_RESPONSES,
)
async def delete_bookmark_folder(
    request: Request,
    command: BookmarkFolderDeleteRequest,
    folder_id: str = Path(
        pattern=r"^knowledge_bookmark_folder:[A-Za-z0-9_-]+$", max_length=128
    ),
) -> NavigationReceiptResponse:
    try:
        return await _service(request).delete_folder(folder_id, command)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.get(
    "/workspaces",
    response_model=KnowledgeWorkspaceListResponse,
    responses=_ERROR_RESPONSES,
)
async def list_workspaces(request: Request) -> KnowledgeWorkspaceListResponse:
    try:
        return KnowledgeWorkspaceListResponse(
            items=await _service(request).list_workspaces()
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.post(
    "/workspaces",
    status_code=status.HTTP_201_CREATED,
    response_model=KnowledgeWorkspaceResponse,
    responses=_ERROR_RESPONSES,
)
async def create_workspace(
    request: Request, command: KnowledgeWorkspaceCreateRequest
) -> KnowledgeWorkspaceResponse:
    try:
        return await _service(request).create_workspace(command)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.post(
    "/workspaces/{workspace_id}/restore-plan",
    response_model=KnowledgeWorkspaceRestorePlanResponse,
    responses=_ERROR_RESPONSES,
)
async def workspace_restore_plan(
    request: Request,
    command: KnowledgeWorkspaceRestorePlanRequest,
    workspace_id: str = Path(
        pattern=r"^named_knowledge_workspace:[A-Za-z0-9_-]+$", max_length=128
    ),
) -> KnowledgeWorkspaceRestorePlanResponse:
    try:
        return await _service(request).workspace_restore_plan(
            workspace_id, command.revision
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.get(
    "/workspaces/{workspace_id}",
    response_model=KnowledgeWorkspaceResponse,
    responses=_ERROR_RESPONSES,
)
async def get_workspace(
    request: Request,
    workspace_id: str = Path(
        pattern=r"^named_knowledge_workspace:[A-Za-z0-9_-]+$", max_length=128
    ),
) -> KnowledgeWorkspaceResponse:
    try:
        return await _service(request).get_workspace(workspace_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.patch(
    "/workspaces/{workspace_id}",
    response_model=KnowledgeWorkspaceResponse,
    responses=_ERROR_RESPONSES,
)
async def update_workspace(
    request: Request,
    command: KnowledgeWorkspaceUpdateRequest,
    workspace_id: str = Path(
        pattern=r"^named_knowledge_workspace:[A-Za-z0-9_-]+$", max_length=128
    ),
) -> KnowledgeWorkspaceResponse:
    try:
        return await _service(request).update_workspace(workspace_id, command)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.post(
    "/workspaces/{workspace_id}/duplicate",
    status_code=status.HTTP_201_CREATED,
    response_model=KnowledgeWorkspaceResponse,
    responses=_ERROR_RESPONSES,
)
async def duplicate_workspace(
    request: Request,
    command: KnowledgeWorkspaceDuplicateRequest,
    workspace_id: str = Path(
        pattern=r"^named_knowledge_workspace:[A-Za-z0-9_-]+$", max_length=128
    ),
) -> KnowledgeWorkspaceResponse:
    try:
        return await _service(request).duplicate_workspace(workspace_id, command)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.delete(
    "/workspaces/{workspace_id}",
    response_model=NavigationReceiptResponse,
    responses=_ERROR_RESPONSES,
)
async def delete_workspace(
    request: Request,
    command: KnowledgeWorkspaceDeleteRequest,
    workspace_id: str = Path(
        pattern=r"^named_knowledge_workspace:[A-Za-z0-9_-]+$", max_length=128
    ),
) -> NavigationReceiptResponse:
    try:
        return await _service(request).delete_workspace(workspace_id, command)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


__all__ = ["MAX_NAVIGATION_JSON_BYTES", "router"]
