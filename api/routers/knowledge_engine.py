"""Authenticated, GET-only diagnostics for the optional knowledge engine."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute

from api.schemas.knowledge_engine import (
    KnowledgeDocumentDetailResponse,
    KnowledgeDocumentListResponse,
    KnowledgeEngineStatusResponse,
)
from deeper_notebook.knowledge_engine.contracts import KnowledgeDocument
from deeper_notebook.knowledge_engine.repository import KnowledgeRepositoryError

MAX_KNOWLEDGE_ENGINE_OFFSET = 1_000_000


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


class _KnowledgeEngineRoute(APIRoute):
    """Keep all parameter failures on the stable, content-free envelope."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original_route_handler = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            try:
                return await original_route_handler(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content={"detail": {"code": "knowledge_engine_request_invalid"}},
                )

        return route_handler


router = APIRouter(route_class=_KnowledgeEngineRoute)


def _service(request: Request) -> Any:
    service = getattr(request.app.state, "knowledge_engine_service", None)
    if service is None:
        raise _error(status.HTTP_404_NOT_FOUND, "knowledge_engine_disabled")
    if not callable(getattr(service, "status", None)):
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "knowledge_engine_unavailable")
    return service


def _map_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, (ValueError, RequestValidationError)):
        return _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "knowledge_engine_request_invalid",
        )
    if isinstance(exc, LookupError):
        return _error(status.HTTP_404_NOT_FOUND, "knowledge_document_not_found")
    if isinstance(exc, KnowledgeRepositoryError):
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "knowledge_engine_unavailable",
        )
    return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "knowledge_engine_unavailable")


def _document_summary(document: KnowledgeDocument) -> dict[str, Any]:
    return {
        "id": document.id,
        "space_id": document.space_id,
        "relative_locator": document.relative_locator,
        "title": document.title,
        "kind": document.document_kind,
        "source_hash": document.content_hash,
        "source_revision_id": document.source_revision_id,
        "provenance": document.provenance,
        "authority_kind": document.authority_kind,
        "availability": document.availability,
        "state": document.parse_state,
        "capabilities": document.capabilities,
    }


KnowledgeDocumentId = Annotated[
    str,
    Path(
        min_length=1,
        max_length=128,
        pattern=r"^knowledge_engine_document:[A-Za-z0-9_-]+$",
    ),
]
KnowledgeSpaceId = Annotated[
    str,
    Query(
        min_length=1,
        max_length=128,
        pattern=r"^knowledge_engine_space:[A-Za-z0-9_-]+$",
    ),
]


@router.get("/knowledge-engine/status", response_model=KnowledgeEngineStatusResponse)
async def get_status(request: Request) -> KnowledgeEngineStatusResponse:
    try:
        projection = await _service(request).status()
        return KnowledgeEngineStatusResponse(
            projected=projection.projected,
            unchanged=projection.unchanged,
            failed=projection.failed,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.get(
    "/knowledge-engine/documents",
    response_model=list[KnowledgeDocumentListResponse],
)
async def list_documents(
    request: Request,
    space_id: KnowledgeSpaceId | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=MAX_KNOWLEDGE_ENGINE_OFFSET),
) -> list[KnowledgeDocumentListResponse]:
    try:
        documents = await _service(request).list_documents(
            space_id=space_id,
            limit=limit,
            offset=offset,
        )
        return [KnowledgeDocumentListResponse(**_document_summary(item)) for item in documents]
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.get(
    "/knowledge-engine/documents/{document_id}",
    response_model=KnowledgeDocumentDetailResponse,
)
async def get_document(
    request: Request,
    document_id: KnowledgeDocumentId,
) -> KnowledgeDocumentDetailResponse:
    try:
        document = await _service(request).get_document(document_id)
        return KnowledgeDocumentDetailResponse(
            **_document_summary(document),
            normalized_body=document.normalized_body,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


__all__ = ["MAX_KNOWLEDGE_ENGINE_OFFSET", "router"]
