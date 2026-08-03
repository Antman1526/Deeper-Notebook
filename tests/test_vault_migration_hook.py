from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone, tzinfo

import pytest

from deeper_notebook.database import async_migrate


class _UndefinedOffsetTimezone(tzinfo):
    def utcoffset(self, _value):
        return None

    def dst(self, _value):
        return None


def test_canonical_title_key_matches_projection_and_migration_semantics():
    from deeper_notebook.vault.normalization import canonical_title_key

    assert canonical_title_key("  Ｃａｆｅ\u0301 \t  PROJECT\n X  ") == "café project x"
    assert canonical_title_key("\u2003Straße\u00a0") == "strasse"


def test_discovered_migration_33_carries_numeric_hook_identity():
    ups, downs = async_migrate.AsyncMigrationManager._discover_migrations()

    assert ups[32].version == 33
    assert downs[32] is not None
    assert downs[32].version == 33


def test_migration_33_schema_phase_enters_explicit_timestamp_carriage_mode():
    ups, _downs = async_migrate.AsyncMigrationManager._discover_migrations()

    note_preservation = (
        "DEFINE FIELD OVERWRITE updated ON note "
        "DEFAULT time::now() VALUE $before OR time::now();"
    )
    note_passthrough = (
        "DEFINE FIELD IF NOT EXISTS updated ON note DEFAULT time::now();"
    )
    link_preservation = (
        "DEFINE FIELD OVERWRITE updated ON TABLE note_link TYPE datetime "
        "DEFAULT time::now() VALUE $before OR time::now();"
    )
    link_passthrough = (
        "DEFINE FIELD IF NOT EXISTS updated ON TABLE note_link TYPE datetime "
        "DEFAULT time::now();"
    )
    assert ups[32].sql.index(note_preservation) < ups[32].sql.index(note_passthrough)
    assert ups[32].sql.index(link_preservation) < ups[32].sql.index(link_passthrough)
    assert ups[32].sql.index(
        "REMOVE FIELD IF EXISTS updated ON note;"
    ) < ups[32].sql.index(note_passthrough)
    assert ups[32].sql.index(
        "REMOVE FIELD IF EXISTS updated ON TABLE note_link;"
    ) < ups[32].sql.index(link_passthrough)


@pytest.mark.asyncio
async def test_migration_33_runs_hook_after_schema_before_version_bump(monkeypatch):
    events: list[str] = []

    class Connection:
        async def query(self, _sql):
            events.append("schema")

    @asynccontextmanager
    async def connection_factory():
        yield Connection()

    async def hook(version, _connection):
        events.append(f"hook-{version}")

    async def bump():
        events.append("bump")

    monkeypatch.setattr(async_migrate, "db_connection", connection_factory)
    monkeypatch.setattr(
        async_migrate,
        "run_python_migration_hook",
        hook,
        raising=False,
    )
    monkeypatch.setattr(async_migrate, "bump_version", bump)
    migration = async_migrate.AsyncMigration("DEFINE TABLE example;", version=33)

    await migration.run()

    assert events == ["schema", "hook-33", "bump"]


@pytest.mark.asyncio
async def test_migration_33_hook_failure_never_records_version(monkeypatch):
    bumped = False

    class Connection:
        async def query(self, _sql):
            return None

    @asynccontextmanager
    async def connection_factory():
        yield Connection()

    async def hook(_version, _connection):
        raise RuntimeError("synthetic hook failure")

    async def bump():
        nonlocal bumped
        bumped = True

    monkeypatch.setattr(async_migrate, "db_connection", connection_factory)
    monkeypatch.setattr(
        async_migrate,
        "run_python_migration_hook",
        hook,
        raising=False,
    )
    monkeypatch.setattr(async_migrate, "bump_version", bump)
    migration = async_migrate.AsyncMigration("DEFINE TABLE example;", version=33)

    with pytest.raises(RuntimeError, match="synthetic hook failure"):
        await migration.run()

    assert bumped is False


@pytest.mark.asyncio
async def test_backfill_treats_database_error_strings_as_hook_failure():
    from deeper_notebook.database.migration_33_vault_backfill import (
        run_vault_migration_33_backfill,
    )

    class Connection:
        selected = False

        async def query(self, statement, _variables=None):
            if "SELECT id, title, updated FROM note" in statement and not self.selected:
                self.selected = True
                return [
                    {
                        "id": "note:old",
                        "title": "Old",
                        "updated": datetime(2026, 7, 27, tzinfo=timezone.utc),
                    }
                ]
            if "FOR $item IN $items" in statement:
                return "synthetic database error"
            return []

    with pytest.raises(RuntimeError, match="migration_33_query_failed"):
        await run_vault_migration_33_backfill(Connection(), batch_size=1)


@pytest.mark.asyncio
async def test_backfill_selects_only_none_keys_not_completed_empty_keys():
    from deeper_notebook.database.migration_33_vault_backfill import (
        run_vault_migration_33_backfill,
    )

    class Connection:
        statements: list[str] = []

        async def query(self, statement, _variables=None):
            self.statements.append(statement)
            if "canonical_updated_fields_restored" in statement:
                return {"canonical_updated_fields_restored": True}
            return []

    connection = Connection()
    await run_vault_migration_33_backfill(connection)

    note_select = next(
        statement
        for statement in connection.statements
        if "SELECT id, title, updated FROM note" in statement
    )
    link_select = next(
        statement
        for statement in connection.statements
        if "SELECT id, target_text, updated FROM note_link" in statement
    )
    assert "title_key = NONE" in note_select
    assert "title_key = ''" not in note_select
    assert "target_title_key = NONE" in link_select
    assert "target_title_key = ''" not in link_select


@pytest.mark.asyncio
async def test_note_key_batch_is_fixed_transaction_and_hook_restores_link_updated_ddl():
    from deeper_notebook.database.migration_33_vault_backfill import (
        run_vault_migration_33_backfill,
    )

    class Connection:
        selected = False
        statements: list[tuple[str, dict | None]] = []
        historical_updated = datetime(2026, 7, 27, 12, 34, tzinfo=timezone.utc)

        async def query(self, statement, variables=None):
            self.statements.append((statement, variables))
            if "SELECT id, title, updated FROM note" in statement and not self.selected:
                self.selected = True
                return [
                    {
                        "id": "note:old",
                        "title": "Old",
                        "updated": self.historical_updated,
                    }
                ]
            if "BEGIN TRANSACTION;" in statement:
                if "canonical_updated_fields_restored" in statement:
                    return {"canonical_updated_fields_restored": True}
                return {"updated_preserved": True}
            return []

    connection = Connection()
    await run_vault_migration_33_backfill(connection, batch_size=1)

    transaction, variables = next(
        call for call in connection.statements if "SET title_key" in call[0]
    )
    assert transaction.strip().startswith("BEGIN TRANSACTION;")
    assert "DEFINE FIELD" not in transaction
    assert "updated = $item.updated" in transaction
    assert transaction.index("RETURN { updated_preserved: true };") < transaction.index(
        "COMMIT TRANSACTION;"
    )
    assert variables == {
        "items": [
            {
                "record_id": "note:old",
                "title_key": "old",
                "updated": connection.historical_updated,
            }
        ]
    }
    restoration = next(
        statement
        for statement, _variables in connection.statements
        if "canonical_updated_fields_restored" in statement
    )
    assert "DEFINE FIELD OVERWRITE updated ON note " not in restoration
    assert (
        "DEFINE FIELD OVERWRITE updated ON TABLE note_link TYPE datetime "
        "DEFAULT time::now() VALUE time::now();"
    ) in restoration
    assert restoration.index(
        "RETURN { canonical_updated_fields_restored: true };"
    ) < restoration.index("COMMIT TRANSACTION;")


@pytest.mark.asyncio
async def test_migration_36_hook_restores_note_updated_after_note_schema_changes():
    from deeper_notebook.database.migration_33_vault_backfill import (
        run_python_migration_hook,
    )

    class Connection:
        statements: list[tuple[str, dict | None]] = []

        async def query(self, statement, variables=None):
            self.statements.append((statement, variables))
            if "canonical_note_updated_field_restored" in statement:
                return {"canonical_note_updated_field_restored": True}
            return []

    connection = Connection()
    await run_python_migration_hook(36, connection)

    assert len(connection.statements) == 1
    restoration, variables = connection.statements[0]
    assert variables == {}
    assert (
        "DEFINE FIELD OVERWRITE updated ON note "
        "DEFAULT time::now() VALUE time::now();"
    ) in restoration
    assert "ON TABLE note_link" not in restoration
    assert restoration.index(
        "RETURN { canonical_note_updated_field_restored: true };"
    ) < restoration.index("COMMIT TRANSACTION;")


@pytest.mark.asyncio
async def test_link_batches_are_fixed_timestamp_preserving_transactions():
    from deeper_notebook.database.migration_33_vault_backfill import (
        run_vault_migration_33_backfill,
    )

    class Connection:
        link_key_selected = False
        reconcile_selected = False
        statements: list[tuple[str, dict | None]] = []
        historical_updated = datetime(2026, 7, 27, 12, 34, tzinfo=timezone.utc)

        async def query(self, statement, variables=None):
            self.statements.append((statement, variables))
            if (
                "SELECT id, target_text, updated FROM note_link" in statement
                and not self.link_key_selected
            ):
                self.link_key_selected = True
                return [
                    {
                        "id": "note_link:old",
                        "target_text": "Target",
                        "updated": self.historical_updated,
                    }
                ]
            if (
                "source_note_id,\n                    target_title_key" in statement
                and not self.reconcile_selected
            ):
                self.reconcile_selected = True
                return [
                    {
                        "id": "note_link:old",
                        "source_note_id": "note:source",
                        "target_title_key": "target",
                        "target_note_id": None,
                        "resolved": False,
                        "updated": self.historical_updated,
                    }
                ]
            if "SELECT id, vault_id FROM note" in statement:
                return [{"id": "note:source", "vault_id": "vault_mount:one"}]
            if "SELECT id FROM note" in statement:
                return [{"id": "note:target"}]
            if "BEGIN TRANSACTION;" in statement:
                if "canonical_updated_fields_restored" in statement:
                    return {"canonical_updated_fields_restored": True}
                return {"updated_preserved": True}
            return []

    connection = Connection()
    await run_vault_migration_33_backfill(connection, batch_size=1)

    transactions = [
        statement
        for statement, _variables in connection.statements
        if "UPDATE $item.record_id" in statement
    ]
    assert len(transactions) == 2
    for transaction in transactions:
        assert transaction.strip().startswith("BEGIN TRANSACTION;")
        assert "DEFINE FIELD" not in transaction
        assert "updated = $item.updated" in transaction
        assert transaction.index(
            "RETURN { updated_preserved: true };"
        ) < transaction.index("COMMIT TRANSACTION;")
    update_batches = [
        variables
        for statement, variables in connection.statements
        if "UPDATE $item.record_id" in statement
    ]
    assert all(
        item["updated"] == connection.historical_updated
        for variables in update_batches
        for item in variables["items"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_updated",
    [
        None,
        "not-a-datetime",
        datetime(2026, 7, 27, tzinfo=_UndefinedOffsetTimezone()),
    ],
)
async def test_note_key_backfill_rejects_missing_or_invalid_updated(missing_updated):
    from deeper_notebook.database.migration_33_vault_backfill import (
        run_vault_migration_33_backfill,
    )

    class Connection:
        selected = False

        async def query(self, statement, _variables=None):
            if "SELECT id, title, updated FROM note" in statement and not self.selected:
                self.selected = True
                return [
                    {
                        "id": "note:old",
                        "title": "Old",
                        "updated": missing_updated,
                    }
                ]
            return []

    with pytest.raises(RuntimeError, match="migration_33_note_updated_invalid"):
        await run_vault_migration_33_backfill(Connection(), batch_size=1)
