"""Owner-fenced persistence for source visual claims and operation receipts."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.source_visuals.contracts import (
    SourceVisualAuthority,
    SourceVisualClaim,
    SourceVisualOperationReceipt,
    SourceVisualRecord,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ASSET_RELPATH_RE = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{64}/[0-9a-f]{64}\.webp$")
_MAX_REVISIONS = 200
_PUBLIC_ERROR_CODES = frozenset(
    {
        "INVALID_INPUT",
        "MAX_REVISIONS",
        "DATABASE_ERROR",
        "MALFORMED_ROW",
        "CLAIM_HELD",
        "CLAIM_NOT_FOUND",
        "OWNER_MISMATCH",
        "COMMAND_CONFLICT",
        "REQUEST_CONFLICT",
        "DELETE_REQUESTED",
        "SOURCE_STALE",
        "LEASE_EXPIRED",
    }
)


class _CurrentVisualRows(dict[str, SourceVisualRecord]):
    """Mapping-compatible ready rows with bounded non-ready status hints."""

    def __init__(
        self,
        *args: object,
        statuses: Mapping[str, Mapping[str, object]] | None = None,
        **kwargs: object,
    ):
        super().__init__(*args, **kwargs)
        self.statuses = dict(statuses or {})


class SourceVisualRepositoryError(ValueError):
    """Safe repository failure with a bounded public code."""

    def __init__(self, code: str):
        self.code = code if code in _PUBLIC_ERROR_CODES else "DATABASE_ERROR"
        super().__init__(self.code)


class SourceVisualConflictError(SourceVisualRepositoryError):
    """A lease, command, request, or source-revision fence rejected a write."""


def claim_identity(source_id: str, content_sha256: str, extractor_version: str) -> str:
    return hashlib.sha256(
        f"{source_id}\0{content_sha256}\0{extractor_version}".encode("utf-8")
    ).hexdigest()


def operation_identity(source_id: str, request_id: str, operation: str) -> str:
    return hashlib.sha256(
        f"{source_id}\0{request_id}\0{operation}".encode("utf-8")
    ).hexdigest()


def _cache_identity(source_id: str, content_sha256: str) -> str:
    return hashlib.sha256(f"{source_id}\0{content_sha256}".encode("utf-8")).hexdigest()


def _get(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _string(value: object) -> str:
    return str(value)


def _datetime(value: object, fallback: datetime | None = None) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return fallback
    else:
        return fallback
    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _now(value: datetime | None) -> datetime:
    result = _datetime(value)
    return result or datetime.now(timezone.utc)


def _hash(value: object, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise SourceVisualRepositoryError("INVALID_INPUT")
    return value


def _rows(result: object) -> list[dict[str, Any]]:
    if result is None:
        return []
    if isinstance(result, Mapping):
        nested = result.get("result")
        if isinstance(nested, list):
            return [dict(row) for row in nested if isinstance(row, Mapping)]
        return [dict(result)]
    if isinstance(result, list):
        return [dict(row) for row in result if isinstance(row, Mapping)]
    return []


def _row(result: object) -> dict[str, Any] | None:
    rows = _rows(result)
    if not rows:
        return None
    for item in reversed(rows):
        if any(
            key in item
            for key in (
                "claim_id",
                "operation_id",
                "owner_token",
                "source_updated_at",
                "source_id",
                "conflict",
                "source_stale",
            )
        ):
            return item
    return rows[-1]


def _require_live_lease(
    row: Mapping[str, Any] | None, owner_token: str, now: datetime
) -> Mapping[str, Any]:
    """Require both exact ownership and a lease strictly after ``now``."""

    if not row or row.get("owner_mismatch") or row.get("owner_token") != owner_token:
        raise SourceVisualConflictError("OWNER_MISMATCH")
    lease_until = _datetime(row.get("lease_until"))
    if lease_until is None or lease_until <= now:
        raise SourceVisualConflictError("LEASE_EXPIRED")
    return row


def _plain_id(value: object) -> str | None:
    if value is None:
        return None
    result = str(value)
    if ":" in result:
        table, _, suffix = result.partition(":")
        if table in {
            "source_visual_claim",
            "source_visual_operation",
            "source_visual_cache",
        }:
            return suffix
    return result


def _source_id(value: object) -> str:
    if isinstance(value, SourceVisualAuthority):
        return value.source_id
    candidate = _get(value, "source_id")
    if candidate is None:
        candidate = _get(value, "id")
    if candidate is None:
        candidate = value
    result = str(candidate)
    if not result or not result.startswith("source:") or "\x00" in result:
        raise SourceVisualRepositoryError("INVALID_INPUT")
    return result


def _identity(
    source_id: str | SourceVisualAuthority | None,
    content_sha256: str | None,
    extractor_version: str | None,
    authority: SourceVisualAuthority | None,
) -> tuple[str, str, str, SourceVisualAuthority | None]:
    if authority is None and isinstance(source_id, SourceVisualAuthority):
        authority = source_id
    if authority is not None:
        resolved_source_id = authority.source_id
        resolved_content = authority.content_sha256
        resolved_version = authority.extractor_version
    else:
        if source_id is None or content_sha256 is None or extractor_version is None:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        resolved_source_id = _source_id(source_id)
        resolved_content = content_sha256
        resolved_version = extractor_version
    _hash(resolved_content)
    if not isinstance(resolved_version, str) or not resolved_version:
        raise SourceVisualRepositoryError("INVALID_INPUT")
    return resolved_source_id, resolved_content, resolved_version, authority


def _record(table: str, identity: str) -> object:
    try:
        record_id = (
            identity if identity.startswith(f"{table}:") else f"{table}:{identity}"
        )
        return ensure_record_id(record_id)
    except (TypeError, ValueError):
        raise SourceVisualRepositoryError("INVALID_INPUT") from None


def _command_text(value: object) -> str | None:
    if value is None:
        return None
    result = str(value)
    return result if result.startswith("command:") else f"command:{result}"


def _command_record(value: object) -> object | None:
    command_text = _command_text(value)
    return _record("command", command_text) if command_text is not None else None


def _source_record(source_id: str) -> object:
    try:
        return ensure_record_id(source_id)
    except (TypeError, ValueError):
        raise SourceVisualRepositoryError("INVALID_INPUT") from None


async def _transaction(query: str, variables: dict[str, object]) -> object:
    try:
        return await repo_query(query, variables)
    except SourceVisualRepositoryError:
        raise
    except Exception as exc:
        if "DN_SOURCE_VISUAL_" in query and "failed transaction" in str(exc).lower():
            # SurrealDB 2.x rolls back a transaction aborted by THROW but its
            # Python driver exposes only this generic message, not the thrown
            # marker.  Guarded callers perform exact persisted-state
            # postcondition reads and recover the bounded public conflict.
            return None
        raise SourceVisualRepositoryError("DATABASE_ERROR") from exc


async def _read_exact_row(table: str, identity: str) -> dict[str, Any] | None:
    """Read one deterministic repository record after a fenced transaction.

    SurrealDB's Python driver returns ``None`` for multi-statement transactions
    containing a top-level ``IF``, even when the transaction committed.  The
    write remains atomic; this bounded read supplies the authoritative
    postcondition instead of manufacturing a success row from caller input.
    """

    return _row(
        await _transaction(
            "SELECT * FROM $record;",
            {"record": _record(table, identity)},
        )
    )


def _claim_from_row(
    row: Mapping[str, Any] | None,
    *,
    claim_id: str,
    source_id: str,
    content_sha256: str,
    extractor_version: str,
    owner_token: str,
    lease_until: datetime,
    now: datetime,
    command_id: str | None = None,
) -> SourceVisualClaim:
    data = dict(row or {})
    data.pop("id", None)
    raw_id = data.get("claim_id", data.get("id"))
    data.update(
        {
            "claim_id": _plain_id(raw_id) or claim_id,
            "source_id": _string(data.get("source_id", source_id)),
            "content_sha256": data.get("content_sha256", content_sha256),
            "extractor_version": data.get("extractor_version", extractor_version),
            "owner_token": data.get("owner_token", owner_token),
            "lease_until": _datetime(data.get("lease_until"), lease_until),
            "command_id": data.get("command_id", command_id),
            "created_at": _datetime(data.get("created_at"), now),
            "updated_at": _datetime(data.get("updated_at"), now),
        }
    )
    data["source_id"] = _string(data["source_id"])
    data["command_id"] = _command_text(data["command_id"])
    try:
        return SourceVisualClaim.model_validate(data)
    except Exception as exc:
        raise SourceVisualRepositoryError("MALFORMED_ROW") from exc


def _operation_unknown_fields(row: Mapping[str, Any]) -> set[str]:
    allowed = {
        "id",
        "operation_id",
        "source_id",
        "request_id",
        "source_updated_at",
        "content_sha256",
        "operation",
        "command_id",
        "outcome",
        "error_code",
        "created_at",
        "updated_at",
    }
    return set(row).difference(allowed)


def _operation_matches(
    row: Mapping[str, Any],
    *,
    source_id: str,
    request_id: str,
    source_updated_at: datetime,
    content_sha256: str,
    operation: str,
    command_id: str | None,
    outcome: str,
    error_code: str | None,
) -> bool:
    if _operation_unknown_fields(row):
        return False
    row_source = _string(row.get("source_id", ""))
    row_revision = _datetime(row.get("source_updated_at"))
    row_command = _command_text(row.get("command_id"))
    return (
        row_source == source_id
        and row.get("request_id") == request_id
        and row_revision == source_updated_at
        and row.get("content_sha256") == content_sha256
        and row.get("operation") == operation
        and row_command == _command_text(command_id)
        and row.get("outcome") == outcome
        and row.get("error_code") == error_code
    )


def _receipt_from_row(
    row: Mapping[str, Any] | None,
    *,
    operation_id: str,
    source_id: str,
    request_id: str,
    source_updated_at: datetime,
    content_sha256: str,
    operation: str,
    command_id: str | None,
    outcome: str,
    error_code: str | None,
    now: datetime,
    fallback: SourceVisualOperationReceipt | None = None,
) -> SourceVisualOperationReceipt:
    data = dict(row or {})
    data.pop("id", None)
    if fallback is not None:
        data = {**fallback.model_dump(), **data}
    data.update(
        {
            "operation_id": _plain_id(data.get("operation_id", data.get("id")))
            or operation_id,
            "source_id": _string(data.get("source_id", source_id)),
            "request_id": data.get("request_id", request_id),
            "source_updated_at": _datetime(
                data.get("source_updated_at"), source_updated_at
            ),
            "content_sha256": data.get("content_sha256", content_sha256),
            "operation": data.get("operation", operation),
            "command_id": data.get("command_id", command_id),
            "outcome": data.get("outcome", outcome),
            "error_code": data.get("error_code", error_code),
            "created_at": _datetime(data.get("created_at"), now),
            "updated_at": _datetime(data.get("updated_at"), now),
        }
    )
    data["command_id"] = _command_text(data["command_id"])
    try:
        return SourceVisualOperationReceipt.model_validate(data)
    except Exception as exc:
        raise SourceVisualRepositoryError("MALFORMED_ROW") from exc


def _record_from_row(row: Mapping[str, Any]) -> SourceVisualRecord:
    data = dict(row)
    data.pop("id", None)
    try:
        return SourceVisualRecord.model_validate(data)
    except Exception as exc:
        raise SourceVisualRepositoryError("MALFORMED_ROW") from exc


class SourceVisualRepository:
    """Repository whose writes are fenced by the claim owner token."""

    def __init__(self) -> None:
        self._operation_cache: dict[str, SourceVisualOperationReceipt] = {}

    async def acquire_claim(
        self,
        source_id: str | SourceVisualAuthority | None = None,
        content_sha256: str | None = None,
        extractor_version: str | None = None,
        owner_token: str | None = None,
        *,
        authority: SourceVisualAuthority | None = None,
        now: datetime | None = None,
        lease_until: datetime | None = None,
        lease_seconds: int = 300,
    ) -> SourceVisualClaim:
        source_id, content_sha256, extractor_version, _ = _identity(
            source_id, content_sha256, extractor_version, authority
        )
        owner_token = _hash(owner_token)
        current = _now(now)
        if lease_until is None:
            if (
                isinstance(lease_seconds, bool)
                or not isinstance(lease_seconds, int)
                or lease_seconds <= 0
            ):
                raise SourceVisualRepositoryError("INVALID_INPUT")
            lease_until = current + timedelta(seconds=lease_seconds)
        lease_until = _datetime(lease_until)
        if lease_until is None or lease_until <= current:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        identity = claim_identity(source_id, content_sha256, extractor_version)
        result = await _transaction(
            """
            BEGIN TRANSACTION;
            LET $existing = (SELECT * FROM $claim_record)[0];
            IF $existing = NONE THEN
                CREATE $claim_record CONTENT $claim_data;
            ELSE IF $existing.owner_token = $owner_token OR $existing.lease_until <= $now THEN
                UPDATE $claim_record MERGE $claim_data;
            ELSE
                RETURN { conflict: true, existing: $existing };
            END;
            SELECT * FROM $claim_record;
            COMMIT TRANSACTION;
            """,
            {
                "claim_record": _record("source_visual_claim", identity),
                "source_record": _source_record(source_id),
                "claim_data": {
                    "claim_id": identity,
                    "source_id": _source_record(source_id),
                    "content_sha256": content_sha256,
                    "extractor_version": extractor_version,
                    "owner_token": owner_token,
                    "lease_until": lease_until,
                    "command_id": None,
                    "created_at": current,
                    "updated_at": current,
                },
                "owner_token": owner_token,
                "now": current,
            },
        )
        row = _row(result)
        if row is None:
            row = await _read_exact_row("source_visual_claim", identity)
        if row and (row.get("conflict") or row.get("existing")):
            existing = row.get("existing")
            if not isinstance(existing, Mapping):
                existing = row
            existing_until = _datetime(existing.get("lease_until"))
            if existing.get("owner_token") != owner_token and (
                existing_until is None or existing_until > current
            ):
                raise SourceVisualConflictError("CLAIM_HELD")
            row = dict(existing)
        if row:
            existing_owner = row.get("owner_token")
            existing_until = _datetime(row.get("lease_until"))
            if (
                existing_owner is not None
                and existing_owner != owner_token
                and (existing_until is None or existing_until > current)
            ):
                raise SourceVisualConflictError("CLAIM_HELD")
            row = dict(row)
            row.update(
                {
                    "source_id": source_id,
                    "content_sha256": content_sha256,
                    "extractor_version": extractor_version,
                    "owner_token": owner_token,
                    "lease_until": lease_until,
                }
            )
        return _claim_from_row(
            row,
            claim_id=identity,
            source_id=source_id,
            content_sha256=content_sha256,
            extractor_version=extractor_version,
            owner_token=owner_token,
            lease_until=lease_until,
            now=current,
        )

    async def renew_claim(
        self,
        source_id: str | SourceVisualAuthority | None = None,
        content_sha256: str | None = None,
        extractor_version: str | None = None,
        owner_token: str | None = None,
        *,
        authority: SourceVisualAuthority | None = None,
        now: datetime | None = None,
        lease_until: datetime | None = None,
        lease_seconds: int = 300,
    ) -> SourceVisualClaim:
        source_id, content_sha256, extractor_version, _ = _identity(
            source_id, content_sha256, extractor_version, authority
        )
        owner_token = _hash(owner_token)
        current = _now(now)
        if lease_until is None:
            if (
                isinstance(lease_seconds, bool)
                or not isinstance(lease_seconds, int)
                or lease_seconds <= 0
            ):
                raise SourceVisualRepositoryError("INVALID_INPUT")
            lease_until = current + timedelta(seconds=lease_seconds)
        lease_until = _datetime(lease_until)
        if lease_until is None or lease_until <= current:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        identity = claim_identity(source_id, content_sha256, extractor_version)
        result = await _transaction(
            """
            BEGIN TRANSACTION;
            LET $existing = (SELECT * FROM $claim_record)[0];
            IF $existing = NONE OR $existing.owner_token != $owner_token
                    OR $existing.lease_until <= $now {
                THROW "DN_SOURCE_VISUAL_OWNER_MISMATCH";
            };
            UPDATE $claim_record MERGE { lease_until: $lease_until, updated_at: $now };
            SELECT * FROM $claim_record;
            COMMIT TRANSACTION;
            """,
            {
                "claim_record": _record("source_visual_claim", identity),
                "owner_token": owner_token,
                "lease_until": lease_until,
                "now": current,
            },
        )
        row = _row(result)
        if row is None:
            row = await _read_exact_row("source_visual_claim", identity)
        _require_live_lease(row, owner_token, current)
        if _datetime(row.get("lease_until")) != lease_until:
            raise SourceVisualRepositoryError("DATABASE_ERROR")
        return _claim_from_row(
            row,
            claim_id=identity,
            source_id=source_id,
            content_sha256=content_sha256,
            extractor_version=extractor_version,
            owner_token=owner_token,
            lease_until=lease_until,
            now=current,
        )

    async def bind_command(
        self,
        source_id: str | SourceVisualAuthority | None = None,
        content_sha256: str | None = None,
        extractor_version: str | None = None,
        owner_token: str | None = None,
        command_id: str | None = None,
        *,
        authority: SourceVisualAuthority | None = None,
        now: datetime | None = None,
    ) -> SourceVisualClaim:
        source_id, content_sha256, extractor_version, _ = _identity(
            source_id, content_sha256, extractor_version, authority
        )
        owner_token = _hash(owner_token)
        if not command_id:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        current = _now(now)
        identity = claim_identity(source_id, content_sha256, extractor_version)
        result = await _transaction(
            """
            BEGIN TRANSACTION;
            LET $existing = (SELECT * FROM $claim_record)[0];
            IF $existing = NONE OR $existing.owner_token != $owner_token
                    OR $existing.lease_until <= $now {
                THROW "DN_SOURCE_VISUAL_OWNER_MISMATCH";
            };
            IF $existing.command_id != NONE AND $existing.command_id != $command_record {
                THROW "DN_SOURCE_VISUAL_COMMAND_CONFLICT";
            };
            UPDATE $claim_record MERGE { command_id: $command_record, updated_at: $now };
            SELECT * FROM $claim_record;
            COMMIT TRANSACTION;
            """,
            {
                "claim_record": _record("source_visual_claim", identity),
                "command_record": _command_record(command_id),
                "owner_token": owner_token,
                "now": current,
            },
        )
        row = _row(result)
        if row is None:
            row = await _read_exact_row("source_visual_claim", identity)
        _require_live_lease(row, owner_token, current)
        existing_command = _command_text(row.get("command_id"))
        requested_command = _command_text(command_id)
        if existing_command != requested_command:
            if existing_command is None:
                raise SourceVisualRepositoryError("DATABASE_ERROR")
            raise SourceVisualConflictError("COMMAND_CONFLICT")
        return _claim_from_row(
            row,
            claim_id=identity,
            source_id=source_id,
            content_sha256=content_sha256,
            extractor_version=extractor_version,
            owner_token=owner_token,
            lease_until=_datetime(row.get("lease_until"), current) or current,
            now=current,
            command_id=requested_command,
        )

    async def bind_command_and_finalize_operation(
        self,
        source_id: str | SourceVisualAuthority | None = None,
        content_sha256: str | None = None,
        extractor_version: str | None = None,
        owner_token: str | None = None,
        command_id: str | None = None,
        *,
        request_id: str | None = None,
        source_updated_at: datetime | None = None,
        authority: SourceVisualAuthority | None = None,
        now: datetime | None = None,
    ) -> SourceVisualOperationReceipt:
        """Atomically bind one owner-fenced command and its queued receipt."""

        source_id, content_sha256, extractor_version, authority = _identity(
            source_id, content_sha256, extractor_version, authority
        )
        owner_token = _hash(owner_token)
        if not command_id or not request_id:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        if authority is not None and source_updated_at is None:
            source_updated_at = authority.source_updated_at
        source_updated_at = _datetime(source_updated_at)
        if source_updated_at is None:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        current = _now(now)
        claim_id = claim_identity(source_id, content_sha256, extractor_version)
        operation_id = operation_identity(source_id, request_id, "refresh")
        command_record = _command_record(command_id)
        canonical_command_id = _command_text(command_id)
        result = await _transaction(
            """
            BEGIN TRANSACTION;
            LET $claim = (SELECT * FROM $claim_record)[0];
            LET $operation = (SELECT * FROM $operation_record)[0];
            IF $claim = NONE OR $claim.owner_token != $owner_token
                    OR $claim.lease_until <= $now {
                THROW "DN_SOURCE_VISUAL_OWNER_MISMATCH";
            };
            IF $claim.command_id != NONE AND $claim.command_id != $command_record {
                THROW "DN_SOURCE_VISUAL_COMMAND_CONFLICT";
            };
            IF $operation = NONE OR $operation.source_id != $source_record
                    OR $operation.request_id != $request_id
                    OR $operation.operation != "refresh"
                    OR $operation.content_sha256 != $content_sha256
                    OR $operation.source_updated_at != $source_updated_at
                    OR ($operation.command_id != NONE AND $operation.command_id != $command_record)
                    OR ($operation.command_id = NONE AND ($operation.outcome != "queued"
                        OR $operation.error_code != NONE))
                    OR ($operation.command_id = $command_record AND ($operation.outcome != "queued"
                        OR $operation.error_code != NONE)) {
                THROW "DN_SOURCE_VISUAL_REQUEST_CONFLICT";
            };
            UPDATE $claim_record MERGE { command_id: $command_record, updated_at: $now };
            UPDATE $operation_record MERGE {
                command_id: $command_record,
                outcome: "queued",
                error_code: NONE,
                updated_at: $now
            };
            COMMIT TRANSACTION;
            """,
            {
                "claim_record": _record("source_visual_claim", claim_id),
                "operation_record": _record("source_visual_operation", operation_id),
                "source_record": _source_record(source_id),
                "owner_token": owner_token,
                "command_record": command_record,
                "request_id": request_id,
                "source_updated_at": source_updated_at,
                "content_sha256": content_sha256,
                "now": current,
            },
        )
        row = _row(result)
        if row and row.get("command_conflict"):
            raise SourceVisualConflictError("COMMAND_CONFLICT")
        if row and row.get("request_conflict"):
            raise SourceVisualConflictError("REQUEST_CONFLICT")
        if row is None:
            claim_row = await _read_exact_row("source_visual_claim", claim_id)
            _require_live_lease(claim_row, owner_token, current)
            if _command_text(claim_row.get("command_id")) != canonical_command_id:
                raise SourceVisualConflictError("COMMAND_CONFLICT")
            operation_row = await _read_exact_row(
                "source_visual_operation", operation_id
            )
            if operation_row is None:
                raise SourceVisualConflictError("REQUEST_CONFLICT")
        else:
            _require_live_lease(row, owner_token, current)
            operation_row = dict(row)
        operation_row.pop("owner_token", None)
        operation_row.pop("lease_until", None)
        if not _operation_matches(
            operation_row,
            source_id=source_id,
            request_id=request_id,
            source_updated_at=source_updated_at,
            content_sha256=content_sha256,
            operation="refresh",
            command_id=canonical_command_id,
            outcome="queued",
            error_code=None,
        ):
            raise SourceVisualConflictError("REQUEST_CONFLICT")
        receipt = _receipt_from_row(
            operation_row,
            operation_id=operation_id,
            source_id=source_id,
            request_id=request_id,
            source_updated_at=source_updated_at,
            content_sha256=content_sha256,
            operation="refresh",
            command_id=canonical_command_id,
            outcome="queued",
            error_code=None,
            now=current,
            fallback=self._operation_cache.get(operation_id),
        )
        self._operation_cache[operation_id] = receipt
        return receipt

    async def finalize_operation_from_current_claim(
        self,
        source_id: str | SourceVisualAuthority | None = None,
        content_sha256: str | None = None,
        extractor_version: str | None = None,
        command_id: str | None = None,
        *,
        request_id: str | None = None,
        source_updated_at: datetime | None = None,
        authority: SourceVisualAuthority | None = None,
        now: datetime | None = None,
    ) -> SourceVisualOperationReceipt:
        """Repair a queued receipt only while its exact claim command is current."""

        source_id, content_sha256, extractor_version, authority = _identity(
            source_id, content_sha256, extractor_version, authority
        )
        if not command_id or not request_id:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        if authority is not None and source_updated_at is None:
            source_updated_at = authority.source_updated_at
        source_updated_at = _datetime(source_updated_at)
        if source_updated_at is None:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        current = _now(now)
        claim_id = claim_identity(source_id, content_sha256, extractor_version)
        operation_id = operation_identity(source_id, request_id, "refresh")
        command_record = _command_record(command_id)
        canonical_command_id = _command_text(command_id)
        result = await _transaction(
            """
            BEGIN TRANSACTION;
            LET $claim = (SELECT * FROM $claim_record)[0];
            LET $operation = (SELECT * FROM $operation_record)[0];
            IF $claim = NONE OR $claim.source_id != $source_record
                    OR $claim.content_sha256 != $content_sha256
                    OR $claim.extractor_version != $extractor_version
                    OR $claim.command_id != $command_record
                    OR $claim.lease_until <= $now {
                THROW "DN_SOURCE_VISUAL_COMMAND_CONFLICT";
            };
            IF $operation = NONE OR $operation.source_id != $source_record
                    OR $operation.request_id != $request_id
                    OR $operation.operation != "refresh"
                    OR $operation.content_sha256 != $content_sha256
                    OR $operation.source_updated_at != $source_updated_at
                    OR $operation.command_id != NONE
                    OR $operation.outcome != "queued"
                    OR $operation.error_code != NONE {
                THROW "DN_SOURCE_VISUAL_REQUEST_CONFLICT";
            };
            UPDATE $operation_record MERGE {
                command_id: $command_record,
                outcome: "queued",
                error_code: NONE,
                updated_at: $now
            };
            SELECT * FROM $operation_record;
            COMMIT TRANSACTION;
            """,
            {
                "claim_record": _record("source_visual_claim", claim_id),
                "operation_record": _record("source_visual_operation", operation_id),
                "source_record": _source_record(source_id),
                "content_sha256": content_sha256,
                "extractor_version": extractor_version,
                "command_record": command_record,
                "request_id": request_id,
                "source_updated_at": source_updated_at,
                "now": current,
            },
        )
        row = _row(result)
        if row is None:
            claim_row = await _read_exact_row("source_visual_claim", claim_id)
            if (
                claim_row is None
                or _string(claim_row.get("source_id", "")) != source_id
                or claim_row.get("content_sha256") != content_sha256
                or claim_row.get("extractor_version") != extractor_version
                or _command_text(claim_row.get("command_id")) != canonical_command_id
                or (_datetime(claim_row.get("lease_until")) or current) <= current
            ):
                raise SourceVisualConflictError("COMMAND_CONFLICT")
            row = await _read_exact_row("source_visual_operation", operation_id)
        if not row or row.get("claim_changed"):
            raise SourceVisualConflictError("COMMAND_CONFLICT")
        if row.get("request_conflict") or not _operation_matches(
            row,
            source_id=source_id,
            request_id=request_id,
            source_updated_at=source_updated_at,
            content_sha256=content_sha256,
            operation="refresh",
            command_id=canonical_command_id,
            outcome="queued",
            error_code=None,
        ):
            raise SourceVisualConflictError("REQUEST_CONFLICT")
        receipt = _receipt_from_row(
            row,
            operation_id=operation_id,
            source_id=source_id,
            request_id=request_id,
            source_updated_at=source_updated_at,
            content_sha256=content_sha256,
            operation="refresh",
            command_id=canonical_command_id,
            outcome="queued",
            error_code=None,
            now=current,
            fallback=self._operation_cache.get(operation_id),
        )
        self._operation_cache[operation_id] = receipt
        return receipt

    async def complete_claim(
        self,
        source_id: str | SourceVisualAuthority | None = None,
        content_sha256: str | None = None,
        extractor_version: str | None = None,
        owner_token: str | None = None,
        *,
        authority: SourceVisualAuthority | None = None,
        now: datetime | None = None,
    ) -> SourceVisualClaim:
        return await self._finish_claim(
            source_id,
            content_sha256,
            extractor_version,
            owner_token,
            authority=authority,
            now=now,
        )

    async def release_claim(
        self,
        source_id: str | SourceVisualAuthority | None = None,
        content_sha256: str | None = None,
        extractor_version: str | None = None,
        owner_token: str | None = None,
        *,
        authority: SourceVisualAuthority | None = None,
        now: datetime | None = None,
    ) -> SourceVisualClaim:
        return await self._finish_claim(
            source_id,
            content_sha256,
            extractor_version,
            owner_token,
            authority=authority,
            now=now,
        )

    async def _finish_claim(
        self,
        source_id: str | SourceVisualAuthority | None,
        content_sha256: str | None,
        extractor_version: str | None,
        owner_token: str | None,
        *,
        authority: SourceVisualAuthority | None,
        now: datetime | None,
    ) -> SourceVisualClaim:
        source_id, content_sha256, extractor_version, _ = _identity(
            source_id, content_sha256, extractor_version, authority
        )
        owner_token = _hash(owner_token)
        current = _now(now)
        identity = claim_identity(source_id, content_sha256, extractor_version)
        existing = await _read_exact_row("source_visual_claim", identity)
        _require_live_lease(existing, owner_token, current)
        result = await _transaction(
            """
            BEGIN TRANSACTION;
            DELETE $claim_record
                WHERE owner_token = $owner_token AND lease_until > $now
                RETURN BEFORE;
            COMMIT TRANSACTION;
            """,
            {
                "claim_record": _record("source_visual_claim", identity),
                "owner_token": owner_token,
                "now": current,
            },
        )
        row = _row(result)
        if row is None:
            remaining = await _read_exact_row("source_visual_claim", identity)
            if remaining is not None:
                _require_live_lease(remaining, owner_token, current)
                raise SourceVisualRepositoryError("DATABASE_ERROR")
            row = existing
        _require_live_lease(row, owner_token, current)
        return _claim_from_row(
            row,
            claim_id=identity,
            source_id=source_id,
            content_sha256=content_sha256,
            extractor_version=extractor_version,
            owner_token=owner_token,
            lease_until=_datetime(row.get("lease_until"), current) or current,
            now=current,
        )

    async def record_operation(
        self,
        source_id: str | SourceVisualAuthority | None = None,
        request_id: str | None = None,
        operation: str | None = None,
        *,
        authority: SourceVisualAuthority | None = None,
        source_updated_at: datetime | None = None,
        content_sha256: str | None = None,
        command_id: str | None = None,
        outcome: str = "queued",
        error_code: str | None = None,
        now: datetime | None = None,
    ) -> SourceVisualOperationReceipt:
        source_id, content_sha256, extractor_version, authority = _identity(
            source_id,
            content_sha256,
            "source-visual-v1",
            authority,
        )
        del extractor_version
        if not request_id or operation not in {"refresh", "delete"}:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        if authority is not None and source_updated_at is None:
            source_updated_at = authority.source_updated_at
        source_updated_at = _datetime(source_updated_at)
        if source_updated_at is None:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        if outcome not in {"queued", "replayed", "deleted", "failed"}:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        if command_id is not None and not command_id:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        command_record = _command_record(command_id)
        canonical_command_id = _command_text(command_id)
        current = _now(now)
        identity = operation_identity(source_id, request_id, operation)
        result = await _transaction(
            """
            BEGIN TRANSACTION;
            LET $existing = (SELECT * FROM $operation_record)[0];
            IF $existing = NONE THEN
                CREATE $operation_record CONTENT $operation_data;
            ELSE IF $existing.source_id != $source_record OR $existing.request_id != $request_id
                    OR $existing.operation != $operation OR $existing.content_sha256 != $content_sha256
                    OR $existing.source_updated_at != $source_updated_at
                    OR $existing.command_id != $command_record THEN
                RETURN { request_conflict: true, existing: $existing };
            END;
            SELECT * FROM $operation_record;
            COMMIT TRANSACTION;
            """,
            {
                "operation_record": _record("source_visual_operation", identity),
                "source_record": _source_record(source_id),
                "request_id": request_id,
                "source_updated_at": source_updated_at,
                "content_sha256": content_sha256,
                "operation": operation,
                "command_record": command_record,
                "operation_data": {
                    "operation_id": identity,
                    "source_id": _source_record(source_id),
                    "request_id": request_id,
                    "source_updated_at": source_updated_at,
                    "content_sha256": content_sha256,
                    "operation": operation,
                    "command_id": command_record,
                    "outcome": outcome,
                    "error_code": error_code,
                    "created_at": current,
                    "updated_at": current,
                },
            },
        )
        row = _row(result)
        if row is None:
            row = await _read_exact_row("source_visual_operation", identity)
        if row and (
            row.get("request_conflict")
            or not _operation_matches(
                row,
                source_id=source_id,
                request_id=request_id,
                source_updated_at=source_updated_at,
                content_sha256=content_sha256,
                operation=operation,
                command_id=canonical_command_id,
                outcome=outcome,
                error_code=error_code,
            )
        ):
            raise SourceVisualConflictError("REQUEST_CONFLICT")
        fallback = self._operation_cache.get(identity)
        receipt = _receipt_from_row(
            row,
            operation_id=identity,
            source_id=source_id,
            request_id=request_id,
            source_updated_at=source_updated_at,
            content_sha256=content_sha256,
            operation=operation,
            command_id=canonical_command_id,
            outcome=outcome,
            error_code=error_code,
            now=current,
            fallback=fallback,
        )
        self._operation_cache[identity] = receipt
        return receipt

    async def finalize_operation(
        self,
        source_id: str | SourceVisualAuthority | None = None,
        request_id: str | None = None,
        operation: str | None = None,
        *,
        authority: SourceVisualAuthority | None = None,
        source_updated_at: datetime | None = None,
        content_sha256: str | None = None,
        expected_command_id: str | None = None,
        expected_outcome: str = "queued",
        expected_error_code: str | None = None,
        command_id: str | None = None,
        outcome: str = "queued",
        error_code: str | None = None,
        now: datetime | None = None,
    ) -> SourceVisualOperationReceipt:
        """Compare-and-set one queued receipt to its terminal queue outcome."""

        source_id, content_sha256, extractor_version, authority = _identity(
            source_id,
            content_sha256,
            "source-visual-v1",
            authority,
        )
        del extractor_version
        if not request_id or operation not in {"refresh", "delete"}:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        if authority is not None and source_updated_at is None:
            source_updated_at = authority.source_updated_at
        source_updated_at = _datetime(source_updated_at)
        if source_updated_at is None:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        if (
            expected_command_id is not None
            or expected_outcome != "queued"
            or expected_error_code is not None
        ):
            raise SourceVisualRepositoryError("INVALID_INPUT")
        if (
            operation == "delete"
            and command_id is None
            and outcome == "deleted"
            and error_code is None
        ):
            pass
        elif command_id is not None:
            if outcome != "queued" or error_code is not None:
                raise SourceVisualRepositoryError("INVALID_INPUT")
        elif (
            outcome != "failed"
            or not isinstance(error_code, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", error_code)
        ):
            raise SourceVisualRepositoryError("INVALID_INPUT")

        expected_command_record = _command_record(expected_command_id)
        command_record = _command_record(command_id)
        canonical_command_id = _command_text(command_id)
        current = _now(now)
        identity = operation_identity(source_id, request_id, operation)
        result = await _transaction(
            """
            BEGIN TRANSACTION;
            LET $existing = (SELECT * FROM $operation_record)[0];
            IF $existing = NONE OR $existing.source_id != $source_record
                    OR $existing.request_id != $request_id
                    OR $existing.operation != $operation
                    OR $existing.content_sha256 != $content_sha256
                    OR $existing.source_updated_at != $source_updated_at
                    OR $existing.command_id != $expected_command_record
                    OR $existing.outcome != $expected_outcome
                    OR $existing.error_code != $expected_error_code {
                THROW "DN_SOURCE_VISUAL_REQUEST_CONFLICT";
            };
            UPDATE $operation_record MERGE {
                command_id: $command_record,
                outcome: $outcome,
                error_code: $error_code,
                updated_at: $now
            };
            SELECT * FROM $operation_record;
            COMMIT TRANSACTION;
            """,
            {
                "operation_record": _record("source_visual_operation", identity),
                "source_record": _source_record(source_id),
                "request_id": request_id,
                "source_updated_at": source_updated_at,
                "content_sha256": content_sha256,
                "operation": operation,
                "expected_command_record": expected_command_record,
                "expected_outcome": expected_outcome,
                "expected_error_code": expected_error_code,
                "command_record": command_record,
                "outcome": outcome,
                "error_code": error_code,
                "now": current,
            },
        )
        row = _row(result)
        if row is None:
            row = await _read_exact_row("source_visual_operation", identity)
        if row and (
            row.get("request_conflict")
            or not _operation_matches(
                row,
                source_id=source_id,
                request_id=request_id,
                source_updated_at=source_updated_at,
                content_sha256=content_sha256,
                operation=operation,
                command_id=canonical_command_id,
                outcome=outcome,
                error_code=error_code,
            )
        ):
            raise SourceVisualConflictError("REQUEST_CONFLICT")
        receipt = _receipt_from_row(
            row,
            operation_id=identity,
            source_id=source_id,
            request_id=request_id,
            source_updated_at=source_updated_at,
            content_sha256=content_sha256,
            operation=operation,
            command_id=canonical_command_id,
            outcome=outcome,
            error_code=error_code,
            now=current,
            fallback=self._operation_cache.get(identity),
        )
        self._operation_cache[identity] = receipt
        return receipt

    async def get_operation(
        self,
        source_id: str,
        request_id: str,
        operation: str,
    ) -> SourceVisualOperationReceipt | None:
        source_id = _source_id(source_id)
        if not request_id or operation not in {"refresh", "delete"}:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        identity = operation_identity(source_id, request_id, operation)
        result = await _transaction(
            "SELECT * FROM $operation_record;",
            {"operation_record": _record("source_visual_operation", identity)},
        )
        row = _row(result)
        if row is None:
            return self._operation_cache.get(identity)
        return _receipt_from_row(
            row,
            operation_id=identity,
            source_id=source_id,
            request_id=request_id,
            source_updated_at=_datetime(row.get("source_updated_at")) or _now(None),
            content_sha256=row.get("content_sha256", "0" * 64),
            operation=operation,
            command_id=row.get("command_id"),
            outcome=row.get("outcome", "failed"),
            error_code=row.get("error_code"),
            now=_now(None),
            fallback=self._operation_cache.get(identity),
        )

    async def find_completed_delete(
        self,
        source_id: str,
        source_updated_at: datetime,
        content_sha256: str,
    ) -> SourceVisualOperationReceipt | None:
        """Find one exact successful deletion that suppresses auto-ingest."""

        source_id = _source_id(source_id)
        source_updated_at = _datetime(source_updated_at)
        _hash(content_sha256)
        if source_updated_at is None:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        rows = _rows(
            await _transaction(
                """
                SELECT * FROM source_visual_operation
                WHERE source_id = $source_record
                    AND source_updated_at = $source_updated_at
                    AND content_sha256 = $content_sha256
                    AND operation = "delete"
                    AND outcome = "deleted"
                ORDER BY updated_at DESC LIMIT 1;
                """,
                {
                    "source_record": _source_record(source_id),
                    "source_updated_at": source_updated_at,
                    "content_sha256": content_sha256,
                },
            )
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise SourceVisualRepositoryError("MALFORMED_ROW")
        row = rows[0]
        if not _operation_matches(
            row,
            source_id=source_id,
            request_id=row.get("request_id", ""),
            source_updated_at=source_updated_at,
            content_sha256=content_sha256,
            operation="delete",
            command_id=None,
            outcome="deleted",
            error_code=None,
        ):
            raise SourceVisualRepositoryError("MALFORMED_ROW")
        return _receipt_from_row(
            row,
            operation_id=operation_identity(source_id, row["request_id"], "delete"),
            source_id=source_id,
            request_id=row["request_id"],
            source_updated_at=source_updated_at,
            content_sha256=content_sha256,
            operation="delete",
            command_id=None,
            outcome="deleted",
            error_code=None,
            now=_now(None),
        )

    async def find_accepted_delete(
        self,
        source_id: str,
        source_updated_at: datetime,
        content_sha256: str,
    ) -> SourceVisualOperationReceipt | None:
        """Find one exact queued or completed delete intent for auto-ingest fencing."""

        source_id = _source_id(source_id)
        source_updated_at = _datetime(source_updated_at)
        _hash(content_sha256)
        if source_updated_at is None:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        rows = _rows(
            await _transaction(
                """
                SELECT * FROM source_visual_operation
                WHERE source_id = $source_record
                    AND source_updated_at = $source_updated_at
                    AND content_sha256 = $content_sha256
                    AND operation = "delete"
                    AND outcome IN ["queued", "deleted"]
                ORDER BY updated_at DESC LIMIT 1;
                """,
                {
                    "source_record": _source_record(source_id),
                    "source_updated_at": source_updated_at,
                    "content_sha256": content_sha256,
                },
            )
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise SourceVisualRepositoryError("MALFORMED_ROW")
        row = rows[0]
        outcome = row.get("outcome")
        if outcome not in {"queued", "deleted"} or not _operation_matches(
            row,
            source_id=source_id,
            request_id=row.get("request_id", ""),
            source_updated_at=source_updated_at,
            content_sha256=content_sha256,
            operation="delete",
            command_id=None,
            outcome=outcome,
            error_code=None,
        ):
            raise SourceVisualRepositoryError("MALFORMED_ROW")
        return _receipt_from_row(
            row,
            operation_id=operation_identity(source_id, row["request_id"], "delete"),
            source_id=source_id,
            request_id=row["request_id"],
            source_updated_at=source_updated_at,
            content_sha256=content_sha256,
            operation="delete",
            command_id=None,
            outcome=outcome,
            error_code=None,
            now=_now(None),
        )

    async def post_delete_refresh_needs_reacquire(
        self,
        *,
        source_id: str,
        content_sha256: str,
        extractor_version: str,
        request_id: str,
        source_updated_at: datetime,
        now: datetime | None = None,
    ) -> bool:
        """Atomically fence a queued explicit refresh from pre-delete work.

        ``True`` means the exact queued receipt was created after the latest
        accepted delete but the current claim has no command created after that
        delete.  Callers must try claim acquisition and must not expose or bind
        the pre-delete command.
        """

        source_id, content_sha256, extractor_version, _ = _identity(
            source_id, content_sha256, extractor_version, None
        )
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 256:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        source_updated_at = _datetime(source_updated_at)
        if source_updated_at is None:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        current = _now(now)
        claim_id = claim_identity(source_id, content_sha256, extractor_version)
        operation_id = operation_identity(source_id, request_id, "refresh")
        row = _row(
            await _transaction(
                """
                SELECT *,
                    (SELECT * FROM $claim_record)[0] AS exact_claim,
                    (
                    SELECT * FROM source_visual_operation
                    WHERE source_id = $source_record
                        AND source_updated_at = $source_updated_at
                        AND content_sha256 = $content_sha256
                        AND operation = "delete"
                        AND outcome IN ["queued", "deleted"]
                    ORDER BY created_at DESC, updated_at DESC
                    LIMIT 1
                    )[0] AS delete_intent,
                    (
                    SELECT * FROM source_visual_operation
                    WHERE source_id = $source_record
                        AND source_updated_at = $source_updated_at
                        AND content_sha256 = $content_sha256
                        AND operation = "refresh"
                        AND command_id = (
                            SELECT VALUE command_id FROM $claim_record
                        )[0]
                    ORDER BY created_at DESC, updated_at DESC
                    LIMIT 1
                    )[0] AS command_refresh
                FROM $operation_record;
                """,
                {
                    "operation_record": _record(
                        "source_visual_operation", operation_id
                    ),
                    "claim_record": _record("source_visual_claim", claim_id),
                    "source_record": _source_record(source_id),
                    "request_id": request_id,
                    "source_updated_at": source_updated_at,
                    "content_sha256": content_sha256,
                },
            )
        )
        operation_row = dict(row or {})
        claim = operation_row.pop("exact_claim", None)
        delete_intent = operation_row.pop("delete_intent", None)
        command_refresh = operation_row.pop("command_refresh", None)
        operation_command = _command_text(operation_row.get("command_id"))
        claim_command = (
            _command_text(claim.get("command_id"))
            if isinstance(claim, Mapping)
            else None
        )
        if (
            not operation_row
            or not _operation_matches(
                operation_row,
                source_id=source_id,
                request_id=request_id,
                source_updated_at=source_updated_at,
                content_sha256=content_sha256,
                operation="refresh",
                command_id=operation_command,
                outcome="queued",
                error_code=None,
            )
            or (operation_command is not None and operation_command != claim_command)
        ):
            raise SourceVisualConflictError("REQUEST_CONFLICT")

        if delete_intent is None:
            return False
        if not isinstance(delete_intent, Mapping):
            raise SourceVisualRepositoryError("MALFORMED_ROW")
        operation_created_at = _datetime(operation_row.get("created_at"))
        delete_created_at = _datetime(delete_intent.get("created_at"))
        if operation_created_at is None or delete_created_at is None:
            raise SourceVisualRepositoryError("MALFORMED_ROW")
        if operation_created_at <= delete_created_at:
            return False

        newer_bound_command = (
            isinstance(claim, Mapping)
            and _string(claim.get("source_id", "")) == source_id
            and claim.get("content_sha256") == content_sha256
            and claim.get("extractor_version") == extractor_version
            and claim_command is not None
            and (lease_until := _datetime(claim.get("lease_until"))) is not None
            and lease_until > current
            and isinstance(command_refresh, Mapping)
            and _command_text(command_refresh.get("command_id")) == claim_command
            and (command_created_at := _datetime(command_refresh.get("created_at")))
            is not None
            and command_created_at > delete_created_at
        )
        return not newer_bound_command

    async def list_current(
        self, revisions: Mapping[str, datetime]
    ) -> dict[str, SourceVisualRecord]:
        if len(revisions) > _MAX_REVISIONS:
            raise SourceVisualRepositoryError("MAX_REVISIONS")
        normalised: dict[str, datetime] = {}
        for source_id, revision in revisions.items():
            source_key = _source_id(source_id)
            parsed = _datetime(revision)
            if parsed is None:
                raise SourceVisualRepositoryError("INVALID_INPUT")
            normalised[source_key] = parsed
        if not normalised:
            return {}
        variables = {
            "source_records": [_source_record(source_id) for source_id in normalised],
            "source_revision_values": list(normalised.values()),
            "source_revision_pairs": [
                [_source_record(source_id), revision]
                for source_id, revision in normalised.items()
            ],
            "limit": _MAX_REVISIONS,
        }
        # The SurrealDB Python driver discards a top-level ``RETURN`` envelope
        # containing subqueries.  Keep both reads bounded and parameterized,
        # but issue them separately so ready rows cannot disappear in real DB
        # execution while the exact source/revision pair filter is preserved.
        ready_result = await _transaction(
            "SELECT * FROM source_visual_cache "
            "WHERE [source_id, source_updated_at] IN $source_revision_pairs "
            "LIMIT $limit;",
            variables,
        )
        legacy_envelope = _row(ready_result)
        if (
            isinstance(legacy_envelope, Mapping)
            and isinstance(legacy_envelope.get("ready"), list)
            and isinstance(legacy_envelope.get("statuses"), list)
        ):
            # Preserve the bounded combined envelope accepted by older adapters
            # and unit fakes while real SurrealDB uses the two explicit reads.
            ready_rows = _rows(legacy_envelope["ready"])
            status_rows = _rows(legacy_envelope["statuses"])
        else:
            ready_rows = _rows(ready_result)
            status_rows = _rows(
                await _transaction(
                    "SELECT *, command_id.status AS command_status "
                    "FROM source_visual_operation "
                    "WHERE [source_id, source_updated_at] IN $source_revision_pairs "
                    'AND operation = "refresh" '
                    "ORDER BY updated_at DESC LIMIT $limit;",
                    variables,
                )
            )
        current: dict[str, SourceVisualRecord] = {}
        for raw_row in ready_rows:
            try:
                record = _record_from_row(raw_row)
            except SourceVisualRepositoryError:
                continue
            expected = normalised.get(record.source_id)
            if expected is None or record.source_updated_at != expected:
                continue
            current[record.source_id] = record
        statuses: dict[str, Mapping[str, object]] = {}
        for raw in status_rows:
            source_id = _string(raw.get("source_id", ""))
            revision = _datetime(raw.get("source_updated_at"))
            if (
                source_id not in normalised
                or revision != normalised[source_id]
                or source_id in current
                or source_id in statuses
            ):
                continue
            outcome = raw.get("outcome")
            command = raw.get("command_id")
            command_id = _command_text(command)
            command_status = raw.get("command_status")
            if isinstance(command, Mapping):
                command_id = _command_text(command.get("id"))
                command_status = command.get("status", command_status)
            if outcome == "failed" or command_status == "failed":
                state = "failed"
            elif command_status in {"running", "processing"}:
                state = "processing"
            elif command_status in {"queued", "pending"} or outcome in {
                "queued",
                "replayed",
            }:
                state = "queued"
            else:
                state = "unavailable"
            error_code = raw.get("error_code") if state == "failed" else None
            statuses[source_id] = {
                "state": state,
                "command_id": command_id,
                "error_code": error_code,
                "updated_at": raw.get("updated_at"),
            }
        return _CurrentVisualRows(current, statuses=statuses)

    async def list_current_by_source_file_sha256(
        self, values: Sequence[str] | tuple[str, ...]
    ) -> list[SourceVisualRecord]:
        """Batch-match Capture's existing file digests to current cache rows.

        The query binds only full SHA-256 values and verifies the cache row
        against the linked source's present revision.  It never reads a capture
        path or creates source/visual state.
        """

        hashes = tuple(dict.fromkeys(values))
        if len(hashes) > _MAX_REVISIONS or any(
            _hash(value) is None for value in hashes
        ):
            raise SourceVisualRepositoryError("INVALID_INPUT")
        if not hashes:
            return []
        rows = _rows(
            await _transaction(
                """
                SELECT *, source_id.updated AS source_current_updated
                FROM source_visual_cache
                WHERE source_file_sha256 IN $source_file_sha256s
                LIMIT $limit;
                """,
                {"source_file_sha256s": list(hashes), "limit": _MAX_REVISIONS},
            )
        )
        if len(rows) > _MAX_REVISIONS:
            raise SourceVisualRepositoryError("MALFORMED_ROW")
        current: dict[str, SourceVisualRecord] = {}
        for raw in rows:
            candidate = dict(raw)
            live_updated = _datetime(candidate.pop("source_current_updated", None))
            try:
                record = _record_from_row(candidate)
            except SourceVisualRepositoryError:
                continue
            if (
                record.source_file_sha256 not in hashes
                or live_updated is None
                or live_updated != record.source_updated_at
            ):
                continue
            current.setdefault(record.source_file_sha256, record)
        return list(current.values())

    async def find_ready_by_asset_relpath(
        self, asset_relpath: str
    ) -> SourceVisualRecord | None:
        if (
            not isinstance(asset_relpath, str)
            or _ASSET_RELPATH_RE.fullmatch(asset_relpath) is None
        ):
            raise SourceVisualRepositoryError("INVALID_INPUT")
        rows = _rows(
            await _transaction(
                "SELECT * FROM source_visual_cache "
                "WHERE asset_relpath = $asset_relpath LIMIT 2;",
                {"asset_relpath": asset_relpath},
            )
        )
        if len(rows) > 1:
            raise SourceVisualRepositoryError("MALFORMED_ROW")
        if not rows:
            return None
        record = _record_from_row(rows[0])
        if record.asset_relpath != asset_relpath:
            raise SourceVisualRepositoryError("MALFORMED_ROW")
        return record

    async def list_ready_for_eviction(self, *, limit: int) -> list[SourceVisualRecord]:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise SourceVisualRepositoryError("INVALID_INPUT")
        rows = _rows(
            await _transaction(
                "SELECT * FROM source_visual_cache "
                "ORDER BY updated_at ASC LIMIT $limit;",
                {"limit": limit},
            )
        )
        if len(rows) > limit:
            raise SourceVisualRepositoryError("MALFORMED_ROW")
        records: list[SourceVisualRecord] = []
        for row in rows:
            try:
                records.append(_record_from_row(row))
            except SourceVisualRepositoryError:
                continue
        return records

    async def delete_ready_if_current(self, record: SourceVisualRecord) -> bool:
        if not isinstance(record, SourceVisualRecord):
            raise SourceVisualRepositoryError("INVALID_INPUT")
        cache_id = _cache_identity(record.source_id, record.content_sha256)
        before = await _read_exact_row("source_visual_cache", cache_id)
        if before is None:
            return False
        try:
            if _record_from_row(before) != record:
                return False
        except SourceVisualRepositoryError:
            return False
        rows = _rows(
            await _transaction(
                "BEGIN TRANSACTION; "
                "LET $claim = (SELECT lease_until FROM $claim_record)[0]; "
                "DELETE $cache_record WHERE source_id = $source_record "
                "AND source_updated_at = $source_updated_at "
                "AND content_sha256 = $content_sha256 "
                "AND asset_sha256 = $asset_sha256 "
                "AND asset_relpath = $asset_relpath "
                "AND NOT ($claim != NONE AND $claim.lease_until > time::now()) "
                "AND updated_at = $updated_at RETURN BEFORE; "
                "COMMIT TRANSACTION;",
                {
                    "cache_record": _record(
                        "source_visual_cache",
                        cache_id,
                    ),
                    "source_record": _source_record(record.source_id),
                    "claim_record": _record(
                        "source_visual_claim",
                        claim_identity(
                            record.source_id,
                            record.content_sha256,
                            record.extractor_version,
                        ),
                    ),
                    "source_updated_at": record.source_updated_at,
                    "content_sha256": record.content_sha256,
                    "asset_sha256": record.asset_sha256,
                    "asset_relpath": record.asset_relpath,
                    "updated_at": record.updated_at,
                },
            )
        )
        if any(row.get("claim_active") is True for row in rows):
            return False
        if not rows:
            claim = await _read_exact_row(
                "source_visual_claim",
                claim_identity(
                    record.source_id,
                    record.content_sha256,
                    record.extractor_version,
                ),
            )
            if claim is not None:
                lease_until = _datetime(claim.get("lease_until"))
                if lease_until is None or lease_until > _now(None):
                    return False
            return await _read_exact_row("source_visual_cache", cache_id) is None
        if len(rows) != 1:
            raise SourceVisualRepositoryError("MALFORMED_ROW")
        deleted = _record_from_row(rows[0])
        if deleted != record:
            raise SourceVisualRepositoryError("MALFORMED_ROW")
        return True

    async def is_claim_active(self, record: SourceVisualRecord) -> bool:
        if not isinstance(record, SourceVisualRecord):
            raise SourceVisualRepositoryError("INVALID_INPUT")
        identity = claim_identity(
            record.source_id, record.content_sha256, record.extractor_version
        )
        rows = _rows(
            await _transaction(
                "SELECT claim_id FROM $claim_record "
                "WHERE lease_until > time::now() LIMIT 1;",
                {"claim_record": _record("source_visual_claim", identity)},
            )
        )
        if not rows:
            return False
        if len(rows) != 1 or _plain_id(rows[0].get("claim_id")) != identity:
            raise SourceVisualRepositoryError("MALFORMED_ROW")
        return True

    async def publish_ready(
        self,
        record: SourceVisualRecord | Mapping[str, Any] | str | None = None,
        *,
        source_id: str | SourceVisualAuthority | None = None,
        content_sha256: str | None = None,
        extractor_version: str | None = None,
        owner_token: str | None = None,
        request_id: str | None = None,
        source_updated_at: datetime | None = None,
        authority: SourceVisualAuthority | None = None,
        now: datetime | None = None,
    ) -> SourceVisualRecord:
        record, source_id = self._normalise_record_argument(record, source_id)
        requested_source_id = source_id
        requested_content_sha256 = content_sha256
        requested_extractor_version = extractor_version
        source_id, content_sha256, extractor_version, authority = _identity(
            source_id, content_sha256, extractor_version, authority
        )
        self._validate_authority_inputs(
            authority,
            requested_source_id,
            requested_content_sha256,
            requested_extractor_version,
            source_updated_at,
        )
        source_updated_at = _datetime(
            source_updated_at or (authority.source_updated_at if authority else None)
        )
        if source_updated_at is None:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        if request_id is not None and (
            not isinstance(request_id, str) or not 1 <= len(request_id) <= 256
        ):
            raise SourceVisualRepositoryError("INVALID_INPUT")
        owner_token = _hash(owner_token)
        current = _now(now)
        ready = self._ready_record(
            record,
            source_id=source_id,
            content_sha256=content_sha256,
            extractor_version=extractor_version,
            source_updated_at=source_updated_at,
            now=current,
            authority=authority,
        )
        record_data = ready.model_dump()
        record_data["source_id"] = _source_record(source_id)
        result = await _transaction(
            """
            BEGIN TRANSACTION;
            LET $source_row = (SELECT updated FROM $source_record)[0];
            LET $claim = (SELECT * FROM $claim_record)[0];
            LET $refresh = (SELECT * FROM $refresh_operation_record)[0];
            LET $delete_intent = (
                SELECT * FROM source_visual_operation
                WHERE source_id = $source_record
                    AND source_updated_at = $source_updated_at
                    AND content_sha256 = $content_sha256
                    AND operation = "delete"
                    AND outcome IN ["queued", "deleted"]
                ORDER BY created_at DESC, updated_at DESC
                LIMIT 1
            )[0];
            IF $delete_intent != NONE AND (
                $refresh = NONE
                OR $refresh.source_id != $source_record
                OR $refresh.request_id != $request_id
                OR $refresh.operation != "refresh"
                OR $refresh.source_updated_at != $source_updated_at
                OR $refresh.content_sha256 != $content_sha256
                OR $refresh.command_id != $claim.command_id
                OR $refresh.outcome != "queued"
                OR $refresh.error_code != NONE
                OR $refresh.created_at <= $delete_intent.created_at
            ) {
                THROW "DN_SOURCE_VISUAL_DELETE_REQUESTED";
            };
            IF time::floor($source_row.updated, 1us)
                    != time::floor($source_updated_at, 1us) {
                THROW "DN_SOURCE_VISUAL_SOURCE_STALE";
            };
            IF $claim = NONE OR $claim.owner_token != $owner_token
                    OR $claim.lease_until <= $now {
                THROW "DN_SOURCE_VISUAL_OWNER_MISMATCH";
            };
            UPSERT $cache_record CONTENT $record_data;
            COMMIT TRANSACTION;
            """,
            {
                "source_record": _source_record(source_id),
                "claim_record": _record(
                    "source_visual_claim",
                    claim_identity(source_id, content_sha256, extractor_version),
                ),
                "refresh_operation_record": _record(
                    "source_visual_operation",
                    operation_identity(
                        source_id,
                        request_id or "__publish_without_refresh_receipt__",
                        "refresh",
                    ),
                ),
                "cache_record": _record(
                    "source_visual_cache", _cache_identity(source_id, content_sha256)
                ),
                "source_updated_at": source_updated_at,
                "content_sha256": content_sha256,
                "request_id": request_id or "",
                "owner_token": owner_token,
                "now": current,
                "record_data": record_data,
            },
        )
        row = _row(result)
        if row and row.get("delete_requested"):
            raise SourceVisualConflictError("DELETE_REQUESTED")
        if row and row.get("source_stale"):
            raise SourceVisualConflictError("SOURCE_STALE")
        if row is None:
            claim_row = await _read_exact_row(
                "source_visual_claim",
                claim_identity(source_id, content_sha256, extractor_version),
            )
            _require_live_lease(claim_row, owner_token, current)
            source_row = _row(
                await _transaction(
                    "SELECT updated FROM $source_record;",
                    {"source_record": _source_record(source_id)},
                )
            )
            if (
                _datetime(source_row.get("updated") if source_row else None)
                != source_updated_at
            ):
                raise SourceVisualConflictError("SOURCE_STALE")
            delete_rows = _rows(
                await _transaction(
                    "SELECT * FROM source_visual_operation "
                    "WHERE source_id = $source_record "
                    "AND source_updated_at = $source_updated_at "
                    "AND content_sha256 = $content_sha256 "
                    'AND operation = "delete" '
                    'AND outcome IN ["queued", "deleted"] '
                    "ORDER BY created_at DESC, updated_at DESC LIMIT 1;",
                    {
                        "source_record": _source_record(source_id),
                        "source_updated_at": source_updated_at,
                        "content_sha256": content_sha256,
                    },
                )
            )
            if delete_rows:
                refresh_row = (
                    await _read_exact_row(
                        "source_visual_operation",
                        operation_identity(source_id, request_id, "refresh"),
                    )
                    if request_id
                    else None
                )
                delete_created_at = _datetime(delete_rows[0].get("created_at"))
                refresh_created_at = _datetime(
                    refresh_row.get("created_at") if refresh_row else None
                )
                if not (
                    refresh_row is not None
                    and _string(refresh_row.get("source_id", "")) == source_id
                    and refresh_row.get("request_id") == request_id
                    and refresh_row.get("operation") == "refresh"
                    and _datetime(refresh_row.get("source_updated_at"))
                    == source_updated_at
                    and refresh_row.get("content_sha256") == content_sha256
                    and _command_text(refresh_row.get("command_id"))
                    == _command_text(claim_row.get("command_id"))
                    and refresh_row.get("outcome") == "queued"
                    and refresh_row.get("error_code") is None
                    and delete_created_at is not None
                    and refresh_created_at is not None
                    and refresh_created_at > delete_created_at
                ):
                    raise SourceVisualConflictError("DELETE_REQUESTED")
            cache_row = await _read_exact_row(
                "source_visual_cache", _cache_identity(source_id, content_sha256)
            )
            if cache_row is None or _record_from_row(cache_row) != ready:
                raise SourceVisualRepositoryError("DATABASE_ERROR")
            row = dict(claim_row or {})
            row["source_updated_at"] = source_updated_at
        _require_live_lease(row, owner_token, current)
        return ready

    async def delete_ready(
        self,
        record: SourceVisualRecord | Mapping[str, Any] | str | None = None,
        *,
        source_id: str | SourceVisualAuthority | None = None,
        content_sha256: str | None = None,
        extractor_version: str | None = None,
        owner_token: str | None = None,
        source_updated_at: datetime | None = None,
        authority: SourceVisualAuthority | None = None,
        now: datetime | None = None,
    ) -> SourceVisualRecord:
        record, source_id = self._normalise_record_argument(record, source_id)
        requested_source_id = source_id
        requested_content_sha256 = content_sha256
        requested_extractor_version = extractor_version
        source_id, content_sha256, extractor_version, authority = _identity(
            source_id, content_sha256, extractor_version, authority
        )
        self._validate_authority_inputs(
            authority,
            requested_source_id,
            requested_content_sha256,
            requested_extractor_version,
            source_updated_at,
        )
        source_updated_at = _datetime(
            source_updated_at or (authority.source_updated_at if authority else None)
        )
        if source_updated_at is None:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        owner_token = _hash(owner_token)
        current = _now(now)
        ready = self._ready_record(
            record,
            source_id=source_id,
            content_sha256=content_sha256,
            extractor_version=extractor_version,
            source_updated_at=source_updated_at,
            now=current,
            authority=authority,
        )
        result = await _transaction(
            """
            BEGIN TRANSACTION;
            LET $source_row = (SELECT updated FROM $source_record)[0];
            LET $claim = (SELECT * FROM $claim_record)[0];
            IF time::floor($source_row.updated, 1us)
                    != time::floor($source_updated_at, 1us) {
                THROW "DN_SOURCE_VISUAL_SOURCE_STALE";
            };
            IF $claim = NONE OR $claim.owner_token != $owner_token
                    OR $claim.lease_until <= $now {
                THROW "DN_SOURCE_VISUAL_OWNER_MISMATCH";
            };
            DELETE $cache_record;
            COMMIT TRANSACTION;
            """,
            {
                "source_record": _source_record(source_id),
                "claim_record": _record(
                    "source_visual_claim",
                    claim_identity(source_id, content_sha256, extractor_version),
                ),
                "cache_record": _record(
                    "source_visual_cache", _cache_identity(source_id, content_sha256)
                ),
                "source_updated_at": source_updated_at,
                "owner_token": owner_token,
                "now": current,
            },
        )
        row = _row(result)
        if row and row.get("source_stale"):
            raise SourceVisualConflictError("SOURCE_STALE")
        if row is None:
            claim_row = await _read_exact_row(
                "source_visual_claim",
                claim_identity(source_id, content_sha256, extractor_version),
            )
            _require_live_lease(claim_row, owner_token, current)
            source_row = _row(
                await _transaction(
                    "SELECT updated FROM $source_record;",
                    {"source_record": _source_record(source_id)},
                )
            )
            if (
                _datetime(source_row.get("updated") if source_row else None)
                != source_updated_at
            ):
                raise SourceVisualConflictError("SOURCE_STALE")
            cache_row = await _read_exact_row(
                "source_visual_cache", _cache_identity(source_id, content_sha256)
            )
            if cache_row is not None:
                raise SourceVisualRepositoryError("DATABASE_ERROR")
            row = dict(claim_row or {})
            row["source_updated_at"] = source_updated_at
        _require_live_lease(row, owner_token, current)
        return ready

    @staticmethod
    def _normalise_record_argument(
        record: SourceVisualRecord | Mapping[str, Any] | str | None,
        source_id: str | SourceVisualAuthority | None,
    ) -> tuple[
        SourceVisualRecord | Mapping[str, Any] | None,
        str | SourceVisualAuthority | None,
    ]:
        if isinstance(record, str) and source_id is None:
            return None, record
        return record if record is not None else None, source_id

    @staticmethod
    def _validate_authority_inputs(
        authority: SourceVisualAuthority | None,
        source_id: str | SourceVisualAuthority | None,
        content_sha256: str | None,
        extractor_version: str | None,
        source_updated_at: datetime | None,
    ) -> None:
        if authority is None:
            return
        if (
            source_id is not None
            and not isinstance(source_id, SourceVisualAuthority)
            and _source_id(source_id) != authority.source_id
        ):
            raise SourceVisualRepositoryError("INVALID_INPUT")
        if content_sha256 is not None and content_sha256 != authority.content_sha256:
            raise SourceVisualRepositoryError("INVALID_INPUT")
        if (
            extractor_version is not None
            and extractor_version != authority.extractor_version
        ):
            raise SourceVisualRepositoryError("INVALID_INPUT")
        if (
            source_updated_at is not None
            and _datetime(source_updated_at) != authority.source_updated_at
        ):
            raise SourceVisualConflictError("SOURCE_STALE")

    @staticmethod
    def _ready_record(
        record: SourceVisualRecord | Mapping[str, Any] | None,
        *,
        source_id: str,
        content_sha256: str,
        extractor_version: str,
        source_updated_at: datetime,
        now: datetime,
        authority: SourceVisualAuthority | None = None,
    ) -> SourceVisualRecord:
        def ensure_bound(parsed: SourceVisualRecord) -> SourceVisualRecord:
            if parsed.source_id != source_id or parsed.content_sha256 != content_sha256:
                raise SourceVisualRepositoryError("INVALID_INPUT")
            if parsed.source_updated_at != source_updated_at:
                raise SourceVisualConflictError("SOURCE_STALE")
            if parsed.extractor_version != extractor_version:
                raise SourceVisualRepositoryError("INVALID_INPUT")
            if authority is not None:
                if (
                    parsed.source_id != authority.source_id
                    or parsed.source_updated_at != authority.source_updated_at
                    or parsed.source_file_sha256 != authority.source_file_sha256
                    or parsed.content_sha256 != authority.content_sha256
                    or parsed.extractor_version != authority.extractor_version
                ):
                    raise SourceVisualRepositoryError("INVALID_INPUT")
            return parsed

        if isinstance(record, SourceVisualRecord):
            return ensure_bound(record)
        if isinstance(record, Mapping):
            try:
                parsed = SourceVisualRecord.model_validate(dict(record))
            except Exception as exc:
                raise SourceVisualRepositoryError("MALFORMED_ROW") from exc
            return ensure_bound(parsed)
        return SourceVisualRecord(
            source_id=source_id,
            source_updated_at=source_updated_at,
            source_file_sha256=authority.source_file_sha256 if authority else None,
            content_sha256=content_sha256,
            asset_sha256=content_sha256,
            asset_relpath=f"{content_sha256[:2]}/{content_sha256}/"
            + f"{content_sha256}.webp",
            origin="embedded",
            source_locator={"page": 1},
            extractor_version=extractor_version,
            alt_text="Source visual",
            width=1,
            height=1,
            created_at=now,
            updated_at=now,
        )


__all__ = [
    "SourceVisualConflictError",
    "SourceVisualRepository",
    "SourceVisualRepositoryError",
    "claim_identity",
    "operation_identity",
]
