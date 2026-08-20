"""ONP v0.6.12 — Tests for AsyncMigrationManager._discover_migrations.

Two bugs caught by code review:
  1. Migration numbering gap silently produced wrong version numbers (the
     manager would store DB version 4 while the SQL actually run was
     migration #5, because deleting 4.surrealql left a [m1,m2,m3,m5]
     list and run_all indexed it as 0..3).
  2. run_one_down on a version with no matching `<n>_down.surrealql`
     would IndexError instead of raising a clear error.

These tests exercise the discovery + parallel-list invariants without
touching SurrealDB.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deeper_notebook.database.async_migrate import (
    AsyncMigrationManager,
    AsyncMigrationRunner,
)


def _write_migration_files(
    d: Path, ns: list[int], with_downs: list[int] = None
) -> None:
    """Write empty migration files `1.surrealql`, `2.surrealql`, ... into d.
    with_downs: list of n's that also get a <n>_down.surrealql."""
    with_downs = with_downs or []
    d.mkdir(parents=True, exist_ok=True)
    for n in ns:
        (d / f"{n}.surrealql").write_text(f"-- migration {n}\n")
    for n in with_downs:
        (d / f"{n}_down.surrealql").write_text(f"-- down for {n}\n")


def test_discover_contiguous_set_returns_ordered_ups(tmp_path):
    _write_migration_files(tmp_path, ns=[1, 2, 3], with_downs=[1, 2, 3])
    ups, downs = AsyncMigrationManager._discover_migrations(mig_dir=tmp_path)
    assert len(ups) == 3
    assert len(downs) == 3
    assert all(d is not None for d in downs)


def test_discover_pads_downs_with_none_when_missing(tmp_path):
    """If migration 2 has no _down file, downs[1] is None — must NOT shrink
    the list (would otherwise misalign indices in run_one_down)."""
    _write_migration_files(tmp_path, ns=[1, 2, 3], with_downs=[1, 3])
    ups, downs = AsyncMigrationManager._discover_migrations(mig_dir=tmp_path)
    assert len(ups) == len(downs) == 3
    assert downs[0] is not None  # 1_down exists
    assert downs[1] is None  # 2_down missing
    assert downs[2] is not None  # 3_down exists


def test_discover_raises_on_gap(tmp_path):
    """The original bug: missing migration 4 in a 1,2,3,5 set used to silently
    produce a list of len 4. Must now raise with a clear message."""
    _write_migration_files(tmp_path, ns=[1, 2, 3, 5])
    with pytest.raises(RuntimeError, match=r"gaps.*4\.surrealql"):
        AsyncMigrationManager._discover_migrations(mig_dir=tmp_path)


def test_discover_raises_with_multiple_gaps(tmp_path):
    _write_migration_files(tmp_path, ns=[1, 3, 6])
    with pytest.raises(RuntimeError) as exc:
        AsyncMigrationManager._discover_migrations(mig_dir=tmp_path)
    msg = str(exc.value)
    assert "2.surrealql" in msg
    assert "4.surrealql" in msg
    assert "5.surrealql" in msg


def test_discover_empty_dir_returns_empty_lists(tmp_path):
    """A fresh repo with no migrations should not raise — just produce
    empty lists, so the manager reports needs_migration=False."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    ups, downs = AsyncMigrationManager._discover_migrations(mig_dir=tmp_path)
    assert ups == [] and downs == []


def test_default_migration_discovery_uses_canonical_package_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    ups, downs = AsyncMigrationManager._discover_migrations()

    assert len(ups) >= 1
    assert len(downs) == len(ups)


def test_default_migration_discovery_includes_vault_repair_33_and_down():
    ups, downs = AsyncMigrationManager._discover_migrations()

    assert len(ups) >= 33
    assert "idx_note_vault_title_key" in ups[32].sql
    assert "idx_vault_trust_manifest" in ups[32].sql
    assert downs[32] is not None
    assert "schema_preserved: true" in downs[32].sql
    assert ups[32].version == 33
    assert downs[32].version == 33


def test_default_migration_discovery_includes_overlay_36_and_down():
    ups, downs = AsyncMigrationManager._discover_migrations()

    assert len(ups) >= 36
    assert "overlay_space" in ups[35].sql
    assert "overlay_mutation_receipt" in ups[35].sql
    assert downs[35] is not None
    assert "REMOVE TABLE IF EXISTS overlay_note" in downs[35].sql


def test_default_migration_discovery_includes_overlay_index_repair_37_and_down():
    ups, downs = AsyncMigrationManager._discover_migrations()

    assert len(ups) >= 37
    assert "REMOVE INDEX IF EXISTS idx_overlay_daily" in ups[36].sql
    assert downs[36] is not None
    assert "repaired_index_restored: false" in downs[36].sql
    assert ups[36].version == 37
    assert downs[36].version == 37


def test_default_migration_discovery_includes_unified_engine_38_and_down():
    ups, downs = AsyncMigrationManager._discover_migrations()

    assert len(ups) >= 38
    assert "knowledge_engine_document" in ups[37].sql
    assert downs[37] is not None
    assert "schema_preserved: true" in downs[37].sql
    assert ups[37].version == 38
    assert downs[37].version == 38


def test_default_migration_discovery_includes_navigation_39_and_down():
    ups, downs = AsyncMigrationManager._discover_migrations()

    assert len(ups) >= 39
    assert "knowledge_bookmark_folder" in ups[38].sql
    assert "knowledge_navigation_operation_receipt" in ups[38].sql
    assert downs[38] is not None
    assert "REMOVE TABLE IF EXISTS knowledge_bookmark;" in downs[38].sql
    assert ups[38].version == 39
    assert downs[38].version == 39


def test_migration_46_is_symmetric_and_schema_full():
    ups, downs = AsyncMigrationManager._discover_migrations()

    assert ups[45].version == 46
    sql = ups[45].sql
    assert "DEFINE TABLE IF NOT EXISTS source_visual_cache SCHEMAFULL" in sql
    assert "DEFINE TABLE IF NOT EXISTS source_visual_claim SCHEMAFULL" in sql
    assert "DEFINE TABLE IF NOT EXISTS source_visual_operation SCHEMAFULL" in sql
    assert (
        "DEFINE FIELD IF NOT EXISTS source_locator ON TABLE source_visual_cache TYPE object"
        in sql
    )
    assert "source_locator ON TABLE source_visual_cache FLEXIBLE TYPE object" not in sql
    assert (
        "DEFINE FIELD IF NOT EXISTS source_locator.page ON TABLE source_visual_cache TYPE option<int> "
        "ASSERT $value = NONE OR ($value >= 1 AND $value <= 24);"
    ) in sql
    assert (
        "DEFINE FIELD IF NOT EXISTS source_locator.timestamp_ms ON TABLE source_visual_cache TYPE option<int> "
        "ASSERT $value = NONE OR $value >= 0;"
    ) in sql
    assert (
        "DEFINE FIELD IF NOT EXISTS source_locator.resource_id ON TABLE source_visual_cache TYPE option<string> "
        "ASSERT $value = NONE OR (string::len($value) >= 1 AND string::len($value) <= 128);"
    ) in sql
    assert (
        "($value.page != NONE AND $value.timestamp_ms = NONE AND $value.resource_id = NONE)"
        in sql
    )
    assert (
        "($value.page = NONE AND $value.timestamp_ms != NONE AND $value.resource_id = NONE)"
        in sql
    )
    assert (
        "($value.page = NONE AND $value.timestamp_ms = NONE AND $value.resource_id != NONE)"
        in sql
    )
    assert downs[45] is not None
    assert "REMOVE TABLE IF EXISTS source_visual_operation" in downs[45].sql
    assert "REMOVE TABLE IF EXISTS source_visual_claim" in downs[45].sql
    assert "REMOVE TABLE IF EXISTS source_visual_cache" in downs[45].sql


def test_discover_ignores_non_numeric_files(tmp_path):
    """README.md / *.txt in the migrations dir must not break discovery."""
    _write_migration_files(tmp_path, ns=[1, 2])
    (tmp_path / "README.surrealql").write_text("not a migration")
    ups, downs = AsyncMigrationManager._discover_migrations(mig_dir=tmp_path)
    assert len(ups) == 2


@pytest.mark.asyncio
async def test_run_one_down_raises_clear_error_for_missing_down(monkeypatch, tmp_path):
    """If we're at version 2 and 2_down.surrealql doesn't exist, rolling back
    must raise a clear RuntimeError instead of IndexError-ing."""
    _write_migration_files(tmp_path, ns=[1, 2], with_downs=[1])  # no 2_down
    ups, downs = AsyncMigrationManager._discover_migrations(mig_dir=tmp_path)
    runner = AsyncMigrationRunner(up_migrations=ups, down_migrations=downs)

    # Stub get_latest_version → 2 (pretend DB is at version 2)
    monkeypatch.setattr(
        "deeper_notebook.database.async_migrate.get_latest_version",
        _AsyncReturn(2),
    )

    with pytest.raises(RuntimeError, match=r"no matching 2_down"):
        await runner.run_one_down()


def _AsyncReturn(value):
    async def _f():
        return value

    return _f
