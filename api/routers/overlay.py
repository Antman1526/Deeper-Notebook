"""Canonical authenticated API for app-owned overlay Markdown."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path as FilePath
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from loguru import logger
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from api.schemas.overlay import (
    CreateDailyNote,
    CreateUniqueNote,
    OverlayNote,
    OverlayPage,
    OverlayRootResponse,
    UpdateOverlayNote,
)
from deeper_notebook.overlay.paths import OverlayLayout
from deeper_notebook.overlay.repository import OverlayRepositoryError

MAX_OVERLAY_JSON_BYTES = 10 * 1024 * 1024 + 64 * 1024
# Bound database pagination work even for authenticated local clients.
MAX_OVERLAY_OFFSET = 1_000_000
_INSTANCE_NONCE = secrets.token_urlsafe(32)

_ERRORS = {
    "overlay_not_found": (404, "overlay_not_found"),
    "overlay_revision_conflict": (409, "overlay_revision_conflict"),
    "overlay_file_exists": (409, "overlay_file_exists"),
    "overlay_hash_conflict": (409, "overlay_revision_conflict"),
    "overlay_file_changed": (409, "overlay_revision_conflict"),
    "overlay_request_invalid": (422, "overlay_request_invalid"),
    "overlay_request_too_large": (413, "overlay_request_too_large"),
    "overlay_file_too_large": (413, "overlay_file_too_large"),
    "overlay_projection_pending": (503, "overlay_projection_pending"),
    "overlay_storage_unavailable": (503, "overlay_storage_unavailable"),
}


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


class _BoundedOverlayRequest(Request):
    async def body(self) -> bytes:
        if hasattr(self, "_body"):
            return self._body

        content_length = self.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_OVERLAY_JSON_BYTES:
                    raise _error(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        "overlay_request_too_large",
                    )
            except ValueError:
                pass

        chunks: list[bytes] = []
        received = 0
        async for chunk in self.stream():
            received += len(chunk)
            if received > MAX_OVERLAY_JSON_BYTES:
                raise _error(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "overlay_request_too_large",
                )
            chunks.append(chunk)
        self._body = b"".join(chunks)
        return self._body


class _BoundedOverlayRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original_route_handler = super().get_route_handler()

        async def bounded_route_handler(request: Request) -> Response:
            bounded_request = _BoundedOverlayRequest(
                request.scope,
                request.receive,
            )
            try:
                return await original_route_handler(bounded_request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content={"detail": {"code": "overlay_request_invalid"}},
                )

        return bounded_route_handler


router = APIRouter(route_class=_BoundedOverlayRoute)
_KNOWLEDGE_DOCUMENT_ID = re.compile(r"^knowledge_engine_document:[A-Za-z0-9_-]+$")
_KNOWLEDGE_BLOCK_ID = re.compile(r"^knowledge_engine_block:[A-Za-z0-9_-]+$")


class _OverlayProofIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    instance_nonce: str = Field(min_length=43, max_length=128)
    overlay_root_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    instance_pid: int = Field(gt=1)


def _service(request: Request) -> Any:
    service = getattr(request.app.state, "overlay_service", None)
    if service is None:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "overlay_unavailable",
        )
    return service


def _owned_overlay_root_digest(service: Any) -> str:
    storage = getattr(service, "storage", None)
    layout = getattr(storage, "layout", None)
    canonical_root = getattr(layout, "canonical_root", None)
    if not isinstance(layout, OverlayLayout) or not isinstance(
        canonical_root,
        FilePath,
    ):
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "overlay_unavailable",
        )
    try:
        data_root = canonical_root.parent.parent.resolve(strict=True)
    except (OSError, RuntimeError):
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "overlay_unavailable",
        ) from None
    if layout != OverlayLayout.from_data_root(data_root):
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "overlay_unavailable",
        )
    return hashlib.sha256(str(data_root).encode("utf-8")).hexdigest()


def _stable_exception_code(exc: Exception) -> str | None:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code in _ERRORS:
        return code
    if isinstance(exc, (LookupError, OverlayRepositoryError)) and exc.args:
        candidate = exc.args[0]
        if isinstance(candidate, str) and candidate in _ERRORS:
            return candidate
    return None


def _map_exception(exc: Exception) -> HTTPException:
    code = _stable_exception_code(exc)
    if code is not None:
        status_code, public_code = _ERRORS[code]
        return _error(status_code, public_code)
    logger.warning("Overlay request unavailable ({})", type(exc).__name__)
    return _error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "overlay_unavailable",
    )


async def _enrich_page_identity(request: Request, page: OverlayPage) -> OverlayPage:
    """Attach optional unified IDs without changing overlay persistence semantics."""
    service = getattr(request.app.state, "knowledge_engine_service", None)
    if service is None:
        return page
    blocks = [dict(block) for block in page.blocks]
    try:
        keys = tuple(
            dict.fromkeys(
                key
                for block in blocks
                for key in [block.get("stable_source_id") or block.get("parser_id")]
                if isinstance(key, str)
            )
        )
        resolved = await service.resolve_legacy_page(
            legacy_note_id=str(page.note["id"]), block_keys=keys
        )
        document_id = getattr(resolved, "document_id", None)
        block_ids = getattr(resolved, "block_ids", None)
        if isinstance(resolved, dict):
            document_id = resolved.get("document_id")
            block_ids = resolved.get("block_ids")
        if (
            not isinstance(document_id, str)
            or _KNOWLEDGE_DOCUMENT_ID.fullmatch(document_id) is None
            or not isinstance(block_ids, dict)
        ):
            return page
        for block in blocks:
            key = block.get("stable_source_id") or block.get("parser_id")
            block_id = block_ids.get(key) if isinstance(key, str) else None
            if isinstance(block_id, str) and _KNOWLEDGE_BLOCK_ID.fullmatch(block_id):
                block["knowledge_block_id"] = block_id
        return page.model_copy(
            update={"knowledge_document_id": document_id, "blocks": blocks}
        )
    except Exception:
        return page


def _calendar_date_key(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("invalid date key") from None
    if parsed.isoformat() != value:
        raise ValueError("invalid date key")
    return value


OverlayDateKey = Annotated[
    str,
    Path(
        min_length=10,
        max_length=10,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    AfterValidator(_calendar_date_key),
]
OverlayNoteId = Annotated[
    str,
    Path(
        min_length=1,
        max_length=128,
        pattern=r"^overlay_note:[A-Za-z0-9_-]+$",
    ),
]


@router.get("/overlay", response_model=OverlayRootResponse)
async def get_overlay(request: Request) -> OverlayRootResponse:
    _service(request)
    return OverlayRootResponse()


@router.get("/overlay/proof-identity", response_model=_OverlayProofIdentity)
async def get_overlay_proof_identity(request: Request) -> _OverlayProofIdentity:
    """Bind a controlled proof to this process and its actual owned data root."""

    service = _service(request)
    return _OverlayProofIdentity(
        instance_nonce=_INSTANCE_NONCE,
        overlay_root_sha256=_owned_overlay_root_digest(service),
        instance_pid=os.getpid(),
    )


@router.get("/overlay/notes", response_model=list[OverlayNote])
async def list_overlay_notes(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=MAX_OVERLAY_OFFSET),
) -> list[OverlayNote]:
    try:
        return await _service(request).list_notes(limit, offset)
    except Exception as exc:
        raise _map_exception(exc) from None


@router.put("/overlay/daily/{date_key}", response_model=OverlayPage)
async def create_daily_overlay_note(
    request: Request,
    date_key: OverlayDateKey,
) -> OverlayPage:
    try:
        return await _enrich_page_identity(
            request,
            await _service(request).create_daily(CreateDailyNote(date_key=date_key)),
        )
    except Exception as exc:
        raise _map_exception(exc) from None


@router.post(
    "/overlay/notes/unique",
    response_model=OverlayPage,
    status_code=status.HTTP_201_CREATED,
)
async def create_unique_overlay_note(
    request: Request,
    payload: CreateUniqueNote,
) -> OverlayPage:
    try:
        return await _enrich_page_identity(
            request, await _service(request).create_unique(payload)
        )
    except Exception as exc:
        raise _map_exception(exc) from None


@router.get("/overlay/notes/{note_id}", response_model=OverlayPage)
async def get_overlay_note(
    request: Request,
    note_id: OverlayNoteId,
) -> OverlayPage:
    try:
        return await _enrich_page_identity(
            request, await _service(request).get_page(note_id)
        )
    except Exception as exc:
        raise _map_exception(exc) from None


@router.put("/overlay/notes/{note_id}", response_model=OverlayPage)
async def update_overlay_note(
    request: Request,
    note_id: OverlayNoteId,
    payload: UpdateOverlayNote,
) -> OverlayPage:
    try:
        return await _enrich_page_identity(
            request, await _service(request).update(note_id, payload)
        )
    except Exception as exc:
        raise _map_exception(exc) from None


__all__ = ["MAX_OVERLAY_JSON_BYTES", "MAX_OVERLAY_OFFSET", "router"]
