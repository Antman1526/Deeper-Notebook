"""Owner-fenced persistence for source visual claims and operation receipts."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
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
        "SOURCE_STALE",
    }
)


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
        record_id = identity if identity.startswith(f"{table}:") else f"{table}:{identity}"
        return ensure_record_id(record_id)
    except (TypeError, ValueError):
        raise SourceVisualRepositoryError("INVALID_INPUT") from None


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
        raise SourceVisualRepositoryError("DATABASE_ERROR") from exc


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
    if data["command_id"] is not None:
        data["command_id"] = _string(data["command_id"])
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
    row_command = row.get("command_id")
    if row_command is not None:
        row_command = _string(row_command)
    return (
        row_source == source_id
        and row.get("request_id") == request_id
        and row_revision == source_updated_at
        and row.get("content_sha256") == content_sha256
        and row.get("operation") == operation
        and row_command == command_id
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
    if data["command_id"] is not None:
        data["command_id"] = _string(data["command_id"])
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
            if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or lease_seconds <= 0:
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
        if row and (row.get("conflict") or row.get("existing")):
            existing = row.get("existing")
            if not isinstance(existing, Mapping):
                existing = row
            existing_until = _datetime(existing.get("lease_until"))
            if (
                existing.get("owner_token") != owner_token
                and (existing_until is None or existing_until > current)
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
            if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or lease_seconds <= 0:
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
            IF $existing = NONE OR $existing.owner_token != $owner_token THEN
                RETURN { owner_mismatch: true, existing: $existing };
            END;
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
        if not row or row.get("owner_mismatch") or row.get("owner_token") != owner_token:
            raise SourceVisualConflictError("OWNER_MISMATCH")
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
            IF $existing = NONE OR $existing.owner_token != $owner_token THEN
                RETURN { owner_mismatch: true, existing: $existing };
            ELSE IF $existing.command_id != NONE AND $existing.command_id != $command_record THEN
                RETURN { command_conflict: true, existing: $existing };
            END;
            UPDATE $claim_record MERGE { command_id: $command_record, updated_at: $now };
            SELECT * FROM $claim_record;
            COMMIT TRANSACTION;
            """,
            {
                "claim_record": _record("source_visual_claim", identity),
                "command_record": _record("command", command_id),
                "owner_token": owner_token,
                "now": current,
            },
        )
        row = _row(result)
        if not row or row.get("owner_mismatch") or row.get("owner_token") != owner_token:
            raise SourceVisualConflictError("OWNER_MISMATCH")
        existing_command = row.get("command_id")
        if existing_command is not None and _string(existing_command) not in {
            command_id,
            f"command:{command_id}",
        }:
            raise SourceVisualConflictError("COMMAND_CONFLICT")
        row = dict(row)
        row["command_id"] = command_id
        return _claim_from_row(
            row,
            claim_id=identity,
            source_id=source_id,
            content_sha256=content_sha256,
            extractor_version=extractor_version,
            owner_token=owner_token,
            lease_until=_datetime(row.get("lease_until"), current) or current,
            now=current,
            command_id=command_id,
        )

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
            action="complete",
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
            action="release",
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
        action: str,
    ) -> SourceVisualClaim:
        source_id, content_sha256, extractor_version, _ = _identity(
            source_id, content_sha256, extractor_version, authority
        )
        owner_token = _hash(owner_token)
        current = _now(now)
        identity = claim_identity(source_id, content_sha256, extractor_version)
        result = await _transaction(
            f"""
            BEGIN TRANSACTION;
            LET $existing = (SELECT * FROM $claim_record)[0];
            IF $existing = NONE OR $existing.owner_token != $owner_token THEN
                RETURN {{ owner_mismatch: true, existing: $existing }};
            END;
            DELETE $claim_record;
            COMMIT TRANSACTION;
            """,
            {
                "claim_record": _record("source_visual_claim", identity),
                "owner_token": owner_token,
                "now": current,
            },
        )
        row = _row(result)
        if not row or row.get("owner_mismatch") or row.get("owner_token") != owner_token:
            raise SourceVisualConflictError("OWNER_MISMATCH")
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
                    OR $existing.source_updated_at != $source_updated_at THEN
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
                "operation_data": {
                    "operation_id": identity,
                    "source_id": _source_record(source_id),
                    "request_id": request_id,
                    "source_updated_at": source_updated_at,
                    "content_sha256": content_sha256,
                    "operation": operation,
                    "command_id": command_id,
                    "outcome": outcome,
                    "error_code": error_code,
                    "created_at": current,
                    "updated_at": current,
                },
            },
        )
        row = _row(result)
        if row and (row.get("request_conflict") or not _operation_matches(
            row,
            source_id=source_id,
            request_id=request_id,
            source_updated_at=source_updated_at,
            content_sha256=content_sha256,
            operation=operation,
            command_id=command_id,
            outcome=outcome,
            error_code=error_code,
        )):
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
            command_id=command_id,
            outcome=outcome,
            error_code=error_code,
            now=current,
            fallback=fallback,
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
        result = await _transaction(
            """
            SELECT * FROM source_visual_cache
            WHERE source_id IN $source_records
              AND source_updated_at IN $source_revisions
              AND source_id.updated IN $source_revisions;
            """,
            {
                "source_records": [_source_record(source_id) for source_id in normalised],
                "source_revisions": normalised,
            },
        )
        current: dict[str, SourceVisualRecord] = {}
        for raw_row in _rows(result):
            try:
                record = _record_from_row(raw_row)
            except SourceVisualRepositoryError:
                continue
            expected = normalised.get(record.source_id)
            if expected is None or record.source_updated_at != expected:
                continue
            current[record.source_id] = record
        return current

    async def publish_ready(
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
        source_id, content_sha256, extractor_version, authority = _identity(
            source_id, content_sha256, extractor_version, authority
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
        )
        result = await _transaction(
            """
            BEGIN TRANSACTION;
            LET $source_row = (SELECT updated FROM $source_record)[0];
            LET $claim = (SELECT * FROM $claim_record)[0];
            IF $source_row.updated != $source_updated_at THEN
                RETURN { source_stale: true };
            ELSE IF $claim = NONE OR $claim.owner_token != $owner_token THEN
                RETURN { owner_mismatch: true, existing: $claim };
            END;
            UPSERT $cache_record CONTENT $record_data;
            SELECT * FROM $cache_record;
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
                "record_data": ready.model_dump(),
            },
        )
        row = _row(result)
        if row and row.get("source_stale"):
            raise SourceVisualConflictError("SOURCE_STALE")
        if row and (row.get("owner_mismatch") or row.get("owner_token") not in {None, owner_token}):
            raise SourceVisualConflictError("OWNER_MISMATCH")
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
        source_id, content_sha256, extractor_version, authority = _identity(
            source_id, content_sha256, extractor_version, authority
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
        )
        result = await _transaction(
            """
            BEGIN TRANSACTION;
            LET $source_row = (SELECT updated FROM $source_record)[0];
            LET $claim = (SELECT * FROM $claim_record)[0];
            IF $source_row.updated != $source_updated_at THEN
                RETURN { source_stale: true };
            ELSE IF $claim = NONE OR $claim.owner_token != $owner_token THEN
                RETURN { owner_mismatch: true, existing: $claim };
            END;
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
            },
        )
        row = _row(result)
        if row and row.get("source_stale"):
            raise SourceVisualConflictError("SOURCE_STALE")
        if row and (row.get("owner_mismatch") or row.get("owner_token") not in {None, owner_token}):
            raise SourceVisualConflictError("OWNER_MISMATCH")
        return ready

    @staticmethod
    def _normalise_record_argument(
        record: SourceVisualRecord | Mapping[str, Any] | str | None,
        source_id: str | SourceVisualAuthority | None,
    ) -> tuple[SourceVisualRecord | Mapping[str, Any] | None, str | SourceVisualAuthority | None]:
        if isinstance(record, str) and source_id is None:
            return None, record
        return record if record is not None else None, source_id

    @staticmethod
    def _ready_record(
        record: SourceVisualRecord | Mapping[str, Any] | None,
        *,
        source_id: str,
        content_sha256: str,
        extractor_version: str,
        source_updated_at: datetime,
        now: datetime,
    ) -> SourceVisualRecord:
        if isinstance(record, SourceVisualRecord):
            if record.source_id != source_id or record.content_sha256 != content_sha256:
                raise SourceVisualRepositoryError("INVALID_INPUT")
            return record
        if isinstance(record, Mapping):
            try:
                parsed = SourceVisualRecord.model_validate(dict(record))
            except Exception as exc:
                raise SourceVisualRepositoryError("MALFORMED_ROW") from exc
            if parsed.source_id != source_id or parsed.content_sha256 != content_sha256:
                raise SourceVisualRepositoryError("INVALID_INPUT")
            return parsed
        return SourceVisualRecord(
            source_id=source_id,
            source_updated_at=source_updated_at,
            source_file_sha256=None,
            content_sha256=content_sha256,
            asset_sha256=content_sha256,
            asset_relpath=f"{content_sha256[:2]}/{content_sha256}/" + f"{content_sha256}.webp",
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
