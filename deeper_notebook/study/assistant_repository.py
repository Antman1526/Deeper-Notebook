"""Bounded, projection-only SurrealDB persistence for Study assistants.

This repository stores durable receipts and plan-local memory, not prompts,
hidden reasoning, credentials, or provider payloads.  Every caller value is a
query parameter; only the fixed projection strings below are part of SQL.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from surrealdb import RecordID  # type: ignore[import-untyped]

from deeper_notebook.database.repository import ensure_record_id, repo_query

from .assistants import (
    StudyAssistantHandoff,
    StudyAssistantInvocation,
    StudyAssistantResponse,
    StudyAssistantSession,
    StudyAuthority,
    StudyCitation,
    StudyPlanMemory,
    StudyProgressReceipt,
    StudySessionStatus,
    prompt_sha256,
)

MIGRATION_PATH = Path(__file__).resolve().parents[1] / "database" / "migrations" / "43.surrealql"
MIGRATION_DOWN_PATH = MIGRATION_PATH.with_name("43_down.surrealql")

_MAX_PAGE_SIZE = 500
_MAX_HANDOFF_PAGE = 50
_MAX_MEMORY_PAGE = 100
_MAX_PROGRESS_PAGE = 100
_MAX_PAGE_OFFSET = 100_000


class StudyAssistantRepositoryError(RuntimeError):
    """Safe persistence failure suitable for an API boundary."""


class StudyAssistantNotFoundError(StudyAssistantRepositoryError):
    """The requested plan-owned record does not exist or is not accessible."""


class StudyAssistantConflictError(StudyAssistantRepositoryError):
    """Optimistic or idempotency guard rejected a mutation."""


class StudyAssistantUnavailableError(StudyAssistantRepositoryError):
    """The assistant persistence authority is unavailable."""


_SESSION_FIELDS = (
    "id",
    "schema_version",
    "plan_id",
    "role",
    "authority",
    "request_id",
    "prompt_sha256",
    "selected_source_ids",
    "status",
    "response_id",
    "error_code",
    "revision",
    "created_at",
    "updated_at",
    "completed_at",
)
_HANDOFF_FIELDS = (
    "id",
    "schema_version",
    "plan_id",
    "session_id",
    "role",
    "request_id",
    "observation",
    "evidence",
    "proposed_action",
    "origin",
    "user_decision",
    "created_at",
    "decided_at",
)
_MEMORY_FIELDS = (
    "id",
    "schema_version",
    "plan_id",
    "memory_key",
    "value",
    "provenance",
    "status",
    "confirmation_required",
    "confirmed_at",
    "created_at",
    "updated_at",
    "revision",
)
_PROGRESS_FIELDS = (
    "id",
    "schema_version",
    "request_id",
    "plan_id",
    "unit_id",
    "event",
    "details",
    "created_at",
)
_SESSION_PROJECTION = ", ".join(_SESSION_FIELDS)
_HANDOFF_PROJECTION = ", ".join(_HANDOFF_FIELDS)
_MEMORY_PROJECTION = ", ".join(_MEMORY_FIELDS)
_PROGRESS_PROJECTION = ", ".join(_PROGRESS_FIELDS)
_CONFLICT_MARKERS = frozenset(
    {
        "study_assistant_session_guard_failed",
        "study_assistant_handoff_guard_failed",
        "study_plan_memory_guard_failed",
        "study_progress_guard_failed",
    }
)


def _flatten(value: object) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if "result" in value and len(value) <= 3:
            return _flatten(value["result"])
        return [value]
    if isinstance(value, (list, tuple)):
        rows: list[dict[str, Any]] = []
        for item in value:
            rows.extend(_flatten(item))
        return rows
    return []


def _one(value: object, *, kind: str) -> dict[str, Any]:
    rows = _flatten(value)
    if len(rows) != 1:
        raise StudyAssistantRepositoryError(f"invalid persisted {kind} record")
    row = rows[0]
    if not isinstance(row, dict) or "id" not in row:
        raise StudyAssistantRepositoryError(f"invalid persisted {kind} record")
    return row


def _one_or_none(value: object, *, kind: str) -> dict[str, Any] | None:
    rows = _flatten(value)
    if not rows:
        return None
    return _one(rows, kind=kind)


def _table_record(value: str | RecordID, table: str) -> RecordID:
    try:
        record = ensure_record_id(value)
    except Exception as exc:
        raise StudyAssistantNotFoundError(f"invalid {table.replace('_', ' ')} ID") from exc
    if getattr(record, "table_name", None) != table:
        raise StudyAssistantNotFoundError(f"invalid {table.replace('_', ' ')} ID")
    token = getattr(record, "id", None)
    if not isinstance(token, str) or not token.strip() or len(str(record)) > 512:
        raise StudyAssistantNotFoundError(f"invalid {table.replace('_', ' ')} ID")
    return record


def _record_value(value: str | RecordID, record: RecordID) -> str:
    """Return the caller's stable string ID for string-owned table fields."""
    if isinstance(value, str):
        return value
    token = getattr(record, "id", None)
    if not isinstance(token, str) or not token.strip():
        raise StudyAssistantNotFoundError("invalid record ID")
    return f"{record.table_name}:{token}"


def _page(limit: int, offset: int, *, cap: int = _MAX_PAGE_SIZE) -> tuple[int, int]:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise StudyAssistantRepositoryError("invalid pagination")
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise StudyAssistantRepositoryError("invalid pagination")
    return min(max(limit, 1), cap), min(max(offset, 0), _MAX_PAGE_OFFSET)


def _revision(value: int, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < (0 if allow_zero else 1):
        raise StudyAssistantRepositoryError("invalid expected revision")
    return value


def _safe_datetime(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise StudyAssistantRepositoryError(f"invalid persisted {field_name}") from exc
    else:
        raise StudyAssistantRepositoryError(f"invalid persisted {field_name}")
    if result.tzinfo is None or result.utcoffset() is None:
        raise StudyAssistantRepositoryError(f"invalid persisted {field_name}")
    return result


def _safe_optional_datetime(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _safe_datetime(value, field_name)


def _safe_optional_text(value: object, field_name: str, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise StudyAssistantRepositoryError(f"invalid persisted {field_name}")
    return value


def _stable_token(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:40]


def _conflict(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if str(current).strip() in _CONFLICT_MARKERS:
            return True
        current = current.__cause__ or current.__context__
    return False


def _citation(value: object) -> StudyCitation:
    if not isinstance(value, Mapping):
        raise StudyAssistantRepositoryError("invalid persisted citation")
    safe = {field: value.get(field) for field in StudyCitation.model_fields if field in value}
    try:
        return StudyCitation.model_validate(safe)
    except Exception as exc:
        raise StudyAssistantRepositoryError("invalid persisted citation") from exc


def _session_from(value: object) -> StudyAssistantSession:
    row = _one(value, kind="assistant session")
    raw_id = row.get("id")
    if isinstance(raw_id, RecordID):
        raw_id = str(raw_id)
    if not isinstance(raw_id, str):
        raise StudyAssistantRepositoryError("invalid persisted assistant session")
    values = {
        "session_id": raw_id,
        "plan_id": str(row.get("plan_id", "")),
        "role": row.get("role"),
        "authority": row.get("authority"),
        "request_id": row.get("request_id"),
        "prompt_sha256": row.get("prompt_sha256"),
        "selected_source_ids": tuple(row.get("selected_source_ids") or ()),
        "status": row.get("status", "queued"),
        "response_id": row.get("response_id"),
        "error_code": row.get("error_code"),
        "revision": row.get("revision", 1),
        "created_at": _safe_datetime(row.get("created_at"), "created_at"),
        "updated_at": _safe_datetime(row.get("updated_at"), "updated_at"),
        "completed_at": _safe_optional_datetime(row.get("completed_at"), "completed_at"),
    }
    try:
        return StudyAssistantSession.model_validate(values)
    except Exception as exc:
        raise StudyAssistantRepositoryError("invalid persisted assistant session") from exc


def _handoff_from(value: object) -> StudyAssistantHandoff:
    row = _one(value, kind="assistant handoff")
    raw_id = row.get("id")
    if isinstance(raw_id, RecordID):
        raw_id = str(raw_id)
    evidence = tuple(_citation(item) for item in (row.get("evidence") or ()))
    values = {
        "handoff_id": raw_id,
        "request_id": row.get("request_id"),
        "plan_id": str(row.get("plan_id", "")),
        "session_id": str(row.get("session_id", "")),
        "role": row.get("role"),
        "observation": row.get("observation"),
        "evidence": evidence,
        "proposed_action": row.get("proposed_action"),
        "origin": row.get("origin"),
        "user_decision": row.get("user_decision", "pending"),
        "created_at": _safe_datetime(row.get("created_at"), "created_at"),
        "decided_at": _safe_optional_datetime(row.get("decided_at"), "decided_at"),
    }
    try:
        return StudyAssistantHandoff.model_validate(values)
    except Exception as exc:
        raise StudyAssistantRepositoryError("invalid persisted assistant handoff") from exc


def _memory_from(value: object) -> StudyPlanMemory:
    row = _one(value, kind="plan memory")
    raw_id = row.get("id")
    if isinstance(raw_id, RecordID):
        raw_id = str(raw_id)
    values = {
        "memory_id": raw_id,
        "plan_id": str(row.get("plan_id", "")),
        "memory_key": row.get("memory_key"),
        "value": row.get("value"),
        "provenance": row.get("provenance"),
        "status": row.get("status"),
        "confirmation_required": row.get("confirmation_required"),
        "confirmed_at": _safe_optional_datetime(row.get("confirmed_at"), "confirmed_at"),
        "created_at": _safe_datetime(row.get("created_at"), "created_at"),
        "updated_at": _safe_datetime(row.get("updated_at"), "updated_at"),
        "revision": row.get("revision", 1),
    }
    try:
        return StudyPlanMemory.model_validate(values)
    except Exception as exc:
        raise StudyAssistantRepositoryError("invalid persisted plan memory") from exc


def _progress_from(value: object) -> StudyProgressReceipt:
    row = _one(value, kind="progress")
    raw_id = row.get("id")
    if isinstance(raw_id, RecordID):
        raw_id = str(raw_id)
    try:
        return StudyProgressReceipt.model_validate(
            {
                "receipt_id": raw_id,
                "request_id": row.get("request_id"),
                "plan_id": str(row.get("plan_id", "")),
                "unit_id": row.get("unit_id"),
                "event": row.get("event"),
                "details": row.get("details"),
                "created_at": _safe_datetime(row.get("created_at"), "created_at"),
            }
        )
    except Exception as exc:
        raise StudyAssistantRepositoryError("invalid persisted progress") from exc


class StudyAssistantRepository:
    """Persist only bounded projections owned by a Study Plan."""

    async def create_session(
        self,
        invocation: StudyAssistantInvocation,
        *,
        request_id: str | None = None,
    ) -> StudyAssistantSession:
        request_id = request_id or invocation.request_id or invocation.invocation_id
        if request_id is None:
            request_id = _stable_token(
                invocation.plan_id, invocation.role, invocation.authority, prompt_sha256(invocation.prompt)
            )
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 256:
            raise StudyAssistantRepositoryError("invalid assistant request ID")
        plan_id = _table_record(invocation.plan_id, "study_plan")
        plan_value = _record_value(invocation.plan_id, plan_id)
        session_id = ensure_record_id(
            f"study_assistant_session:{_stable_token(invocation.plan_id, request_id)}"
        )
        now = invocation.created_at
        payload = {
            "schema_version": 1,
            "plan_id": invocation.plan_id,
            "role": invocation.role,
            "authority": invocation.authority,
            "request_id": request_id,
            "prompt_sha256": prompt_sha256(invocation.prompt),
            "selected_source_ids": list(invocation.selected_source_ids),
            "status": "queued",
            "response_id": None,
            "error_code": None,
            "revision": 1,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }
        try:
            existing = await repo_query(
                    f"SELECT {_SESSION_PROJECTION} FROM study_assistant_session "
                    "WHERE plan_id = $plan_id AND request_id = $request_id LIMIT 1;",
                {"plan_id": plan_value, "request_id": request_id},
            )
            if existing:
                session = _session_from(existing)
                if (
                    session.prompt_sha256 != payload["prompt_sha256"]
                    or session.plan_id != payload["plan_id"]
                    or session.role != payload["role"]
                    or session.authority != payload["authority"]
                    or session.selected_source_ids != tuple(payload["selected_source_ids"])
                ):
                    raise StudyAssistantConflictError("assistant request ID was already used")
                return session
            rows = await repo_query(
                "CREATE $assistant_session CONTENT $payload RETURN AFTER;",
                {
                    "assistant_session": session_id,
                    "plan_id": plan_value,
                    "payload": payload,
                },
            )
            return _session_from(rows)
        except (StudyAssistantRepositoryError, StudyAssistantConflictError):
            raise
        except Exception as exc:
            try:
                replay = await repo_query(
                    f"SELECT {_SESSION_PROJECTION} FROM study_assistant_session "
                    "WHERE plan_id = $plan_id AND request_id = $request_id LIMIT 1;",
                    {"plan_id": plan_value, "request_id": request_id},
                )
                if replay:
                    session = _session_from(replay)
                    if session.prompt_sha256 == payload["prompt_sha256"]:
                        return session
            except Exception:
                pass
            logger.exception("Failed to create assistant session")
            raise StudyAssistantUnavailableError("Study assistant sessions are unavailable") from exc

    async def get_session(self, session_id: str) -> StudyAssistantSession | None:
        record = _table_record(session_id, "study_assistant_session")
        try:
            rows = await repo_query(
                f"SELECT {_SESSION_PROJECTION} FROM $assistant_session LIMIT 1;",
                {"assistant_session": record},
            )
            row = _one_or_none(rows, kind="assistant session")
            return _session_from(row) if row else None
        except StudyAssistantRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to load assistant session")
            raise StudyAssistantUnavailableError("Study assistant sessions are unavailable") from exc

    async def update_session(
        self,
        session_id: str,
        *,
        status: StudySessionStatus,
        expected_revision: int,
        response_id: str | None = None,
        error_code: str | None = None,
        completed_at: datetime | None = None,
    ) -> StudyAssistantSession:
        record = _table_record(session_id, "study_assistant_session")
        expected_revision = _revision(expected_revision)
        now = completed_at or datetime.now(UTC)
        if now.tzinfo is None or now.utcoffset() is None:
            raise StudyAssistantRepositoryError("session timestamp must be timezone-aware")
        patch = {
            "status": status,
            "response_id": response_id,
            "error_code": error_code,
            "completed_at": completed_at,
            "updated_at": now,
            "revision": expected_revision + 1,
        }
        try:
            rows = await repo_query(
                "UPDATE $assistant_session MERGE $patch "
                "WHERE revision = $expected_revision RETURN AFTER;",
                {
                    "assistant_session": record,
                    "patch": patch,
                    "expected_revision": expected_revision,
                },
            )
            row = _one_or_none(rows, kind="assistant session")
            if row is None:
                replay = await repo_query(
                    f"SELECT {_SESSION_PROJECTION} FROM $assistant_session LIMIT 1;",
                    {"assistant_session": record},
                )
                current = _session_from(replay) if replay else None
                if current is not None and (
                    current.revision == expected_revision + 1
                    and current.status == status
                    and current.response_id == response_id
                    and current.error_code == error_code
                    and current.completed_at == completed_at
                ):
                    return current
                raise StudyAssistantConflictError("assistant session revision conflict")
            return _session_from(row)
        except StudyAssistantRepositoryError:
            raise
        except Exception as exc:
            if _conflict(exc):
                raise StudyAssistantConflictError("assistant session revision conflict") from exc
            logger.exception("Failed to update assistant session")
            raise StudyAssistantUnavailableError("Study assistant sessions are unavailable") from exc

    async def append_handoff(
        self,
        handoff: StudyAssistantHandoff,
        *,
        request_id: str | None = None,
    ) -> StudyAssistantHandoff:
        request_id = request_id or handoff.request_id
        if request_id is None:
            request_id = _stable_token(
                handoff.plan_id,
                handoff.session_id,
                handoff.role,
                handoff.observation,
            )
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 256:
            raise StudyAssistantRepositoryError("invalid handoff request ID")
        plan_id = _table_record(handoff.plan_id, "study_plan")
        plan_value = _record_value(handoff.plan_id, plan_id)
        handoff_id = ensure_record_id(
            f"study_assistant_handoff:{_stable_token(handoff.plan_id, request_id)}"
        )
        payload = handoff.model_dump(mode="python", exclude={"handoff_id"})
        payload["request_id"] = request_id
        payload["evidence"] = [item.model_dump(mode="python") for item in handoff.evidence]
        payload["plan_id"] = handoff.plan_id
        try:
            existing = await repo_query(
                f"SELECT {_HANDOFF_PROJECTION} FROM study_assistant_handoff "
                "WHERE plan_id = $plan_id AND request_id = $request_id LIMIT 1;",
                {"plan_id": str(plan_id), "request_id": request_id},
            )
            if existing:
                current = _handoff_from(existing)
                if current.model_dump(exclude={"handoff_id", "request_id"}) != handoff.model_dump(
                    exclude={"handoff_id", "request_id"}
                ):
                    raise StudyAssistantConflictError("handoff request ID was already used")
                return current
            rows = await repo_query(
                "CREATE $assistant_handoff CONTENT $payload RETURN AFTER;",
                {
                    "assistant_handoff": handoff_id,
                    "plan_id": plan_value,
                    "payload": payload,
                },
            )
            return _handoff_from(rows)
        except StudyAssistantRepositoryError:
            raise
        except Exception as exc:
            try:
                replay = await repo_query(
                    f"SELECT {_HANDOFF_PROJECTION} FROM study_assistant_handoff "
                    "WHERE plan_id = $plan_id AND request_id = $request_id LIMIT 1;",
                    {"plan_id": plan_value, "request_id": request_id},
                )
                if replay:
                    return _handoff_from(replay)
            except Exception:
                pass
            logger.exception("Failed to append assistant handoff")
            raise StudyAssistantUnavailableError("Study assistant handoffs are unavailable") from exc

    async def get_handoff(self, handoff_id: str) -> StudyAssistantHandoff | None:
        record = _table_record(handoff_id, "study_assistant_handoff")
        try:
            rows = await repo_query(
                f"SELECT {_HANDOFF_PROJECTION} FROM $assistant_handoff LIMIT 1;",
                {"assistant_handoff": record},
            )
            row = _one_or_none(rows, kind="assistant handoff")
            return _handoff_from(row) if row else None
        except StudyAssistantRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to load assistant handoff")
            raise StudyAssistantUnavailableError("Study assistant handoffs are unavailable") from exc

    async def list_handoffs(
        self,
        plan_id: str,
        *,
        limit: int = _MAX_HANDOFF_PAGE,
        offset: int = 0,
    ) -> tuple[StudyAssistantHandoff, ...]:
        page_limit, page_offset = _page(limit, offset, cap=_MAX_HANDOFF_PAGE)
        plan = _table_record(plan_id, "study_plan")
        plan_value = _record_value(plan_id, plan)
        try:
            rows = await repo_query(
                f"SELECT {_HANDOFF_PROJECTION} FROM study_assistant_handoff "
                "WHERE plan_id = $plan_id ORDER BY created_at DESC LIMIT $limit START $offset;",
                {"plan_id": plan_value, "limit": page_limit, "offset": page_offset},
            )
            return tuple(_handoff_from(row) for row in _flatten(rows))
        except StudyAssistantRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to list assistant handoffs")
            raise StudyAssistantUnavailableError("Study assistant handoffs are unavailable") from exc

    async def upsert_memory(
        self,
        memory: StudyPlanMemory,
        *,
        expected_revision: int,
        request_id: str | None = None,
    ) -> StudyPlanMemory:
        expected_revision = _revision(expected_revision, allow_zero=True)
        plan = _table_record(memory.plan_id, "study_plan")
        plan_value = _record_value(memory.plan_id, plan)
        memory_id = ensure_record_id(
            f"study_plan_memory:{_stable_token(memory.plan_id, memory.memory_key)}"
        )
        payload = memory.model_dump(mode="python", exclude={"memory_id", "revision"})
        payload["plan_id"] = memory.plan_id
        try:
            existing = await repo_query(
                f"SELECT {_MEMORY_PROJECTION} FROM study_plan_memory "
                "WHERE plan_id = $plan_id AND memory_key = $memory_key LIMIT 1;",
                {"plan_id": plan_value, "memory_key": memory.memory_key},
            )
            if existing:
                current = _memory_from(existing)
                if current.revision != expected_revision:
                    if current.model_dump(exclude={"memory_id", "revision"}) == memory.model_dump(
                        exclude={"memory_id", "revision"}
                    ):
                        return current
                    raise StudyAssistantConflictError("plan memory revision conflict")
                payload["revision"] = expected_revision + 1
                payload["updated_at"] = memory.updated_at
                rows = await repo_query(
                    "UPDATE $plan_memory MERGE $payload "
                    "WHERE revision = $expected_revision RETURN AFTER;",
                    {
                        "plan_memory": memory_id,
                        "payload": payload,
                        "updated_at": memory.updated_at,
                        "expected_revision": expected_revision,
                        "request_id": request_id,
                    },
                )
                row = _one_or_none(rows, kind="plan memory")
                if row is None:
                    raise StudyAssistantConflictError("plan memory revision conflict")
                return _memory_from(row)
            if expected_revision not in {0, 1}:
                raise StudyAssistantConflictError("plan memory revision conflict")
            rows = await repo_query(
                "CREATE $plan_memory CONTENT $payload RETURN AFTER;",
                {
                    "plan_memory": memory_id,
                    "payload": payload,
                    "request_id": request_id,
                },
            )
            return _memory_from(rows)
        except StudyAssistantRepositoryError:
            raise
        except Exception as exc:
            if _conflict(exc):
                raise StudyAssistantConflictError("plan memory revision conflict") from exc
            try:
                replay = await repo_query(
                    f"SELECT {_MEMORY_PROJECTION} FROM study_plan_memory "
                    "WHERE plan_id = $plan_id AND memory_key = $memory_key LIMIT 1;",
                    {"plan_id": plan_value, "memory_key": memory.memory_key},
                )
                if replay:
                    return _memory_from(replay)
            except Exception:
                pass
            logger.exception("Failed to upsert plan memory")
            raise StudyAssistantUnavailableError("Study plan memory is unavailable") from exc

    async def get_memory(self, plan_id: str, memory_key: str) -> StudyPlanMemory | None:
        plan = _table_record(plan_id, "study_plan")
        plan_value = _record_value(plan_id, plan)
        if not isinstance(memory_key, str) or not memory_key.strip() or len(memory_key) > 128:
            raise StudyAssistantRepositoryError("invalid memory key")
        try:
            rows = await repo_query(
                f"SELECT {_MEMORY_PROJECTION} FROM study_plan_memory "
                "WHERE plan_id = $plan_id AND memory_key = $memory_key LIMIT 1;",
                {"plan_id": plan_value, "memory_key": memory_key},
            )
            row = _one_or_none(rows, kind="plan memory")
            return _memory_from(row) if row else None
        except StudyAssistantRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to load plan memory")
            raise StudyAssistantUnavailableError("Study plan memory is unavailable") from exc

    async def list_memory(
        self,
        plan_id: str,
        *,
        status: str | None = None,
        limit: int = _MAX_MEMORY_PAGE,
        offset: int = 0,
    ) -> tuple[StudyPlanMemory, ...]:
        page_limit, page_offset = _page(limit, offset, cap=_MAX_MEMORY_PAGE)
        plan = _table_record(plan_id, "study_plan")
        plan_value = _record_value(plan_id, plan)
        if status is not None and (not isinstance(status, str) or not status.strip()):
            raise StudyAssistantRepositoryError("invalid memory status")
        where = " AND status = $status" if status is not None else ""
        params: dict[str, object] = {
            "plan_id": plan_value,
            "limit": page_limit,
            "offset": page_offset,
        }
        if status is not None:
            params["status"] = status
        try:
            rows = await repo_query(
                f"SELECT {_MEMORY_PROJECTION} FROM study_plan_memory WHERE plan_id = $plan_id"
                f"{where} ORDER BY updated_at DESC LIMIT $limit START $offset;",
                params,
            )
            return tuple(_memory_from(row) for row in _flatten(rows))
        except StudyAssistantRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to list plan memory")
            raise StudyAssistantUnavailableError("Study plan memory is unavailable") from exc

    async def confirm_memory(
        self,
        plan_id: str,
        memory_key: str,
        *,
        expected_revision: int,
        confirmed_at: datetime | None = None,
    ) -> StudyPlanMemory:
        current = await self.get_memory(plan_id, memory_key)
        if current is None:
            raise StudyAssistantNotFoundError("plan memory not found")
        if current.revision != expected_revision:
            if current.status == "confirmed":
                return current
            raise StudyAssistantConflictError("plan memory revision conflict")
        return await self.upsert_memory(
            current.confirm(now=confirmed_at),
            expected_revision=current.revision,
            request_id=f"confirm:{memory_key}:{current.revision}",
        )

    async def append_progress(self, receipt: StudyProgressReceipt) -> StudyProgressReceipt:
        plan = _table_record(receipt.plan_id, "study_plan")
        plan_value = _record_value(receipt.plan_id, plan)
        receipt_id = ensure_record_id(
            f"study_progress:{_stable_token(receipt.plan_id, receipt.request_id)}"
        )
        payload = receipt.model_dump(mode="python", exclude={"receipt_id"})
        payload["plan_id"] = receipt.plan_id
        try:
            existing = await repo_query(
                f"SELECT {_PROGRESS_PROJECTION} FROM study_progress "
                "WHERE plan_id = $plan_id AND request_id = $request_id LIMIT 1;",
                {"plan_id": plan_value, "request_id": receipt.request_id},
            )
            if existing:
                current = _progress_from(existing)
                if current.model_dump(exclude={"receipt_id"}) != receipt.model_dump(
                    exclude={"receipt_id"}
                ):
                    raise StudyAssistantConflictError("progress request ID was already used")
                return current
            rows = await repo_query(
                "CREATE $progress_receipt CONTENT $payload RETURN AFTER;",
                {"progress_receipt": receipt_id, "payload": payload},
            )
            return _progress_from(rows)
        except StudyAssistantRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to append study progress")
            raise StudyAssistantUnavailableError("Study progress is unavailable") from exc

    async def list_progress(
        self,
        plan_id: str,
        *,
        limit: int = _MAX_PROGRESS_PAGE,
        offset: int = 0,
    ) -> tuple[StudyProgressReceipt, ...]:
        page_limit, page_offset = _page(limit, offset, cap=_MAX_PROGRESS_PAGE)
        plan = _table_record(plan_id, "study_plan")
        plan_value = _record_value(plan_id, plan)
        try:
            rows = await repo_query(
                f"SELECT {_PROGRESS_PROJECTION} FROM study_progress WHERE plan_id = $plan_id "
                "ORDER BY created_at DESC LIMIT $limit START $offset;",
                {"plan_id": plan_value, "limit": page_limit, "offset": page_offset},
            )
            return tuple(_progress_from(row) for row in _flatten(rows))
        except StudyAssistantRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to list study progress")
            raise StudyAssistantUnavailableError("Study progress is unavailable") from exc


__all__ = [
    "MIGRATION_DOWN_PATH",
    "MIGRATION_PATH",
    "StudyAssistantConflictError",
    "StudyAssistantNotFoundError",
    "StudyAssistantRepository",
    "StudyAssistantRepositoryError",
    "StudyAssistantUnavailableError",
]
