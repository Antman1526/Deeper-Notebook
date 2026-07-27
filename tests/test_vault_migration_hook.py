from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from deeper_notebook.database import async_migrate


def test_canonical_title_key_matches_projection_and_migration_semantics():
    from deeper_notebook.vault.normalization import canonical_title_key

    assert canonical_title_key("  Ｃａｆｅ\u0301 \t  PROJECT\n X  ") == "café project x"
    assert canonical_title_key("\u2003Straße\u00a0") == "strasse"


def test_discovered_migration_33_carries_numeric_hook_identity():
    ups, downs = async_migrate.AsyncMigrationManager._discover_migrations()

    assert ups[32].version == 33
    assert downs[32] is not None
    assert downs[32].version == 33


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
            if "SELECT id, title FROM note" in statement and not self.selected:
                self.selected = True
                return [{"id": "note:old", "title": "Old"}]
            if "FOR $item IN $items" in statement:
                return "synthetic database error"
            return []

    with pytest.raises(RuntimeError, match="migration_33_query_failed"):
        await run_vault_migration_33_backfill(Connection(), batch_size=1)
