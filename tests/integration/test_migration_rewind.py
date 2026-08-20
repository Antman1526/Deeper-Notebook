"""Real-SurrealDB regression proof for migration rewind teardown recovery."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

from deeper_notebook.database.async_migrate import (
    AsyncMigrationRunner,
    get_latest_version,
)
from deeper_notebook.database.repository import repo_query

pytestmark = pytest.mark.integration_surreal


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _freeze(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_freeze(item) for item in value]
    return value


async def _schema_snapshot() -> dict[str, Any]:
    rows = await repo_query("INFO FOR DB;")
    database = rows[0] if isinstance(rows, list) else rows
    tables = database.get("tables") or database.get("tb") or {}
    table_info = {}
    for table in sorted(tables):
        rows = await repo_query(f"INFO FOR TABLE {table};")
        table_info[table] = rows[0] if isinstance(rows, list) else rows
    return _freeze({"database": database, "tables": table_info})


@pytest_asyncio.fixture
async def migration_schema_authority(
    clean_namespace: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """Observe the actual migration_rewind teardown after it runs."""
    expected = await _schema_snapshot()
    try:
        yield expected
    finally:
        assert await _schema_snapshot() == expected


async def test_migration_rewind_recovers_schema_when_down_fails_before_lowering(
    migration_schema_authority,
    migration_rewind,
    monkeypatch,
):
    original_head = await get_latest_version()
    assert "text_search" in migration_schema_authority["database"]["functions"]

    async def damaged_down_before_lowering(self) -> None:
        await repo_query("REMOVE FUNCTION IF EXISTS fn::text_search;")
        raise RuntimeError("injected-down-before-lower-version")

    monkeypatch.setattr(
        AsyncMigrationRunner, "run_one_down", damaged_down_before_lowering
    )

    with pytest.raises(RuntimeError, match="injected-down-before-lower-version"):
        await migration_rewind(original_head - 1)

    assert await get_latest_version() == original_head
    rows = await repo_query("INFO FOR DB;")
    database = rows[0] if isinstance(rows, list) else rows
    assert "text_search" not in database["functions"]


@pytest_asyncio.fixture
async def migration_default_data_authority(
    clean_namespace: dict[str, Any],
) -> AsyncIterator[None]:
    """Assert the recovery path replays the default-data migration once."""
    try:
        yield
    finally:
        rows = await repo_query(
            "SELECT id FROM transformation WHERE name = 'Cornell Notes';"
        )
        assert len(rows) == 1


async def test_migration_rewind_replays_default_data_once_after_early_down_failure(
    migration_schema_authority,
    migration_default_data_authority,
    migration_rewind,
    monkeypatch,
):
    """A failed v41 down must not cause a preliminary v42..v50 replay."""
    original_run_one_down = AsyncMigrationRunner.run_one_down

    async def damaged_41_down_before_lowering(self) -> None:
        if await get_latest_version() == 41:
            await repo_query("REMOVE TABLE IF EXISTS study_plan_card;")
            raise RuntimeError("injected-v41-down-before-lower-version")
        await original_run_one_down(self)

    monkeypatch.setattr(
        AsyncMigrationRunner, "run_one_down", damaged_41_down_before_lowering
    )

    with pytest.raises(RuntimeError, match="injected-v41-down-before-lower-version"):
        await migration_rewind(40)

    assert await get_latest_version() == 41
