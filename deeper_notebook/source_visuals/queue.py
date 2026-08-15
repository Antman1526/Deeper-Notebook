"""Durable claim-before-submit handoff for source visual extraction."""

from __future__ import annotations

import asyncio
import inspect
import secrets
from dataclasses import dataclass
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
_CLAIM_HEARTBEAT_SECONDS = 30
_PENDING_RETENTION_SECONDS = 1


@dataclass(slots=True)
class _PendingSubmission:
    """One side-effecting submission that remains owner-fenced after timeout."""

    receipt: asyncio.Future[str | None]
    submit_task: asyncio.Task[object]
    heartbeat_stop: asyncio.Event
    heartbeat_task: asyncio.Task[None]
    finalizer_task: asyncio.Task[None] | None = None
    error_code: str | None = None


_PENDING_SUBMISSIONS: dict[str, _PendingSubmission] = {}


def _retire_pending_submission(identity: str, pending: _PendingSubmission) -> None:
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


async def _load_source(source_id: str) -> object:
    source = await _await_if_needed(Source.get(source_id))
    if source is None:
        raise SourceVisualRepositoryError("INVALID_INPUT")
    return source


async def _record_queued_operation(
    repository: object,
    *,
    authority: object,
    request_id: str,
) -> None:
    """Persist this caller's idempotency receipt before its handoff response."""

    await _await_if_needed(
        repository.record_operation(
            source_id=authority.source_id,
            request_id=request_id,
            operation="refresh",
            source_updated_at=authority.source_updated_at,
            content_sha256=authority.content_sha256,
            command_id=None,
            outcome="queued",
        )
    )


async def _finalize_queued_operation(
    repository: object,
    *,
    authority: object,
    request_id: str,
    command_id: str | None,
    outcome: str,
    error_code: str | None,
) -> object:
    """Advance only this caller's initially unbound queued receipt."""

    return await _await_if_needed(
        repository.finalize_operation(
            source_id=authority.source_id,
            request_id=request_id,
            operation="refresh",
            source_updated_at=authority.source_updated_at,
            content_sha256=authority.content_sha256,
            expected_command_id=None,
            expected_outcome="queued",
            expected_error_code=None,
            command_id=command_id,
            outcome=outcome,
            error_code=error_code,
        )
    )


async def _reconcile_bound_claim_command(
    repository: object,
    *,
    authority: object,
    request_id: str,
    receipt: object,
) -> object:
    """Repair only an exact queued receipt from its exact durable claim."""

    if (
        getattr(receipt, "command_id", None) is not None
        or getattr(receipt, "outcome", None) != "queued"
        or getattr(receipt, "error_code", None) is not None
    ):
        return receipt
    claim = await _await_if_needed(
        repository.get_claim(
            authority.source_id,
            authority.content_sha256,
            authority.extractor_version,
        )
    )
    command_id = getattr(claim, "command_id", None)
    if (
        not command_id
        or getattr(claim, "source_id", None) != authority.source_id
        or getattr(claim, "content_sha256", None) != authority.content_sha256
        or getattr(claim, "extractor_version", None) != authority.extractor_version
    ):
        return receipt
    try:
        return await _finalize_queued_operation(
            repository,
            authority=authority,
            request_id=request_id,
            command_id=str(command_id),
            outcome="queued",
            error_code=None,
        )
    except SourceVisualConflictError:
        repaired = await _await_if_needed(
            repository.get_operation(authority.source_id, request_id, "refresh")
        )
        if repaired is None:
            raise
        return repaired


async def _operation_response(
    repository: object,
    *,
    authority: object,
    request_id: str,
    receipt: object,
) -> SourceVisualJobResponse:
    """Validate and project one current idempotency receipt."""

    receipt = await _reconcile_bound_claim_command(
        repository,
        authority=authority,
        request_id=request_id,
        receipt=receipt,
    )
    if (
        getattr(receipt, "content_sha256", None) != authority.content_sha256
        or getattr(receipt, "source_updated_at", None) != authority.source_updated_at
    ):
        raise SourceVisualConflictError("REQUEST_CONFLICT")
    outcome = "failed" if getattr(receipt, "outcome", None) == "failed" else "replayed"
    return SourceVisualJobResponse(
        source_id=authority.source_id,
        command_id=getattr(receipt, "command_id", None),
        content_sha256=authority.content_sha256,
        outcome=outcome,
        error_code=getattr(receipt, "error_code", None) if outcome == "failed" else None,
    )


async def _suppressed_auto_ingest_response(
    repository: object,
    *,
    authority: object,
    request_id: str,
    explicit: bool,
) -> SourceVisualJobResponse | None:
    """Replay a completed delete for automatic ingestion of the same version."""

    if explicit or request_id != f"ingest:{authority.content_sha256}":
        return None
    deleted = await _await_if_needed(
        repository.find_completed_delete(
            authority.source_id,
            authority.source_updated_at,
            authority.content_sha256,
        )
    )
    if deleted is None:
        return None
    try:
        await _await_if_needed(
            repository.record_operation(
                source_id=authority.source_id,
                request_id=request_id,
                operation="refresh",
                source_updated_at=authority.source_updated_at,
                content_sha256=authority.content_sha256,
                command_id=None,
                outcome="deleted",
            )
        )
    except SourceVisualConflictError:
        # A concurrent automatic caller may have written the deterministic
        # receipt after this caller's initial replay lookup.
        existing = await _await_if_needed(
            repository.get_operation(authority.source_id, request_id, "refresh")
        )
        if existing is None:
            raise
        if (
            getattr(existing, "source_updated_at", None) != authority.source_updated_at
            or getattr(existing, "content_sha256", None) != authority.content_sha256
        ):
            raise SourceVisualConflictError("REQUEST_CONFLICT")
    return SourceVisualJobResponse(
        source_id=authority.source_id,
        command_id=None,
        content_sha256=authority.content_sha256,
        outcome="replayed",
    )


async def _heartbeat_claim(
    repository: object,
    *,
    authority: object,
    owner_token: str,
    stop: asyncio.Event,
) -> None:
    """Retain the exact owner fence while an uncancellable thread can submit."""

    try:
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=_CLAIM_HEARTBEAT_SECONDS)
                return
            except asyncio.TimeoutError:
                await _await_if_needed(
                    repository.renew_claim(
                        source_id=authority.source_id,
                        content_sha256=authority.content_sha256,
                        extractor_version=authority.extractor_version,
                        owner_token=owner_token,
                        lease_seconds=_CLAIM_LEASE_SECONDS,
                    )
                )
    except asyncio.CancelledError:
        raise
    except Exception:
        # The original 90-second claim and owner fence remain the safe crash /
        # takeover boundary. Do not release a claim while a submit thread may
        # still return an unbound command.
        return


async def _finalize_submission(
    repository: object,
    *,
    authority: object,
    request_id: str,
    owner_token: str,
    pending: _PendingSubmission,
    identity: str,
) -> None:
    """Bind a late command without treating its claim as side-effect free."""

    command_id: str | None = None
    try:
        submitted = await asyncio.shield(pending.submit_task)
        command_id = str(submitted)
        if not command_id:
            raise RuntimeError("queue did not return a command id")
        await _await_if_needed(
            repository.bind_command_and_finalize_operation(
                source_id=authority.source_id,
                content_sha256=authority.content_sha256,
                extractor_version=authority.extractor_version,
                owner_token=owner_token,
                command_id=command_id,
                request_id=request_id,
                source_updated_at=authority.source_updated_at,
            )
        )
    except asyncio.CancelledError:
        # Loop shutdown is the only expected cancellation of this detached
        # finalizer. Lease expiry and owner fencing protect any later takeover.
        raise
    except Exception:
        submission_error = (
            pending.submit_task.exception()
            if pending.submit_task.done() and not pending.submit_task.cancelled()
            else None
        )
        if submission_error is not None:
            # The submission itself failed before it returned any command ID,
            # so this exact owner may safely finalize the durable receipt and
            # release its unbound claim. A bind/finalize failure remains
            # fail-closed because a command may already exist.
            try:
                await _finalize_queued_operation(
                    repository,
                    authority=authority,
                    request_id=request_id,
                    command_id=None,
                    outcome="failed",
                    error_code="queue_submit_failed",
                )
                pending.error_code = "queue_submit_failed"
                pending.heartbeat_stop.set()
                try:
                    await asyncio.shield(pending.heartbeat_task)
                except Exception:
                    pass
                await _release_unsubmitted_claim(
                    repository, authority=authority, owner_token=owner_token
                )
            except Exception:
                pending.error_code = None
        # A command may have been created when bind/finalization fails; never
        # release this claim or overwrite its still-queued operation receipt.
        command_id = None
    finally:
        if not pending.receipt.done():
            pending.receipt.set_result(command_id)
        pending.heartbeat_stop.set()
        try:
            await asyncio.shield(pending.heartbeat_task)
        except Exception:
            pass
        asyncio.get_running_loop().call_later(
            _PENDING_RETENTION_SECONDS,
            _retire_pending_submission,
            identity,
            pending,
        )


async def _live_claim_response(
    repository: object,
    *,
    source_id: str,
    content_sha256: str,
    extractor_version: str,
) -> SourceVisualJobResponse:
    """Return a bounded receipt for a durable claim this caller does not own."""

    identity = f"{source_id}\0{content_sha256}\0{extractor_version}"
    pending = _PENDING_SUBMISSIONS.get(identity)
    if pending is not None:
        try:
            command_id = await asyncio.wait_for(
                asyncio.shield(pending.receipt), timeout=_QUEUE_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            command_id = None
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


async def _release_unsubmitted_claim(
    repository: object,
    *,
    authority: object,
    owner_token: str,
) -> None:
    """Release only before a submission thread has been created."""

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


async def submit_source_visual(
    source_id: str, request_id: str, *, explicit: bool
) -> SourceVisualJobResponse:
    """Durably claim, receipt, submit, and bind one owner-fenced queue job."""

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
        return await _operation_response(
            repository,
            authority=authority,
            request_id=request_id,
            receipt=existing,
        )

    suppressed = await _suppressed_auto_ingest_response(
        repository,
        authority=authority,
        request_id=request_id,
        explicit=explicit,
    )
    if suppressed is not None:
        return suppressed

    owner_token = secrets.token_hex(32)
    identity = f"{authority.source_id}\0{authority.content_sha256}\0{authority.extractor_version}"
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
    except SourceVisualConflictError:
        # A losing caller records its own durable receipt before it can replay
        # the winner's bounded response.
        try:
            await _record_queued_operation(
                repository, authority=authority, request_id=request_id
            )
        except SourceVisualConflictError:
            existing = await _await_if_needed(
                repository.get_operation(authority.source_id, request_id, "refresh")
            )
            if existing is None:
                raise
            return await _operation_response(
                repository,
                authority=authority,
                request_id=request_id,
                receipt=existing,
            )
        return await _live_claim_response(
            repository,
            source_id=authority.source_id,
            content_sha256=authority.content_sha256,
            extractor_version=authority.extractor_version,
        )

    try:
        # This record exists before an uncancellable worker thread can create
        # a command. Its command ID remains absent until the fenced bind wins.
        await _record_queued_operation(
            repository, authority=authority, request_id=request_id
        )
    except Exception:
        await _release_unsubmitted_claim(
            repository, authority=authority, owner_token=owner_token
        )
        raise

    loop = asyncio.get_running_loop()
    receipt: asyncio.Future[str | None] = loop.create_future()
    heartbeat_stop = asyncio.Event()
    submit_task = asyncio.create_task(
        asyncio.to_thread(
            submit_command,
            LEGACY_COMMAND_APP,
            "extract_source_visual",
            {
                "source_id": authority.source_id,
                "request_id": request_id,
                "expected_content_sha256": authority.content_sha256,
                "extractor_version": authority.extractor_version,
                "claim_owner_token": owner_token,
            },
        )
    )
    heartbeat_task = asyncio.create_task(
        _heartbeat_claim(
            repository,
            authority=authority,
            owner_token=owner_token,
            stop=heartbeat_stop,
        )
    )
    pending = _PendingSubmission(
        receipt=receipt,
        submit_task=submit_task,
        heartbeat_stop=heartbeat_stop,
        heartbeat_task=heartbeat_task,
    )
    _PENDING_SUBMISSIONS[identity] = pending
    pending.finalizer_task = asyncio.create_task(
        _finalize_submission(
            repository,
            authority=authority,
            request_id=request_id,
            owner_token=owner_token,
            pending=pending,
            identity=identity,
        )
    )

    try:
        command_id = await asyncio.wait_for(
            asyncio.shield(receipt), timeout=_QUEUE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        command_id = None
    return SourceVisualJobResponse(
        source_id=authority.source_id,
        command_id=command_id,
        content_sha256=authority.content_sha256,
        outcome="failed" if pending.error_code else "queued",
        error_code=pending.error_code,
    )


__all__ = ["SourceVisualJobResponse", "submit_source_visual"]
