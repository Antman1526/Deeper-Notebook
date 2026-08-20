"""v0.8.67m — tests for scheduled-export pruning.

The export itself shells out to the bundled surreal binary against the running
DB (not unit-tested); the retention math is pure and pinned here.
"""

from __future__ import annotations

import os

from desktop.launcher import Supervisor


def _mk(tmp_path, name, mtime):
    f = tmp_path / name
    f.write_text("x")
    os.utime(f, (mtime, mtime))
    return f


def test_prune_keeps_only_newest_n(tmp_path):
    made = [
        _mk(tmp_path, f"auto-export-2026010{i}-000000.surql", 1_000_000 + i * 100)
        for i in range(10)
    ]
    # An unrelated backup file must NOT be touched by the prune.
    other = tmp_path / "surreal-export-manual.surql"
    other.write_text("keep me")

    Supervisor._prune_old_exports(tmp_path, keep=3)

    remaining = {p.name for p in tmp_path.glob("auto-export-*.surql")}
    assert remaining == {made[-1].name, made[-2].name, made[-3].name}
    assert other.exists()


def test_prune_noop_when_under_keep(tmp_path):
    _mk(tmp_path, "auto-export-a.surql", 1)
    _mk(tmp_path, "auto-export-b.surql", 2)
    Supervisor._prune_old_exports(tmp_path, keep=7)
    assert len(list(tmp_path.glob("auto-export-*.surql"))) == 2


def test_prune_missing_dir_is_safe(tmp_path):
    # Must not raise when the backup dir doesn't exist yet.
    Supervisor._prune_old_exports(tmp_path / "does-not-exist", keep=3)


def test_prune_keep_floor_is_one(tmp_path):
    for i in range(3):
        _mk(tmp_path, f"auto-export-{i}.surql", i)
    # keep=0 is clamped to 1 (never wipe everything).
    Supervisor._prune_old_exports(tmp_path, keep=0)
    assert len(list(tmp_path.glob("auto-export-*.surql"))) == 1
