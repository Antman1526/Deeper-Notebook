"""Bounded data repair for vault title keys introduced by migration 33."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from deeper_notebook.vault.normalization import canonical_title_key

MIGRATION_33_BATCH_SIZE = 128
MIGRATION_33_MAX_ROWS = 1_000_000

_NOTE_KEY_BATCH_TRANSACTION = """
BEGIN TRANSACTION;
FOR $item IN $items {
    UPDATE $item.record_id SET title_key = $item.title_key,
        updated = $item.updated;
};
RETURN { updated_preserved: true };
COMMIT TRANSACTION;
"""

_LINK_KEY_BATCH_TRANSACTION = """
BEGIN TRANSACTION;
FOR $item IN $items {
    UPDATE $item.record_id SET target_title_key = $item.target_title_key,
        updated = $item.updated;
};
RETURN { updated_preserved: true };
COMMIT TRANSACTION;
"""

_LINK_RECONCILIATION_BATCH_TRANSACTION = """
BEGIN TRANSACTION;
FOR $item IN $items {
    UPDATE $item.record_id SET
        target_note_id = $item.target_note_id,
        resolved = $item.resolved,
        updated = $item.updated;
};
RETURN { updated_preserved: true };
COMMIT TRANSACTION;
"""

_RESTORE_CANONICAL_LINK_UPDATED_FIELD_TRANSACTION = """
BEGIN TRANSACTION;
DEFINE FIELD OVERWRITE updated ON TABLE note_link TYPE datetime DEFAULT time::now() VALUE time::now();
RETURN { canonical_updated_fields_restored: true };
COMMIT TRANSACTION;
"""

_RESTORE_CANONICAL_NOTE_UPDATED_FIELD_TRANSACTION = """
BEGIN TRANSACTION;
DEFINE FIELD OVERWRITE updated ON note DEFAULT time::now() VALUE time::now();
RETURN { canonical_note_updated_field_restored: true };
COMMIT TRANSACTION;
"""


class MigrationConnection(Protocol):
    async def query(
        self,
        statement: str,
        variables: dict[str, Any] | None = None,
    ) -> Any: ...


def _rows(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, str):
        raise RuntimeError("migration_33_query_failed")
    if result is None:
        return []
    if isinstance(result, dict):
        return [result]
    if isinstance(result, list):
        if not all(isinstance(row, dict) for row in result):
            raise RuntimeError("migration_33_result_invalid")
        return result
    raise RuntimeError("migration_33_result_invalid")


def _check_bound(processed: int) -> None:
    if processed > MIGRATION_33_MAX_ROWS:
        raise RuntimeError("migration_33_row_limit_exceeded")


def _historical_updated(row: dict[str, Any], *, error_code: str) -> datetime:
    updated = row.get("updated")
    if not isinstance(updated, datetime) or updated.tzinfo is None:
        raise RuntimeError(error_code)
    try:
        offset = updated.utcoffset()
    except Exception as exc:
        raise RuntimeError(error_code) from exc
    if offset is None:
        raise RuntimeError(error_code)
    return updated


async def _execute(
    connection: MigrationConnection,
    statement: str,
    variables: dict[str, Any],
    *,
    proof_key: str = "updated_preserved",
) -> None:
    result = await connection.query(statement, variables)
    rows = _rows(result)
    if rows != [{proof_key: True}]:
        raise RuntimeError("migration_33_proof_missing")


async def _backfill_note_keys(
    connection: MigrationConnection,
    *,
    batch_size: int,
) -> None:
    processed = 0
    while True:
        rows = _rows(
            await connection.query(
                """
                SELECT id, title, updated FROM note
                WHERE vault_id != NONE
                AND title_key = NONE
                ORDER BY id LIMIT $batch_size;
                """,
                {"batch_size": batch_size},
            )
        )
        if not rows:
            return
        updates = []
        for row in rows:
            title = row.get("title")
            if not isinstance(title, str):
                raise RuntimeError("migration_33_external_note_title_missing")
            updates.append(
                {
                    "record_id": row["id"],
                    "title_key": canonical_title_key(title),
                    "updated": _historical_updated(
                        row,
                        error_code="migration_33_note_updated_invalid",
                    ),
                }
            )
        await _execute(
            connection,
            _NOTE_KEY_BATCH_TRANSACTION,
            {"items": updates},
        )
        processed += len(updates)
        _check_bound(processed)


async def _backfill_link_keys(
    connection: MigrationConnection,
    *,
    batch_size: int,
) -> None:
    processed = 0
    while True:
        rows = _rows(
            await connection.query(
                """
                SELECT id, target_text, updated FROM note_link
                WHERE target_title_key = NONE
                ORDER BY id LIMIT $batch_size;
                """,
                {"batch_size": batch_size},
            )
        )
        if not rows:
            return
        updates = []
        for row in rows:
            target_text = row.get("target_text")
            if not isinstance(target_text, str):
                raise RuntimeError("migration_33_link_target_missing")
            updates.append(
                {
                    "record_id": row["id"],
                    "target_title_key": canonical_title_key(target_text),
                    "updated": _historical_updated(
                        row,
                        error_code="migration_33_link_updated_invalid",
                    ),
                }
            )
        await _execute(
            connection,
            _LINK_KEY_BATCH_TRANSACTION,
            {"items": updates},
        )
        processed += len(updates)
        _check_bound(processed)


async def _reconcile_links(
    connection: MigrationConnection,
    *,
    batch_size: int,
) -> None:
    offset = 0
    while True:
        links = _rows(
            await connection.query(
                """
                SELECT
                    id,
                    source_note_id,
                    target_title_key,
                    target_note_id,
                    resolved,
                    updated
                FROM note_link
                ORDER BY id LIMIT $batch_size START $offset;
                """,
                {"batch_size": batch_size, "offset": offset},
            )
        )
        if not links:
            return
        _check_bound(offset + len(links))
        source_ids = list(
            {
                str(link["source_note_id"]): link["source_note_id"] for link in links
            }.values()
        )
        source_notes = _rows(
            await connection.query(
                """
                SELECT id, vault_id FROM note
                WHERE id IN $source_note_ids;
                """,
                {"source_note_ids": source_ids},
            )
        )
        vault_by_note = {
            str(row["id"]): row.get("vault_id")
            for row in source_notes
            if row.get("vault_id") is not None
        }
        candidates: dict[tuple[str, str], list[Any]] = {}
        for link in links:
            vault_id = vault_by_note.get(str(link["source_note_id"]))
            title_key = link["target_title_key"]
            if vault_id is None:
                continue
            candidate_key = (str(vault_id), title_key)
            if candidate_key in candidates:
                continue
            candidates[candidate_key] = _rows(
                await connection.query(
                    """
                    SELECT id FROM note
                    WHERE vault_id = $vault_id
                    AND title_key = $title_key
                    ORDER BY id LIMIT 2;
                    """,
                    {
                        "vault_id": vault_id,
                        "title_key": title_key,
                    },
                )
            )
        updates = []
        for link in links:
            vault_id = vault_by_note.get(str(link["source_note_id"]))
            matches = (
                candidates.get((str(vault_id), link["target_title_key"]), [])
                if vault_id is not None
                else []
            )
            target_note_id = matches[0]["id"] if len(matches) == 1 else None
            resolved = len(matches) == 1
            current_target = link.get("target_note_id")
            target_unchanged = (
                current_target is None
                if target_note_id is None
                else str(current_target) == str(target_note_id)
            )
            if target_unchanged and link.get("resolved") is resolved:
                continue
            updates.append(
                {
                    "record_id": link["id"],
                    "target_note_id": target_note_id,
                    "resolved": resolved,
                    "updated": _historical_updated(
                        link,
                        error_code="migration_33_link_updated_invalid",
                    ),
                }
            )
        if updates:
            await _execute(
                connection,
                _LINK_RECONCILIATION_BATCH_TRANSACTION,
                {"items": updates},
            )
        offset += len(links)


async def run_vault_migration_33_backfill(
    connection: MigrationConnection,
    *,
    batch_size: int = MIGRATION_33_BATCH_SIZE,
) -> None:
    if (
        not isinstance(batch_size, int)
        or isinstance(batch_size, bool)
        or batch_size <= 0
    ):
        raise ValueError("invalid_migration_33_batch_size")
    await _backfill_note_keys(connection, batch_size=batch_size)
    await _backfill_link_keys(connection, batch_size=batch_size)
    await _reconcile_links(connection, batch_size=batch_size)
    await _execute(
        connection,
        _RESTORE_CANONICAL_LINK_UPDATED_FIELD_TRANSACTION,
        {},
        proof_key="canonical_updated_fields_restored",
    )


async def run_python_migration_hook(
    version: int,
    connection: MigrationConnection,
) -> None:
    if version == 33:
        await run_vault_migration_33_backfill(connection)
    elif version == 36:
        await _execute(
            connection,
            _RESTORE_CANONICAL_NOTE_UPDATED_FIELD_TRANSACTION,
            {},
            proof_key="canonical_note_updated_field_restored",
        )


__all__ = [
    "MIGRATION_33_BATCH_SIZE",
    "run_python_migration_hook",
    "run_vault_migration_33_backfill",
]
