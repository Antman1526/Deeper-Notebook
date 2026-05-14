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

from open_notebook.database.async_migrate import (
    AsyncMigrationManager,
    AsyncMigrationRunner,
)


def _write_migration_files(d: Path, ns: list[int], with_downs: list[int] = None) -> None:
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
    assert downs[1] is None       # 2_down missing
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
        "open_notebook.database.async_migrate.get_latest_version",
        _AsyncReturn(2),
    )

    with pytest.raises(RuntimeError, match=r"no matching 2_down"):
        await runner.run_one_down()


def _AsyncReturn(value):
    async def _f():
        return value
    return _f
