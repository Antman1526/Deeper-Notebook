"""Strict, feature-gated HTTP operations for rebuildable source visuals."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from api.schemas.source_visuals import (
    SourceVisualDeleteRequest,
    SourceVisualRefreshRequest,
)
from deeper_notebook.domain.notebook import Source
from deeper_notebook.exceptions import NotFoundError
from deeper_notebook.feature_flags import source_visuals_enabled
from deeper_notebook.source_visuals.authority import (
    SourceVisualAuthorityError,
    compute_source_visual_authority,
)
from deeper_notebook.source_visuals.cleanup import SourceVisualCleanup
from deeper_notebook.source_visuals.queue import submit_source_visual
from deeper_notebook.source_visuals.repository import (
    SourceVisualConflictError,
    SourceVisualRepository,
    SourceVisualRepositoryError,
)
from deeper_notebook.source_visuals.storage import (
    SourceVisualStorageError,
    SourceVisualStore,
)

router = APIRouter(prefix="/sources", tags=["source-visuals"])
_FEATURE_UNAVAILABLE = "Source visuals are unavailable"


def _guard() -> None:
    if not source_visuals_enabled():
        raise HTTPException(status_code=404, detail=_FEATURE_UNAVAILABLE)


async def _source_authority(source_id: str):
    source = await _require_source(source_id)
    try:
        return await compute_source_visual_authority(source)
    except SourceVisualAuthorityError:
        raise HTTPException(
            status_code=409, detail="Source visual authority is unavailable"
        ) from None


async def _require_source(source_id: str):
    try:
        source = await Source.get(source_id)
    except (NotFoundError, ValueError):
        source = None
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


def _conflict() -> HTTPException:
    return HTTPException(
        status_code=409, detail="Source visual receipt is stale or conflicts"
    )


def _payload(
    value: object,
    model: type[SourceVisualRefreshRequest] | type[SourceVisualDeleteRequest],
) -> str:
    try:
        if not isinstance(value, Mapping):
            raise ValueError
        return model.model_validate(dict(value)).request_id
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=422, detail="Invalid source visual request"
        ) from None


def _job_response(value: object, *, status_code: int) -> JSONResponse:
    payload = {
        "source_id": getattr(value, "source_id", None),
        "command_id": getattr(value, "command_id", None),
        "content_sha256": getattr(value, "content_sha256", None),
        "asset_sha256": getattr(value, "asset_sha256", None),
        "origin": getattr(value, "origin", None),
        "width": getattr(value, "width", None),
        "height": getattr(value, "height", None),
        "duration_ms": getattr(value, "duration_ms", None),
        "outcome": getattr(value, "outcome", "failed"),
        "error_code": getattr(value, "error_code", None),
    }
    return JSONResponse(status_code=status_code, content=payload)


async def get_source_visual_asset(
    source_id: str,
    *,
    if_none_match: str | None,
    repository: SourceVisualRepository | object | None = None,
    store: SourceVisualStore | object | None = None,
) -> Response:
    """Serve verified bytes only after the full current authority is recomputed."""

    _guard()
    authority = await _source_authority(source_id)
    repo = repository or SourceVisualRepository()
    asset_store = store or SourceVisualStore()
    try:
        current = await repo.list_current(
            {authority.source_id: authority.source_updated_at}
        )
        record = (
            current.get(authority.source_id) if isinstance(current, Mapping) else None
        )
        if record is None or record.content_sha256 != authority.content_sha256:
            raise _conflict()
        body = asset_store.read_exact(record)
    except HTTPException:
        raise
    except (
        SourceVisualRepositoryError,
        SourceVisualStorageError,
        ValueError,
        TypeError,
    ):
        raise _conflict() from None
    headers = {
        "ETag": f'"{record.asset_sha256}"',
        "Cache-Control": "private, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
    }
    if if_none_match == headers["ETag"]:
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="image/webp", headers=headers)


async def submit_source_visual_refresh(source_id: str, payload: object) -> JSONResponse:
    """Submit an explicit visual job or return its durable replay receipt."""

    _guard()
    request_id = _payload(payload, SourceVisualRefreshRequest)
    await _require_source(source_id)
    try:
        job = await submit_source_visual(source_id, request_id, explicit=True)
    except (
        SourceVisualConflictError,
        SourceVisualRepositoryError,
        SourceVisualAuthorityError,
    ):
        raise _conflict() from None
    return _job_response(
        job, status_code=200 if getattr(job, "outcome", None) == "replayed" else 202
    )


async def delete_source_visual(
    source_id: str,
    payload: object,
    *,
    repository: SourceVisualRepository | object | None = None,
    cleanup: SourceVisualCleanup | object | None = None,
) -> JSONResponse:
    """Tombstone the exact current derivative with a durable delete receipt."""

    _guard()
    request_id = _payload(payload, SourceVisualDeleteRequest)
    authority = await _source_authority(source_id)
    repo = repository or SourceVisualRepository()
    cleanup_service = cleanup or SourceVisualCleanup(SourceVisualStore(), repo)
    try:
        existing = await repo.get_operation(authority.source_id, request_id, "delete")
        if existing is not None:
            if (
                getattr(existing, "source_updated_at", None)
                != authority.source_updated_at
                or getattr(existing, "content_sha256", None) != authority.content_sha256
            ):
                raise SourceVisualConflictError("REQUEST_CONFLICT")
            if getattr(existing, "outcome", None) == "deleted":
                return _job_response(existing, status_code=200)
            if getattr(existing, "outcome", None) != "queued":
                raise SourceVisualConflictError("REQUEST_CONFLICT")
        current = await repo.list_current(
            {authority.source_id: authority.source_updated_at}
        )
        record = (
            current.get(authority.source_id) if isinstance(current, Mapping) else None
        )
        if record is not None and record.content_sha256 != authority.content_sha256:
            raise SourceVisualConflictError("SOURCE_STALE")
        if existing is None:
            await repo.record_operation(
                source_id=authority.source_id,
                request_id=request_id,
                operation="delete",
                source_updated_at=authority.source_updated_at,
                content_sha256=authority.content_sha256,
                outcome="queued",
            )
        if record is not None and not await cleanup_service.delete_record(record):
            raise SourceVisualConflictError("REQUEST_CONFLICT")
        completed = await repo.finalize_operation(
            source_id=authority.source_id,
            request_id=request_id,
            operation="delete",
            source_updated_at=authority.source_updated_at,
            content_sha256=authority.content_sha256,
            outcome="deleted",
        )
        return _job_response(completed, status_code=200)
    except (
        SourceVisualConflictError,
        SourceVisualRepositoryError,
        SourceVisualStorageError,
    ):
        raise _conflict() from None


@router.get("/{source_id}/visual")
async def source_visual_asset_endpoint(
    source_id: str,
    if_none_match: str | None = Header(default=None),
) -> Response:
    return await get_source_visual_asset(source_id, if_none_match=if_none_match)


@router.post("/{source_id}/visual:refresh")
async def source_visual_refresh_endpoint(
    source_id: str, request: Request
) -> JSONResponse:
    _guard()
    try:
        payload = await request.json()
    except Exception:
        payload = None
    return await submit_source_visual_refresh(source_id, payload)


@router.delete("/{source_id}/visual")
async def source_visual_delete_endpoint(
    source_id: str, request: Request
) -> JSONResponse:
    _guard()
    try:
        payload = await request.json()
    except Exception:
        payload = None
    return await delete_source_visual(source_id, payload)


__all__ = [
    "delete_source_visual",
    "get_source_visual_asset",
    "router",
    "submit_source_visual_refresh",
]
