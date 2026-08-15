"""Durable claim-before-submit handoff for source visual extraction."""

from __future__ import annotations

import asyncio
import inspect
import secrets
from typing import Awaitable, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from surreal_commands import submit_command

from deeper_notebook.domain.notebook import Source
from deeper_notebook.identity import LEGACY_COMMAND_APP
from deeper_notebook.source_visuals.authority import compute_source_visual_authority
from deeper_notebook.source_visuals.repository import (
    SourceVisualConflictError,
    SourceVisualRepository,
    SourceVisualRepositoryError,
)

_AwaitableValue = TypeVar("_AwaitableValue")
_QUEUE_TIMEOUT_SECONDS = 10
_CLAIM_LEASE_SECONDS = 90
_PENDING_SUBMISSIONS: dict[str, asyncio.Future[str | None]] = {}


def _retire_pending_submission(
    identity: str, pending: asyncio.Future[str | None]
) -> None:
    if _PENDING_SUBMISSIONS.get(identity) is pending:
        _PENDING_SUBMISSIONS.pop(identity, None)


class SourceVisualJobResponse(BaseModel):
    """Safe submission receipt; it intentionally contains no source path or text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=512)
    command_id: str | None = Field(default=None, min_length=1, max_length=512)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: Literal["queued", "replayed", "failed"]
    error_code: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$",
        max_length=64,
    )


async def _await_if_needed(value: _AwaitableValue | Awaitable[_AwaitableValue]) -> _AwaitableValue:
    if inspect.isawaitable(value):
        return await value
    return value


def _safe_error_code(value: object, *, fallback: str) -> str:
    raw = str(getattr(value, "code", fallback)).strip().lower()
    safe = "".join(character if character.isalnum() else "_" for character in raw)
    safe = safe.strip("_")[:64]
    return safe or fallback


async def _load_source(source_id: str) -> object:
    source = await _await_if_needed(Source.get(source_id))
    if source is None:
        raise SourceVisualRepositoryError("INVALID_INPUT")
    return source


async def _live_claim_response(
    repository: object,
    *,
    source_id: str,
    content_sha256: str,
    extractor_version: str,
) -> SourceVisualJobResponse:
    """Return a bounded receipt for a durable claim we do not own.

    Task 2 intentionally does not expose a general claim-read API.  Test and
    future repository adapters may provide one; otherwise the queue receipt
    remains useful but does not disclose or invent a command identifier.
    """

    identity = f"{source_id}\0{content_sha256}\0{extractor_version}"
    pending = _PENDING_SUBMISSIONS.get(identity)
    if pending is not None:
        try:
            command_id = await asyncio.wait_for(asyncio.shield(pending), timeout=_QUEUE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            command_id = None
        if command_id:
            return SourceVisualJobResponse(
                source_id=source_id,
                command_id=command_id,
                content_sha256=content_sha256,
                outcome="replayed",
            )

    get_claim = getattr(repository, "get_claim", None)
    claim = None
    if callable(get_claim):
        claim = await _await_if_needed(
            get_claim(source_id, content_sha256, extractor_version)
        )
    return SourceVisualJobResponse(
        source_id=source_id,
        command_id=(str(getattr(claim, "command_id", "")) or None),
        content_sha256=content_sha256,
        outcome="replayed",
    )


async def _record_failure(
    repository: object,
    *,
    source_id: str,
    request_id: str,
    source_updated_at: object,
    content_sha256: str,
    error_code: str,
) -> None:
    try:
        await _await_if_needed(
            repository.record_operation(
                source_id=source_id,
                request_id=request_id,
                operation="refresh",
                source_updated_at=source_updated_at,
                content_sha256=content_sha256,
                outcome="failed",
                error_code=error_code,
            )
        )
    except (SourceVisualConflictError, SourceVisualRepositoryError):
        # A concurrent, valid receipt wins; do not overwrite it with a local
        # failure from a claim we no longer own.
        return


async def submit_source_visual(
    source_id: str, request_id: str, *, explicit: bool
) -> SourceVisualJobResponse:
    """Acquire a 90-second owner-fenced claim before creating a queue row."""

    if (
        not isinstance(source_id, str)
        or not source_id
        or not isinstance(request_id, str)
        or not 1 <= len(request_id) <= 256
        or not isinstance(explicit, bool)
    ):
        raise SourceVisualRepositoryError("INVALID_INPUT")

    repository = SourceVisualRepository()
    source = await _load_source(source_id)
    authority = await _await_if_needed(compute_source_visual_authority(source))
    if authority.source_id != source_id:
        raise SourceVisualRepositoryError("INVALID_INPUT")

    existing = await _await_if_needed(
        repository.get_operation(source_id, request_id, "refresh")
    )
    if existing is not None:
        if (
            getattr(existing, "content_sha256", None) != authority.content_sha256
            or getattr(existing, "source_updated_at", None) != authority.source_updated_at
        ):
            raise SourceVisualConflictError("REQUEST_CONFLICT")
        outcome = "failed" if getattr(existing, "outcome", None) == "failed" else "replayed"
        return SourceVisualJobResponse(
            source_id=source_id,
            command_id=getattr(existing, "command_id", None),
            content_sha256=authority.content_sha256,
            outcome=outcome,
            error_code=getattr(existing, "error_code", None) if outcome == "failed" else None,
        )

    owner_token = secrets.token_hex(32)
    claim_acquired = False
    pending_identity = f"{authority.source_id}\0{authority.content_sha256}\0{authority.extractor_version}"
    pending: asyncio.Future[str | None] | None = None
    try:
        await _await_if_needed(
            repository.acquire_claim(
                source_id=authority.source_id,
                content_sha256=authority.content_sha256,
                extractor_version=authority.extractor_version,
                owner_token=owner_token,
                lease_seconds=_CLAIM_LEASE_SECONDS,
            )
        )
        claim_acquired = True
        pending = asyncio.get_running_loop().create_future()
        _PENDING_SUBMISSIONS[pending_identity] = pending
    except SourceVisualConflictError:
        return await _live_claim_response(
            repository,
            source_id=authority.source_id,
            content_sha256=authority.content_sha256,
            extractor_version=authority.extractor_version,
        )

    try:
        payload = {
            "source_id": authority.source_id,
            "request_id": request_id,
            "expected_content_sha256": authority.content_sha256,
            "extractor_version": authority.extractor_version,
            "claim_owner_token": owner_token,
        }
        command_id = await asyncio.wait_for(
            asyncio.to_thread(
                submit_command,
                LEGACY_COMMAND_APP,
                "extract_source_visual",
                payload,
            ),
            timeout=_QUEUE_TIMEOUT_SECONDS,
        )
        command_id = str(command_id)
        if not command_id:
            raise RuntimeError("queue did not return a command id")
        await _await_if_needed(
            repository.bind_command(
                source_id=authority.source_id,
                content_sha256=authority.content_sha256,
                extractor_version=authority.extractor_version,
                owner_token=owner_token,
                command_id=command_id,
            )
        )
        await _await_if_needed(
            repository.record_operation(
                source_id=authority.source_id,
                request_id=request_id,
                operation="refresh",
                source_updated_at=authority.source_updated_at,
                content_sha256=authority.content_sha256,
                command_id=command_id,
                outcome="queued",
            )
        )
        if pending is not None and not pending.done():
            pending.set_result(command_id)
        if pending is not None:
            asyncio.get_running_loop().call_later(
                1,
                _retire_pending_submission,
                pending_identity,
                pending,
            )
        return SourceVisualJobResponse(
            source_id=authority.source_id,
            command_id=command_id,
            content_sha256=authority.content_sha256,
            outcome="queued",
        )
    except asyncio.TimeoutError as exc:
        error_code = "queue_timeout"
        failure = exc
    except Exception as exc:
        error_code = _safe_error_code(exc, fallback="queue_failed")
        if error_code not in {"queue_timeout", "queue_failed"}:
            error_code = "queue_failed"
        failure = exc

    if claim_acquired:
        try:
            await _await_if_needed(
                repository.release_claim(
                    source_id=authority.source_id,
                    content_sha256=authority.content_sha256,
                    extractor_version=authority.extractor_version,
                    owner_token=owner_token,
                )
            )
        except Exception:
            pass
    await _record_failure(
        repository,
        source_id=authority.source_id,
        request_id=request_id,
        source_updated_at=authority.source_updated_at,
        content_sha256=authority.content_sha256,
        error_code=error_code,
    )
    if pending is not None and not pending.done():
        pending.set_result(None)
    if pending is not None and _PENDING_SUBMISSIONS.get(pending_identity) is pending:
        _PENDING_SUBMISSIONS.pop(pending_identity, None)
    del failure
    return SourceVisualJobResponse(
        source_id=authority.source_id,
        content_sha256=authority.content_sha256,
        outcome="failed",
        error_code=error_code,
    )


__all__ = ["SourceVisualJobResponse", "submit_source_visual"]
