"""Transactional persistence for app-owned overlay Markdown metadata."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from pydantic import ValidationError

from deeper_notebook.database.repository import (
    db_connection,
    ensure_record_id,
    parse_record_ids,
)
from deeper_notebook.overlay.contracts import (
    CreateDailyNote,
    OverlayMutationReceipt,
    OverlayNote,
    OverlayNoteKind,
    OverlayPage,
    OverlaySpace,
)
from deeper_notebook.overlay.paths import validate_relative_path
from deeper_notebook.vault.contracts import ParsedDocument
from deeper_notebook.vault.repository import VaultRepository, _record_id

_HASH = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ERROR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_OVERLAY_NOTE_ID = re.compile(r"^overlay_note:[A-Za-z0-9_-]+$")
_ZERO_HASH = "0" * 64


class _Connection(Protocol):
    async def query(
        self,
        statement: str,
        variables: dict[str, Any] | None = None,
    ) -> Any: ...


ConnectionFactory = Callable[[], AbstractAsyncContextManager[_Connection]]


class OverlayRepositoryError(RuntimeError):
    """A sanitized persistence-boundary failure."""


class OverlayConflictError(OverlayRepositoryError):
    """A stable optimistic-concurrency or reservation conflict."""


@dataclass(frozen=True, slots=True)
class OverlayReservation:
    operation_id: str
    idempotency_key: str
    overlay_note_id: str
    projected_note_id: str
    relative_path: str
    title: str
    kind: OverlayNoteKind
    date_key: str | None
    expected_revision: int | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _db_id(value: str):
    return ensure_record_id(value)


def _overlay_note_db_id(value: str):
    if not isinstance(value, str) or _OVERLAY_NOTE_ID.fullmatch(value) is None:
        raise ValueError("invalid_overlay_note_id")
    return _db_id(value)


def _operation_id(operation: str, idempotency_key: str) -> str:
    return f"overlay-{uuid.uuid5(uuid.NAMESPACE_URL, f'{operation}:{idempotency_key}').hex}"


def _stable_id(note_id: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, note_id).hex.upper()


def _safe_key(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("invalid_idempotency_key")
    return value


def _safe_hash(value: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError("invalid_content_hash")
    return value


def _page_from_mapping(value: Any) -> OverlayPage:
    try:
        return OverlayPage.model_validate(value)
    except ValidationError:
        raise OverlayRepositoryError("overlay_projection_invalid") from None


class OverlayRepository:
    """Reserve overlay identities and atomically commit derived projections."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory | None = None,
        clock: Callable[[], datetime] = _now,
        projection_repository: VaultRepository | None = None,
    ) -> None:
        self._connection_factory = connection_factory or db_connection
        self._clock = clock
        self._projection_repository = projection_repository or VaultRepository(
            connection_factory=self._connection_factory
        )

    async def _query(
        self,
        connection: _Connection,
        statement: str,
        variables: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            result = await connection.query(statement, variables)
        except OverlayRepositoryError:
            raise
        except Exception:
            raise OverlayRepositoryError("overlay_repository_unavailable") from None
        if isinstance(result, str):
            raise OverlayRepositoryError("overlay_repository_unavailable")
        parsed = parse_record_ids(result)
        return parsed if isinstance(parsed, list) else [parsed]

    async def ensure_default_space(self) -> OverlaySpace:
        now = self._clock()
        space_id = "overlay_space:default"
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                UPSERT $space_id MERGE $space RETURN AFTER;
                """,
                {
                    "space_id": _db_id(space_id),
                    "space": {
                        "schema_version": 1,
                        "slug": "default",
                        "display_name": "Deeper Notebook Overlay",
                        "root_version": 1,
                        "created_at": now,
                        "updated_at": now,
                    },
                },
            )
        if not rows:
            raise OverlayRepositoryError("overlay_space_unavailable")
        return OverlaySpace.model_validate(rows[-1])

    async def get_daily(self, date_key: str) -> OverlayNote | None:
        validated_date = CreateDailyNote(date_key=date_key).date_key
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                SELECT * FROM overlay_note
                WHERE space_id = $space_id AND date_key = $date_key
                LIMIT 1;
                """,
                {
                    "space_id": _db_id("overlay_space:default"),
                    "date_key": validated_date,
                },
            )
        return OverlayNote.model_validate(rows[0]) if rows else None

    async def get_note(self, note_id: str) -> OverlayNote:
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "SELECT * FROM $note_id LIMIT 1;",
                {"note_id": _overlay_note_db_id(note_id)},
            )
        if not rows:
            raise LookupError("overlay_not_found")
        try:
            return OverlayNote.model_validate(rows[0])
        except ValidationError:
            raise OverlayRepositoryError("overlay_note_invalid") from None

    async def list_notes(self, limit: int, offset: int) -> list[OverlayNote]:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit <= 0
            or limit > 500
            or isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 0
        ):
            raise ValueError("invalid_pagination")
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                SELECT * FROM overlay_note
                WHERE space_id = $space_id
                ORDER BY updated_at DESC, id
                LIMIT $limit START $offset;
                """,
                {
                    "space_id": _db_id("overlay_space:default"),
                    "limit": limit,
                    "offset": offset,
                },
            )
        return [OverlayNote.model_validate(row) for row in rows]

    async def reserve_create(
        self,
        *,
        operation: Literal["create-daily", "create-unique"],
        idempotency_key: str,
        kind: OverlayNoteKind,
        date_key: str | None,
        relative_path: str,
        title: str,
    ) -> OverlayReservation:
        if (operation, kind) not in {
            ("create-daily", "daily"),
            ("create-unique", "unique"),
        }:
            raise ValueError("overlay_operation_kind_mismatch")
        if (
            not isinstance(title, str)
            or not title.strip()
            or len(title) > 512
            or any(ord(character) < 32 for character in title)
        ):
            raise ValueError("invalid_overlay_title")
        key = _safe_key(idempotency_key)
        relative_path = validate_relative_path(relative_path)
        now = self._clock()
        operation_id = _operation_id(operation, key)
        note_id = _record_id(
            "overlay_note",
            "default",
            kind,
            date_key or key,
        )
        projected_note_id = _record_id("note", note_id)
        receipt_id = _record_id("overlay_mutation_receipt", operation, key)
        try:
            pending_note = OverlayNote(
                id=note_id,
                space_id="overlay_space:default",
                projected_note_id=projected_note_id,
                stable_id=_stable_id(note_id),
                kind=kind,
                date_key=date_key,
                relative_path=relative_path,
                title=title,
                content_hash=_ZERO_HASH,
                revision=1,
                projection_state="pending",
                encoding="utf-8",
                newline="lf",
                created_at=now,
                updated_at=now,
            )
        except ValidationError:
            raise ValueError("invalid_overlay_reservation") from None
        note = {
            "schema_version": 1,
            **pending_note.model_dump(exclude={"id", "source_authority"}),
        }
        note["space_id"] = _db_id(pending_note.space_id)
        note["projected_note_id"] = _db_id(pending_note.projected_note_id)
        receipt = {
            "schema_version": 1,
            "operation_id": operation_id,
            "idempotency_key": key,
            "overlay_note_id": _db_id(note_id),
            "operation": operation,
            "expected_revision": None,
            "resulting_revision": None,
            "before_hash": None,
            "after_hash": None,
            "status": "started",
            "error_code": None,
            "started_at": now,
            "completed_at": None,
        }
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                self._reserve_create_transaction(),
                {
                    "space_id": _db_id("overlay_space:default"),
                    "space": {
                        "schema_version": 1,
                        "slug": "default",
                        "display_name": "Deeper Notebook Overlay",
                        "root_version": 1,
                        "created_at": now,
                        "updated_at": now,
                    },
                    "note_id": _db_id(note_id),
                    "projected_note_id": _db_id(projected_note_id),
                    "receipt_id": _db_id(receipt_id),
                    "operation": operation,
                    "idempotency_key": key,
                    "kind": kind,
                    "date_key": date_key,
                    "relative_path": relative_path,
                    "note": note,
                    "receipt": receipt,
                },
            )
        outcome = self._outcome(rows)
        status = outcome.get("outcome")
        if status == "path-conflict":
            raise OverlayConflictError("overlay_path_conflict")
        if status == "idempotency-conflict":
            raise OverlayConflictError("overlay_idempotency_conflict")
        if status not in {"reserved", "replay", "daily-winner"}:
            raise OverlayRepositoryError("overlay_reservation_outcome_missing")
        return self._reservation(outcome)

    @staticmethod
    def _reserve_create_transaction() -> str:
        return """
        BEGIN TRANSACTION;
        UPSERT $space_id MERGE $space;
        LET $existing_receipt = (
            SELECT * FROM overlay_mutation_receipt
            WHERE operation = $operation
            AND idempotency_key = $idempotency_key
            LIMIT 1
        )[0];
        LET $daily_winner = IF $kind = 'daily' {
            (
                SELECT * FROM overlay_note
                WHERE space_id = $space_id
                AND date_key = $date_key
                LIMIT 1
            )[0]
        } ELSE {
            NONE
        };
        LET $path_winner = (
            SELECT * FROM overlay_note
            WHERE space_id = $space_id
            AND relative_path = $relative_path
            LIMIT 1
        )[0];
        LET $receipt_note = IF $existing_receipt != NONE {
            (SELECT * FROM $existing_receipt.overlay_note_id LIMIT 1)[0]
        } ELSE {
            NONE
        };
        LET $winner = IF $receipt_note != NONE {
            $receipt_note
        } ELSE {
            $daily_winner
        };
        LET $winner_receipt = IF $existing_receipt != NONE {
            $existing_receipt
        } ELSE {
            (
                SELECT * FROM overlay_mutation_receipt
                WHERE overlay_note_id = $winner.id
                AND operation = 'create-daily'
                ORDER BY started_at
                LIMIT 1
            )[0]
        };
        LET $idempotency_conflict = (
            $existing_receipt != NONE
            AND (
                $receipt_note.kind != $kind
                OR $receipt_note.date_key != $date_key
            )
        );
        LET $path_conflict = (
            $existing_receipt = NONE
            AND $daily_winner = NONE
            AND $path_winner != NONE
        );
        LET $can_reserve = (
            $existing_receipt = NONE
            AND $daily_winner = NONE
            AND !$path_conflict
        );
        IF $can_reserve {
            CREATE $note_id CONTENT $note;
            CREATE $receipt_id CONTENT $receipt;
        };
        LET $reserved_note = IF $can_reserve {
            (SELECT * FROM $note_id LIMIT 1)[0]
        } ELSE {
            $winner
        };
        LET $reserved_receipt = IF $can_reserve {
            (SELECT * FROM $receipt_id LIMIT 1)[0]
        } ELSE {
            $winner_receipt
        };
        LET $outcome = IF $idempotency_conflict {
            'idempotency-conflict'
        } ELSE {
            IF $path_conflict {
                'path-conflict'
            } ELSE {
                IF $can_reserve {
                    'reserved'
                } ELSE {
                    IF $existing_receipt != NONE {
                        'replay'
                    } ELSE {
                        'daily-winner'
                    }
                }
            }
        };
        RETURN {
            outcome: $outcome,
            note: $reserved_note,
            receipt: $reserved_receipt
        };
        COMMIT TRANSACTION;
        """

    async def reserve_update(
        self,
        *,
        note_id: str,
        expected_revision: int,
        idempotency_key: str,
    ) -> OverlayReservation:
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise ValueError("invalid_expected_revision")
        key = _safe_key(idempotency_key)
        note_db_id = _overlay_note_db_id(note_id)
        now = self._clock()
        operation = "update"
        operation_id = _operation_id(operation, key)
        receipt_id = _record_id("overlay_mutation_receipt", operation, key)
        receipt = {
            "schema_version": 1,
            "operation_id": operation_id,
            "idempotency_key": key,
            "overlay_note_id": note_db_id,
            "operation": operation,
            "expected_revision": expected_revision,
            "resulting_revision": None,
            "before_hash": None,
            "after_hash": None,
            "status": "started",
            "error_code": None,
            "started_at": now,
            "completed_at": None,
        }
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                self._reserve_update_transaction(),
                {
                    "note_id": note_db_id,
                    "receipt_id": _db_id(receipt_id),
                    "idempotency_key": key,
                    "expected_revision": expected_revision,
                    "receipt": receipt,
                },
            )
        outcome = self._outcome(rows)
        status = outcome.get("outcome")
        if status == "not-found":
            raise LookupError("overlay_not_found")
        if status == "idempotency-conflict":
            raise OverlayConflictError("overlay_idempotency_conflict")
        if status == "revision-conflict":
            raise OverlayConflictError("overlay_revision_conflict")
        if status not in {"reserved", "replay"}:
            raise OverlayRepositoryError("overlay_reservation_outcome_missing")
        return self._reservation(outcome)

    async def prepare_revision(
        self,
        *,
        reservation: OverlayReservation,
        content_hash: str,
    ) -> None:
        """Durably bind a started receipt to the exact bytes to be published."""
        if not isinstance(reservation, OverlayReservation):
            raise ValueError("invalid_overlay_reservation")
        content_hash = _safe_hash(content_hash)
        receipt_id = _record_id(
            "overlay_mutation_receipt",
            "update"
            if reservation.expected_revision is not None
            else ("create-daily" if reservation.kind == "daily" else "create-unique"),
            reservation.idempotency_key,
        )
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                BEGIN TRANSACTION;
                LET $receipt = (SELECT * FROM $receipt_id LIMIT 1)[0];
                LET $identity_valid = (
                    $receipt != NONE
                    AND $receipt.operation_id = $operation_id
                    AND $receipt.overlay_note_id = $overlay_note_id
                    AND $receipt.status IN ['started', 'failed']
                );
                LET $hash_valid = (
                    $receipt.after_hash = NONE
                    OR $receipt.after_hash = $content_hash
                );
                IF $identity_valid AND $hash_valid {
                    UPDATE $receipt_id SET
                        after_hash = $content_hash,
                        status = 'started',
                        error_code = NONE,
                        completed_at = NONE;
                };
                RETURN {
                    outcome: IF !$identity_valid {
                        'conflict'
                    } ELSE {
                        IF $hash_valid {
                            'prepared'
                        } ELSE {
                            'hash-conflict'
                        }
                    }
                };
                COMMIT TRANSACTION;
                """,
                {
                    "receipt_id": _db_id(receipt_id),
                    "operation_id": reservation.operation_id,
                    "overlay_note_id": _overlay_note_db_id(reservation.overlay_note_id),
                    "content_hash": content_hash,
                },
            )
        outcome = self._outcome(rows).get("outcome")
        if outcome == "hash-conflict":
            raise OverlayConflictError("overlay_hash_conflict")
        if outcome != "prepared":
            raise OverlayConflictError("overlay_revision_conflict")

    async def reassign_unique_path(
        self,
        *,
        reservation: OverlayReservation,
        relative_path: str,
    ) -> OverlayReservation:
        """Move an unpublished unique reservation off a disk-only collision."""
        if (
            not isinstance(reservation, OverlayReservation)
            or reservation.kind != "unique"
            or reservation.expected_revision is not None
        ):
            raise ValueError("invalid_overlay_reservation")
        relative_path = validate_relative_path(relative_path)
        receipt_id = _record_id(
            "overlay_mutation_receipt",
            "create-unique",
            reservation.idempotency_key,
        )
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                BEGIN TRANSACTION;
                LET $receipt = (SELECT * FROM $receipt_id LIMIT 1)[0];
                LET $note = (SELECT * FROM $overlay_note_id LIMIT 1)[0];
                LET $revision = (
                    SELECT * FROM overlay_revision
                    WHERE overlay_note_id = $overlay_note_id
                    LIMIT 1
                )[0];
                LET $path_winner = (
                    SELECT * FROM overlay_note
                    WHERE space_id = $space_id
                    AND relative_path = $relative_path
                    LIMIT 1
                )[0];
                LET $valid = (
                    $receipt != NONE
                    AND $receipt.operation_id = $operation_id
                    AND $receipt.overlay_note_id = $overlay_note_id
                    AND $receipt.operation = 'create-unique'
                    AND $receipt.status IN ['started', 'failed', 'conflict']
                    AND $note != NONE
                    AND $note.space_id = $space_id
                    AND $note.kind = 'unique'
                    AND $note.content_hash = $zero_hash
                    AND $revision = NONE
                );
                IF $valid AND $path_winner = NONE {
                    UPDATE $overlay_note_id SET
                        relative_path = $relative_path,
                        projection_state = 'pending';
                    UPDATE $receipt_id SET
                        after_hash = NONE,
                        status = 'started',
                        error_code = NONE,
                        completed_at = NONE;
                };
                RETURN {
                    outcome: IF !$valid {
                        'conflict'
                    } ELSE {
                        IF $path_winner != NONE {
                            'path-conflict'
                        } ELSE {
                            'reassigned'
                        }
                    },
                    note: (SELECT * FROM $overlay_note_id LIMIT 1)[0],
                    receipt: (SELECT * FROM $receipt_id LIMIT 1)[0]
                };
                COMMIT TRANSACTION;
                """,
                {
                    "receipt_id": _db_id(receipt_id),
                    "operation_id": reservation.operation_id,
                    "overlay_note_id": _overlay_note_db_id(reservation.overlay_note_id),
                    "space_id": _db_id("overlay_space:default"),
                    "relative_path": relative_path,
                    "zero_hash": _ZERO_HASH,
                },
            )
        outcome = self._outcome(rows)
        if outcome.get("outcome") == "path-conflict":
            raise OverlayConflictError("overlay_path_conflict")
        if outcome.get("outcome") != "reassigned":
            raise OverlayConflictError("overlay_revision_conflict")
        return self._reservation(outcome)

    @staticmethod
    def _reserve_update_transaction() -> str:
        return """
        BEGIN TRANSACTION;
        LET $note = (SELECT * FROM $note_id LIMIT 1)[0];
        LET $latest_revision = (
            SELECT * FROM overlay_revision
            WHERE overlay_note_id = $note_id
            ORDER BY revision DESC
            LIMIT 1
        )[0];
        LET $existing_receipt = (
            SELECT * FROM overlay_mutation_receipt
            WHERE operation = 'update'
            AND idempotency_key = $idempotency_key
            LIMIT 1
        )[0];
        LET $idempotency_conflict = (
            $existing_receipt != NONE
            AND (
                $existing_receipt.overlay_note_id != $note_id
                OR $existing_receipt.expected_revision != $expected_revision
            )
        );
        LET $valid_revision = (
            $note != NONE
            AND $note.revision = $expected_revision
            AND $latest_revision.revision = $note.revision
            AND $latest_revision.content_hash = $note.content_hash
        );
        LET $can_reserve = (
            $existing_receipt = NONE
            AND !$idempotency_conflict
            AND $valid_revision
        );
        IF $can_reserve {
            CREATE $receipt_id CONTENT $receipt;
            UPDATE $receipt_id SET before_hash = $note.content_hash;
        };
        LET $reserved_receipt = IF $can_reserve {
            (SELECT * FROM $receipt_id LIMIT 1)[0]
        } ELSE {
            $existing_receipt
        };
        LET $outcome = IF $note = NONE {
            'not-found'
        } ELSE {
            IF $idempotency_conflict {
                'idempotency-conflict'
            } ELSE {
                IF $existing_receipt != NONE {
                    'replay'
                } ELSE {
                    IF $valid_revision {
                        'reserved'
                    } ELSE {
                        'revision-conflict'
                    }
                }
            }
        };
        RETURN {
            outcome: $outcome,
            note: $note,
            receipt: $reserved_receipt
        };
        COMMIT TRANSACTION;
        """

    async def commit_revision(
        self,
        *,
        reservation: OverlayReservation,
        content_hash: str,
        byte_size: int,
        relative_snapshot: str | None,
        parsed: ParsedDocument,
    ) -> OverlayNote:
        if not isinstance(reservation, OverlayReservation):
            raise ValueError("invalid_overlay_reservation")
        overlay_note_db_id = _overlay_note_db_id(reservation.overlay_note_id)
        content_hash = _safe_hash(content_hash)
        if (
            isinstance(byte_size, bool)
            or not isinstance(byte_size, int)
            or byte_size < 0
        ):
            raise ValueError("invalid_byte_size")
        if (
            parsed.relative_path != reservation.relative_path
            or parsed.content_hash != content_hash
        ):
            raise ValueError("overlay_projection_input_mismatch")
        if parsed.title != reservation.title:
            raise ValueError("overlay_projection_title_mismatch")
        if relative_snapshot is None:
            raise ValueError("overlay_snapshot_required")
        relative_snapshot = validate_relative_path(relative_snapshot)
        if not relative_snapshot.startswith("revisions/"):
            raise ValueError("overlay_snapshot_required")
        target_revision = (
            1
            if reservation.expected_revision is None
            else reservation.expected_revision + 1
        )
        projection = self._projection_repository.owned_projection_unit_of_work(
            source_authority="overlay",
            overlay_space_id="overlay_space:default",
            overlay_note_id=reservation.overlay_note_id,
            projected_note_id=reservation.projected_note_id,
            parsed=parsed,
            revision=target_revision,
        )
        now = self._clock()
        receipt_id = _record_id(
            "overlay_mutation_receipt",
            "update"
            if reservation.expected_revision is not None
            else ("create-daily" if reservation.kind == "daily" else "create-unique"),
            reservation.idempotency_key,
        )
        revision_id = _record_id(
            "overlay_revision",
            reservation.overlay_note_id,
            str(target_revision),
        )
        overlay_note = {
            "title": reservation.title,
            "content_hash": content_hash,
            "revision": target_revision,
            "projection_state": "current",
            "encoding": "utf-8",
            "newline": "lf",
            "updated_at": now,
        }
        revision = {
            "schema_version": 1,
            "overlay_note_id": overlay_note_db_id,
            "revision": target_revision,
            "relative_snapshot": relative_snapshot,
            "content_hash": content_hash,
            "byte_size": byte_size,
            "created_at": now,
        }
        success_receipt = {
            "resulting_revision": target_revision,
            "after_hash": content_hash,
            "status": "success",
            "error_code": None,
            "completed_at": now,
        }
        variables = {
            **projection.variables,
            "receipt_id": _db_id(receipt_id),
            "operation_id": reservation.operation_id,
            "expected_revision": reservation.expected_revision,
            "content_hash": content_hash,
            "target_revision": target_revision,
            "overlay_note": overlay_note,
            "revision_id": _db_id(revision_id),
            "revision": revision,
            "success_receipt": success_receipt,
        }
        statement = self._commit_transaction(projection.mutation_statement)
        async with self._connection_factory() as connection:
            rows = await self._query(connection, statement, variables)
        outcome = self._outcome(rows)
        status = outcome.get("outcome")
        if status == "conflict":
            raise OverlayConflictError("overlay_revision_conflict")
        if status not in {"committed", "replay"}:
            raise OverlayRepositoryError("overlay_commit_outcome_missing")
        try:
            note = OverlayNote.model_validate(outcome.get("note"))
        except ValidationError:
            raise OverlayRepositoryError("overlay_note_invalid") from None
        return note

    def _commit_transaction(self, projection_mutation: str) -> str:
        return (
            """
            BEGIN TRANSACTION;
            LET $receipt = (SELECT * FROM $receipt_id LIMIT 1)[0];
            LET $current_note = (
                SELECT * FROM $overlay_note_id LIMIT 1
            )[0];
            LET $latest_revision = (
                SELECT * FROM overlay_revision
                WHERE overlay_note_id = $overlay_note_id
                ORDER BY revision DESC
                LIMIT 1
            )[0];
            LET $prior_projected_note = (
                SELECT * FROM $projected_note_id LIMIT 1
            )[0];
            LET $replay = (
                $receipt.status = 'success'
                AND $receipt.operation_id = $operation_id
                AND $receipt.resulting_revision = $target_revision
                AND $receipt.after_hash = $content_hash
            );
            LET $create_valid = (
                $expected_revision = NONE
                AND $current_note.revision = 1
                AND (
                    $latest_revision = NONE
                    OR (
                        $latest_revision.revision = 1
                        AND $latest_revision.content_hash = $content_hash
                    )
                )
            );
            LET $update_valid = (
                $expected_revision != NONE
                AND $current_note.revision = $expected_revision
                AND $current_note.content_hash = $receipt.before_hash
                AND $latest_revision.revision = $expected_revision
                AND $latest_revision.content_hash = $current_note.content_hash
            );
            LET $projection_valid = (
                $prior_projected_note = NONE
                OR (
                    $prior_projected_note.source_authority = 'overlay'
                    AND $prior_projected_note.overlay_space_id = $overlay_space_id
                    AND $prior_projected_note.overlay_note_id = $overlay_note_id
                )
            );
            LET $valid = (
                $receipt != NONE
                AND $receipt.operation_id = $operation_id
                AND $receipt.overlay_note_id = $overlay_note_id
                AND $receipt.status IN ['started', 'failed']
                AND $receipt.after_hash = $content_hash
                AND $projection_valid
                AND ($create_valid OR $update_valid)
            );
            IF $valid {
            """
            + projection_mutation
            + """
                UPSERT $overlay_note_id MERGE $overlay_note;
                CREATE $revision_id CONTENT $revision;
                UPDATE $receipt_id MERGE $success_receipt;
            };
            LET $outcome = IF $replay {
                'replay'
            } ELSE {
                IF $valid {
                    'committed'
                } ELSE {
                    'conflict'
                }
            };
            RETURN {
                outcome: $outcome,
                note: (SELECT * FROM $overlay_note_id LIMIT 1)[0]
            };
            COMMIT TRANSACTION;
            """
        )

    async def record_failure(
        self,
        *,
        reservation: OverlayReservation,
        error_code: str,
    ) -> None:
        if not isinstance(reservation, OverlayReservation):
            raise ValueError("invalid_overlay_reservation")
        if not isinstance(error_code, str) or _SAFE_ERROR.fullmatch(error_code) is None:
            error_code = "overlay_error"
        receipt_id = _record_id(
            "overlay_mutation_receipt",
            "update"
            if reservation.expected_revision is not None
            else ("create-daily" if reservation.kind == "daily" else "create-unique"),
            reservation.idempotency_key,
        )
        conflict = error_code in {
            "overlay_revision_conflict",
            "overlay_hash_conflict",
            "overlay_identity_conflict",
            "overlay_file_changed",
        }
        failure_status = "conflict" if conflict else "failed"
        if conflict:
            projection_state: str | None = "conflict"
        elif error_code in {
            "overlay_projection_pending",
            "overlay_parser_failed",
            "overlay_repository_unavailable",
        }:
            projection_state = "pending"
        elif reservation.expected_revision is None:
            projection_state = "failed"
        else:
            projection_state = None
        async with self._connection_factory() as connection:
            await self._query(
                connection,
                """
                BEGIN TRANSACTION;
                LET $receipt = (SELECT * FROM $receipt_id LIMIT 1)[0];
                IF $receipt != NONE AND $receipt.status != 'success' {
                    UPDATE $receipt_id SET
                        status = $failure_status,
                        error_code = $error_code,
                        completed_at = $completed_at;
                    IF $projection_state != NONE {
                        UPDATE $overlay_note_id SET
                            projection_state = $projection_state;
                    };
                };
                COMMIT TRANSACTION;
                """,
                {
                    "receipt_id": _db_id(receipt_id),
                    "overlay_note_id": _overlay_note_db_id(reservation.overlay_note_id),
                    "error_code": error_code,
                    "failure_status": failure_status,
                    "projection_state": projection_state,
                    "completed_at": self._clock(),
                },
            )

    async def get_receipt(
        self,
        reservation: OverlayReservation,
    ) -> OverlayMutationReceipt | None:
        if not isinstance(reservation, OverlayReservation):
            raise ValueError("invalid_overlay_reservation")
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                SELECT * FROM overlay_mutation_receipt
                WHERE operation_id = $operation_id
                LIMIT 1;
                """,
                {"operation_id": reservation.operation_id},
            )
        return OverlayMutationReceipt.model_validate(rows[0]) if rows else None

    async def get_replay(
        self,
        reservation: OverlayReservation,
    ) -> OverlayPage | None:
        receipt = await self.get_receipt(reservation)
        if receipt is None or receipt.status not in {"success", "unchanged"}:
            return None
        return await self.get_page(reservation.overlay_note_id)

    async def get_page(self, note_id: str) -> OverlayPage:
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                self._page_query(),
                {
                    "overlay_note_id": _overlay_note_db_id(note_id),
                    "overlay_space_id": _db_id("overlay_space:default"),
                },
            )
        if not rows:
            raise LookupError("overlay_not_found")
        outcome = rows[-1]
        page = outcome.get("page", outcome)
        if not page or not page.get("overlay") or not page.get("note"):
            raise LookupError("overlay_not_found")
        return _page_from_mapping(page)

    @staticmethod
    def _page_query() -> str:
        return """
        LET $overlay = (
            SELECT
                id,
                space_id,
                projected_note_id,
                stable_id,
                kind,
                date_key,
                relative_path,
                title,
                content_hash,
                revision,
                projection_state,
                encoding,
                newline,
                created_at,
                updated_at
            FROM $overlay_note_id
            WHERE space_id = $overlay_space_id
            LIMIT 1
        )[0];
        LET $projected_note_id = $overlay.projected_note_id;
        RETURN {
            page: {
                overlay: $overlay,
                note: (
                    SELECT * FROM note
                    WHERE overlay_note_id = $overlay_note_id
                    AND overlay_space_id = $overlay_space_id
                    AND source_authority = 'overlay'
                    LIMIT 1
                )[0],
                blocks: (
                    SELECT * FROM note_block
                    WHERE overlay_note_id = $overlay_note_id
                    ORDER BY position
                ),
                tasks: (
                    SELECT * FROM knowledge_task
                    WHERE note_id = $projected_note_id
                ),
                outgoing_links: (
                    SELECT *,
                        source_note_id.title AS source_note_title,
                        source_note_id.overlay_note_id
                            AS source_overlay_note_id,
                        source_note_id.overlay_note_id.relative_path
                            AS source_relative_path,
                        target_note_id.title AS target_note_title,
                        target_note_id.overlay_note_id
                            AS target_overlay_note_id,
                        target_note_id.overlay_note_id.relative_path
                            AS target_relative_path
                    FROM note_link
                    WHERE source_note_id = $projected_note_id
                ),
                backlinks: (
                    SELECT *,
                        source_note_id.title AS source_note_title,
                        source_note_id.overlay_note_id
                            AS source_overlay_note_id,
                        source_note_id.overlay_note_id.relative_path
                            AS source_relative_path,
                        target_note_id.title AS target_note_title,
                        target_note_id.overlay_note_id
                            AS target_overlay_note_id,
                        target_note_id.overlay_note_id.relative_path
                            AS target_relative_path
                    FROM note_link
                    WHERE target_note_id = $projected_note_id
                )
            }
        };
        """

    @staticmethod
    def _outcome(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return next(
            (
                row
                for row in reversed(rows)
                if isinstance(row, dict) and row.get("outcome")
            ),
            {},
        )

    @staticmethod
    def _reservation(outcome: dict[str, Any]) -> OverlayReservation:
        try:
            note = OverlayNote.model_validate(outcome.get("note"))
            receipt = OverlayMutationReceipt.model_validate(outcome.get("receipt"))
        except ValidationError:
            raise OverlayRepositoryError("overlay_reservation_invalid") from None
        if receipt.overlay_note_id != note.id:
            raise OverlayRepositoryError("overlay_reservation_invalid")
        return OverlayReservation(
            operation_id=receipt.operation_id,
            idempotency_key=receipt.idempotency_key,
            overlay_note_id=note.id,
            projected_note_id=note.projected_note_id,
            relative_path=note.relative_path,
            title=note.title,
            kind=note.kind,
            date_key=note.date_key,
            expected_revision=receipt.expected_revision,
        )


__all__ = [
    "OverlayConflictError",
    "OverlayRepository",
    "OverlayRepositoryError",
    "OverlayReservation",
]
