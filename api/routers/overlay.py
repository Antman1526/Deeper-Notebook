"""Canonical authenticated API for app-owned overlay Markdown."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response, status
from fastapi.routing import APIRoute
from loguru import logger
from pydantic import AfterValidator

from api.schemas.overlay import (
    CreateDailyNote,
    CreateUniqueNote,
    OverlayNote,
    OverlayPage,
    OverlayRootResponse,
    UpdateOverlayNote,
)
from deeper_notebook.overlay.repository import OverlayRepositoryError

MAX_OVERLAY_JSON_BYTES = 10 * 1024 * 1024 + 64 * 1024

_ERRORS = {
    "overlay_not_found": (404, "overlay_not_found"),
    "overlay_revision_conflict": (409, "overlay_revision_conflict"),
    "overlay_file_exists": (409, "overlay_file_exists"),
    "overlay_hash_conflict": (409, "overlay_revision_conflict"),
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
            return await original_route_handler(bounded_request)

        return bounded_route_handler


router = APIRouter(route_class=_BoundedOverlayRoute)


def _service(request: Request) -> Any:
    service = getattr(request.app.state, "overlay_service", None)
    if service is None:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "overlay_unavailable",
        )
    return service


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


@router.get("/overlay/notes", response_model=list[OverlayNote])
async def list_overlay_notes(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[OverlayNote]:
    try:
        return await _service(request).list_notes(limit, offset)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.put("/overlay/daily/{date_key}", response_model=OverlayPage)
async def create_daily_overlay_note(
    request: Request,
    date_key: OverlayDateKey,
) -> OverlayPage:
    try:
        return await _service(request).create_daily(CreateDailyNote(date_key=date_key))
    except HTTPException:
        raise
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
        return await _service(request).create_unique(payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.get("/overlay/notes/{note_id}", response_model=OverlayPage)
async def get_overlay_note(
    request: Request,
    note_id: OverlayNoteId,
) -> OverlayPage:
    try:
        return await _service(request).get_page(note_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


@router.put("/overlay/notes/{note_id}", response_model=OverlayPage)
async def update_overlay_note(
    request: Request,
    note_id: OverlayNoteId,
    payload: UpdateOverlayNote,
) -> OverlayPage:
    try:
        return await _service(request).update(note_id, payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_exception(exc) from None


__all__ = ["MAX_OVERLAY_JSON_BYTES", "router"]
