"""v0.7.125 — tests for LangGraph SQLite checkpoint pruning.

Uses a tmp_path-backed sqlite file populated with LangGraph's actual
SqliteSaver to mimic real-world conditions. No external dep beyond
what the app already ships (langgraph-checkpoint-sqlite).

Covers:
  * No-op when sqlite file doesn't exist (fresh install)
  * No-op when tables don't exist (empty DB)
  * Keeps the most recent N checkpoints per thread, deletes older
  * Multi-thread: each thread's cap is independent
  * Orphan writes (whose checkpoint_id no longer exists) are cascaded
  * Returns counts that match what was actually deleted
  * Env-knob DEEPER_NOTEBOOK_CHECKPOINT_KEEP_PER_THREAD honored
  * Invalid env value falls back to default with a warning
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _make_checkpoint_db(path: Path, threads_and_counts: dict[str, int]) -> None:
    """Build a sqlite file with the LangGraph SqliteSaver schema and
    populate it with the requested number of checkpoints per thread.

    LangGraph's SqliteSaver creates the schema on `setup()`. We don't
    need the JSON-encoded checkpoint blob to be valid (we're not
    going to deserialize it) — just non-empty bytes.
    """
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    # Recreate the schema langgraph-checkpoint-sqlite uses.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            thread_id TEXT,
            checkpoint_ns TEXT,
            checkpoint_id TEXT,
            parent_checkpoint_id TEXT,
            type TEXT,
            checkpoint BLOB,
            metadata BLOB,
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS writes (
            thread_id TEXT,
            checkpoint_ns TEXT,
            checkpoint_id TEXT,
            task_id TEXT,
            idx INTEGER,
            channel TEXT,
            type TEXT,
            value BLOB,
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
        )
    """)
    # Populate. checkpoint_id is normally a uuid6 (time-prefixed);
    # for tests, an ordered zero-padded sequence is enough — the
    # window function sorts lexicographically and we need newest-last.
    for thread_id, count in threads_and_counts.items():
        for i in range(count):
            cid = f"{i:06d}-checkpoint"  # 000000-checkpoint = oldest
            conn.execute(
                "INSERT INTO checkpoints (thread_id, checkpoint_ns, "
                "checkpoint_id, parent_checkpoint_id, type, "
                "checkpoint, metadata) VALUES (?, '', ?, NULL, 'msgpack', "
                "X'00', X'00')",
                (thread_id, cid),
            )
            # Add 2 writes per checkpoint so the cascade tests can
            # detect the deletion.
            for idx in range(2):
                conn.execute(
                    "INSERT INTO writes (thread_id, checkpoint_ns, "
                    "checkpoint_id, task_id, idx, channel, type, value) "
                    "VALUES (?, '', ?, 'task-0', ?, 'messages', 'msgpack', "
                    "X'00')",
                    (thread_id, cid, idx),
                )
    conn.commit()
    conn.close()


def _count(path: Path, table: str) -> int:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_prune_no_op_when_file_missing(tmp_path):
    """v0.7.125 — A fresh install has no checkpoints.sqlite. Prune
    must silently return zero counts (NOT raise) so the lifespan task
    doesn't crash on first boot."""
    from deeper_notebook.utils.checkpoint_prune import prune_old_checkpoints

    missing = tmp_path / "does-not-exist.sqlite"
    result = prune_old_checkpoints(missing)
    assert result["checkpoints_deleted"] == 0
    assert result["writes_deleted"] == 0
    assert result["threads_seen"] == 0


def test_prune_no_op_when_tables_missing(tmp_path):
    """v0.7.125 — An existing sqlite file that doesn't have the
    LangGraph schema (someone ran a different sqlite tool on the
    path?) must NOT raise — silently skip."""
    from deeper_notebook.utils.checkpoint_prune import prune_old_checkpoints

    path = tmp_path / "empty.sqlite"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE something_else (x INTEGER)")
    conn.close()

    result = prune_old_checkpoints(path)
    assert result["checkpoints_deleted"] == 0
    assert result["writes_deleted"] == 0


def test_prune_keeps_most_recent_n_per_thread(tmp_path):
    """v0.7.125 — Core behavior. A thread with 100 checkpoints gets
    pruned to the N most recent (newest checkpoint_id wins because
    LangGraph's uuid6 IDs are sorted DESC for newest-first)."""
    from deeper_notebook.utils.checkpoint_prune import prune_old_checkpoints

    path = tmp_path / "checkpoints.sqlite"
    _make_checkpoint_db(path, {"thread-A": 100})

    # Sanity: 100 checkpoints + 200 writes pre-prune
    assert _count(path, "checkpoints") == 100
    assert _count(path, "writes") == 200

    result = prune_old_checkpoints(path, keep_per_thread=10)

    # 90 checkpoints deleted, 180 cascade writes deleted
    assert result["checkpoints_deleted"] == 90
    assert result["writes_deleted"] == 180
    assert result["threads_seen"] == 1
    assert _count(path, "checkpoints") == 10
    assert _count(path, "writes") == 20

    # Survivors are the NEWEST checkpoints (000090..000099)
    conn = sqlite3.connect(str(path))
    surviving_ids = sorted(
        row[0] for row in conn.execute("SELECT checkpoint_id FROM checkpoints")
    )
    conn.close()
    expected = sorted(f"{i:06d}-checkpoint" for i in range(90, 100))
    assert surviving_ids == expected


def test_prune_independent_per_thread(tmp_path):
    """v0.7.125 — Each thread's cap is independent. A heavy chat
    thread doesn't cause a light thread's history to be pruned."""
    from deeper_notebook.utils.checkpoint_prune import prune_old_checkpoints

    path = tmp_path / "checkpoints.sqlite"
    _make_checkpoint_db(
        path,
        {
            "heavy-thread": 80,
            "light-thread": 5,  # under the cap — should be untouched
            "medium-thread": 25,  # mostly under the cap of 10 — but trimmed
        },
    )

    result = prune_old_checkpoints(path, keep_per_thread=10)

    # heavy: 80 → 10 (70 deleted)
    # light: 5 → 5 (0 deleted — under cap)
    # medium: 25 → 10 (15 deleted)
    assert result["checkpoints_deleted"] == 70 + 0 + 15  # 85
    assert result["threads_seen"] == 3

    # Verify each thread's row count
    conn = sqlite3.connect(str(path))
    counts = dict(
        conn.execute("SELECT thread_id, COUNT(*) FROM checkpoints GROUP BY thread_id")
    )
    conn.close()
    assert counts["heavy-thread"] == 10
    assert counts["light-thread"] == 5
    assert counts["medium-thread"] == 10


def test_prune_cascades_orphan_writes(tmp_path):
    """v0.7.125 — When a checkpoint is deleted, its associated `writes`
    rows must be cleaned up too (otherwise we leak rows that can
    never be re-associated with a checkpoint)."""
    from deeper_notebook.utils.checkpoint_prune import prune_old_checkpoints

    path = tmp_path / "checkpoints.sqlite"
    _make_checkpoint_db(path, {"thread-X": 20})

    assert _count(path, "writes") == 40  # 2 per checkpoint × 20

    prune_old_checkpoints(path, keep_per_thread=5)

    # 5 checkpoints survive → 10 writes survive (2 per)
    assert _count(path, "checkpoints") == 5
    assert _count(path, "writes") == 10


def test_prune_honors_env_knob(tmp_path, monkeypatch):
    """v0.7.125 — DEEPER_NOTEBOOK_CHECKPOINT_KEEP_PER_THREAD env var sets the
    retention cap when no explicit `keep_per_thread` is passed."""
    from deeper_notebook.utils.checkpoint_prune import prune_old_checkpoints

    monkeypatch.setenv("DEEPER_NOTEBOOK_CHECKPOINT_KEEP_PER_THREAD", "3")

    path = tmp_path / "checkpoints.sqlite"
    _make_checkpoint_db(path, {"thread-A": 20})

    result = prune_old_checkpoints(path)  # NO explicit keep_per_thread

    assert result["checkpoints_deleted"] == 17
    assert _count(path, "checkpoints") == 3


def test_prune_falls_back_on_invalid_env(tmp_path, monkeypatch, caplog):
    """v0.7.125 — A typo in the env knob should fall back to the
    default (50) with a warning, NOT crash the pruning loop."""
    from deeper_notebook.utils.checkpoint_prune import prune_old_checkpoints

    monkeypatch.setenv("DEEPER_NOTEBOOK_CHECKPOINT_KEEP_PER_THREAD", "not-a-number")

    path = tmp_path / "checkpoints.sqlite"
    _make_checkpoint_db(path, {"thread-A": 100})

    result = prune_old_checkpoints(path)
    # Default cap is 50 — so 100 → 50, 50 deleted
    assert result["checkpoints_deleted"] == 50
    assert _count(path, "checkpoints") == 50


def test_prune_negative_env_falls_back_to_default(tmp_path, monkeypatch):
    """v0.7.125 — Negative values (which would prune EVERYTHING) are
    rejected with a warning + default-fallback."""
    from deeper_notebook.utils.checkpoint_prune import prune_old_checkpoints

    monkeypatch.setenv("DEEPER_NOTEBOOK_CHECKPOINT_KEEP_PER_THREAD", "-5")

    path = tmp_path / "checkpoints.sqlite"
    _make_checkpoint_db(path, {"thread-A": 100})

    result = prune_old_checkpoints(path)
    # Negative value rejected → default 50
    assert _count(path, "checkpoints") == 50


def test_prune_is_idempotent(tmp_path):
    """v0.7.125 — Running prune twice in a row should not delete
    anything the second time (nothing left to prune below the cap)."""
    from deeper_notebook.utils.checkpoint_prune import prune_old_checkpoints

    path = tmp_path / "checkpoints.sqlite"
    _make_checkpoint_db(path, {"thread-A": 100})

    first = prune_old_checkpoints(path, keep_per_thread=10)
    assert first["checkpoints_deleted"] == 90

    second = prune_old_checkpoints(path, keep_per_thread=10)
    assert second["checkpoints_deleted"] == 0
    assert second["writes_deleted"] == 0
    # threads_seen is non-zero because we still found 1 thread (just
    # nothing to remove within it).
    assert second["threads_seen"] == 1


def test_prune_returns_elapsed_ms(tmp_path):
    """v0.7.125 — Result dict includes elapsed_ms for operational
    visibility (matches the slow-query log philosophy)."""
    from deeper_notebook.utils.checkpoint_prune import prune_old_checkpoints

    path = tmp_path / "checkpoints.sqlite"
    _make_checkpoint_db(path, {"thread-A": 10})

    result = prune_old_checkpoints(path, keep_per_thread=5)
    assert "elapsed_ms" in result
    assert isinstance(result["elapsed_ms"], int)
    assert result["elapsed_ms"] >= 0
