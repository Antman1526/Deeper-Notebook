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
from deeper_notebook.database.repository import ensure_record_id, repo_query

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


async def _data_snapshot() -> dict[str, list[dict[str, Any]]]:
    """Capture every user-table row with stable ordering for teardown proof."""
    rows = await repo_query("INFO FOR DB;")
    database = rows[0] if isinstance(rows, list) else rows
    tables = database.get("tables") or database.get("tb") or {}
    return {
        table: _freeze(await repo_query(f"SELECT * FROM {table} ORDER BY id;"))
        for table in sorted(tables)
        if not table.startswith("_")
    }


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


@pytest_asyncio.fixture
async def migration_data_authority(
    clean_namespace: dict[str, Any],
) -> AsyncIterator[dict[str, list[dict[str, Any]]]]:
    """Seed exact IDs, then prove failed-down teardown restores all table rows."""
    seeded = {
        "source:rewind-data-deleted": {
            "title": "Deleted by failed down",
            "full_text": "original deleted source body",
        },
        "source:rewind-data-updated": {
            "title": "Updated by failed down",
            "full_text": "original updated source body",
        },
    }
    for record_id, payload in seeded.items():
        await repo_query(
            "CREATE $record SET title = $title, asset = NONE, full_text = $full_text;",
            {
                "record": ensure_record_id(record_id),
                **payload,
            },
        )

    expected = await _data_snapshot()
    try:
        yield expected
    finally:
        assert await _data_snapshot() == expected


async def _reference_traversal_targets() -> list[str]:
    """Return the real graph traversal targets for the seeded relation edge."""
    rows = await repo_query(
        """
        SELECT ->reference->notebook.id AS targets
        FROM source:rewind_relation_source;
        """
    )
    assert len(rows) == 1
    targets = rows[0]["targets"]
    assert isinstance(targets, list)
    return targets


@pytest_asyncio.fixture
async def migration_relation_authority(
    clean_namespace: dict[str, Any],
) -> AsyncIterator[list[dict[str, Any]]]:
    """Observe exact edge data and native traversal after rewind teardown."""
    await repo_query(
        """
        CREATE source:rewind_relation_source SET
            title = 'Rewind relation source',
            asset = NONE,
            full_text = 'relation source body';
        CREATE notebook:rewind_relation_notebook SET
            name = 'Rewind relation notebook';
        RELATE source:rewind_relation_source
            ->reference:rewind_relation_edge
            ->notebook:rewind_relation_notebook
            SET rewind_marker = 'original relation payload';
        """
    )
    expected_edge = await repo_query("SELECT * FROM reference:rewind_relation_edge;")
    assert len(expected_edge) == 1
    assert await _reference_traversal_targets() == ["notebook:rewind_relation_notebook"]
    try:
        yield expected_edge
    finally:
        assert await repo_query("SELECT * FROM reference:rewind_relation_edge;") == (
            expected_edge
        )
        assert await _reference_traversal_targets() == [
            "notebook:rewind_relation_notebook"
        ]


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
) -> AsyncIterator[list[dict[str, Any]]]:
    """Pin v47's pre-rewind default row so recovery cannot duplicate it."""
    await repo_query(
        """
        CREATE transformation:rewind_cornell_default SET
            name = 'Cornell Notes',
            title = 'Cornell Notes',
            description = 'pre-rewind default authority',
            prompt = 'pre-rewind default authority',
            apply_default = false;
        """
    )
    expected = await repo_query(
        "SELECT * FROM transformation WHERE name = 'Cornell Notes';"
    )
    assert len(expected) == 1
    try:
        yield expected
    finally:
        rows = await repo_query(
            "SELECT * FROM transformation WHERE name = 'Cornell Notes';"
        )
        assert rows == expected


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


async def test_migration_rewind_restores_rows_after_failed_down_data_mutation(
    migration_schema_authority,
    migration_data_authority,
    migration_rewind,
    monkeypatch,
):
    """Teardown must restore deleted and updated rows with their original IDs."""
    original_head = await get_latest_version()

    async def damaged_down_after_data_mutation(self) -> None:
        await repo_query(
            "DELETE $record;",
            {"record": ensure_record_id("source:rewind-data-deleted")},
        )
        await repo_query(
            "UPDATE $record SET full_text = $full_text;",
            {
                "record": ensure_record_id("source:rewind-data-updated"),
                "full_text": "corrupted updated source body",
            },
        )
        raise RuntimeError("injected-down-after-data-mutation")

    monkeypatch.setattr(
        AsyncMigrationRunner, "run_one_down", damaged_down_after_data_mutation
    )

    with pytest.raises(RuntimeError, match="injected-down-after-data-mutation"):
        await migration_rewind(original_head - 1)

    assert await get_latest_version() == original_head
    assert migration_data_authority["source"] != await repo_query(
        "SELECT * FROM source ORDER BY id;"
    )


async def test_migration_rewind_restores_relation_traversal_after_failed_down(
    migration_schema_authority,
    migration_relation_authority,
    migration_rewind,
    monkeypatch,
):
    """Failed-down recovery must preserve relation semantics, not just edge fields."""
    original_head = await get_latest_version()

    async def damaged_down_after_relation_mutation(self) -> None:
        await repo_query(
            "UPDATE reference:rewind_relation_edge SET rewind_marker = 'corrupted';"
        )
        await repo_query("DELETE reference:rewind_relation_edge;")
        raise RuntimeError("injected-down-after-relation-mutation")

    monkeypatch.setattr(
        AsyncMigrationRunner, "run_one_down", damaged_down_after_relation_mutation
    )

    with pytest.raises(RuntimeError, match="injected-down-after-relation-mutation"):
        await migration_rewind(original_head - 1)

    assert await get_latest_version() == original_head
    assert migration_relation_authority != await repo_query(
        "SELECT * FROM reference:rewind_relation_edge;"
    )
