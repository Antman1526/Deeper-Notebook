"""v0.7.32 — regression tests for the shared SQLite checkpoint helper.

Before v0.7.32, both chat.py and source_chat.py called
`sqlite3.connect()` directly with no WAL, no busy_timeout, no
integrity check. Two graphs racing the same file could "database is
locked"; a corrupted file would prevent API startup forever.

The helper at deeper_notebook.utils.sqlite_checkpoint:
- WAL journal_mode → concurrent reader + writer don't block
- busy_timeout=5000ms → brief writes wait out contention
- synchronous=NORMAL → WAL's recommended pairing
- Process-wide singleton per path → both graphs share state
- Light corruption recovery → rename aside + start fresh on integrity_check fail
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from deeper_notebook.utils import sqlite_checkpoint as ckpt


@pytest.fixture(autouse=True)
def _reset_cache():
    ckpt._reset_for_tests()
    yield
    ckpt._reset_for_tests()


# ---------------------------------------------------------------------------
# PRAGMA tuning
# ---------------------------------------------------------------------------


def test_connection_uses_wal_mode(tmp_path):
    conn = ckpt.get_checkpoint_connection(str(tmp_path / "chat.db"))
    mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert mode.lower() == "wal", f"expected WAL, got {mode}"


def test_connection_has_busy_timeout(tmp_path):
    conn = ckpt.get_checkpoint_connection(str(tmp_path / "chat.db"))
    timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
    assert timeout == 5000, f"expected 5000ms, got {timeout}"


def test_connection_uses_synchronous_normal(tmp_path):
    conn = ckpt.get_checkpoint_connection(str(tmp_path / "chat.db"))
    # synchronous returns 0=OFF / 1=NORMAL / 2=FULL / 3=EXTRA
    sync = conn.execute("PRAGMA synchronous;").fetchone()[0]
    assert sync == 1, f"expected NORMAL (1), got {sync}"


# ---------------------------------------------------------------------------
# Shared singleton
# ---------------------------------------------------------------------------


def test_same_path_returns_same_connection(tmp_path):
    """Both chat.py and source_chat.py target the same file; the
    helper must give them the SAME connection object so they don't
    race two SQLite writers on the same file."""
    p = str(tmp_path / "shared.db")
    a = ckpt.get_checkpoint_connection(p)
    b = ckpt.get_checkpoint_connection(p)
    assert a is b


def test_different_paths_get_different_connections(tmp_path):
    a = ckpt.get_checkpoint_connection(str(tmp_path / "a.db"))
    b = ckpt.get_checkpoint_connection(str(tmp_path / "b.db"))
    assert a is not b


# ---------------------------------------------------------------------------
# Corruption recovery
# ---------------------------------------------------------------------------


def test_corrupted_file_is_renamed_and_fresh_one_created(tmp_path):
    """Drop bytes that aren't valid SQLite into the checkpoint path,
    then ask the helper to open it. It should detect the corruption,
    move the bad file aside, create a clean one, and return a working
    connection."""
    p = tmp_path / "corrupt.db"
    p.write_bytes(b"this is not a valid sqlite file" * 100)

    conn = ckpt.get_checkpoint_connection(str(p))

    # The good connection should be usable
    conn.execute("CREATE TABLE IF NOT EXISTS sanity (id INTEGER);")
    conn.execute("INSERT INTO sanity (id) VALUES (1);")
    cur = conn.execute("SELECT id FROM sanity;")
    assert cur.fetchone() == (1,)

    # The corrupt file should have been renamed aside
    corrupt_files = list(tmp_path.glob("corrupt.corrupt-*.db"))
    assert corrupt_files, "expected the corrupt file to be renamed aside"


def test_empty_file_is_NOT_renamed_just_initialized(tmp_path):
    """A brand-new empty file is fine — SQLite will write a header
    on first use. Don't trigger the corruption rename for that."""
    p = tmp_path / "fresh.db"
    # Don't pre-create — let the helper do it.

    conn = ckpt.get_checkpoint_connection(str(p))
    conn.execute("CREATE TABLE t (x INTEGER);")
    conn.execute("INSERT INTO t VALUES (42);")

    # Nothing got renamed aside
    aside = list(tmp_path.glob("fresh.corrupt-*"))
    assert not aside, f"unexpected rename of fresh file: {aside}"


def test_directories_auto_created(tmp_path):
    """The helper must auto-mkdir the parent of the DB path."""
    nested = tmp_path / "deep" / "path" / "ckpt.db"
    conn = ckpt.get_checkpoint_connection(str(nested))
    assert nested.exists()
    conn.execute("CREATE TABLE t (x INTEGER);")  # smoke


def test_tuning_failure_closes_connection_before_corruption_recovery(tmp_path):
    """Windows cannot rename a corrupt DB while its failed tuning connection
    remains open, so _open_tuned must release that handle before re-raising."""

    class FailingConnection:
        closed = False

        def execute(self, _statement):
            raise sqlite3.DatabaseError("file is not a database")

        def close(self):
            self.closed = True

    conn = FailingConnection()
    with patch.object(ckpt.sqlite3, "connect", return_value=conn):
        with pytest.raises(sqlite3.DatabaseError):
            ckpt._open_tuned(str(tmp_path / "corrupt.db"))

    assert conn.closed is True


# ---------------------------------------------------------------------------
# Concurrency (smoke — WAL should let a reader and writer coexist)
# ---------------------------------------------------------------------------


def test_reader_and_writer_can_coexist_under_wal(tmp_path):
    """Open two connections to the same file (via different paths to
    bypass the singleton cache, simulating reader from one process +
    writer from another). Under WAL they should not deadlock on
    overlapping operations."""
    p = str(tmp_path / "concurrent.db")
    writer = ckpt.get_checkpoint_connection(p)
    writer.execute("CREATE TABLE t (x INTEGER);")

    # Manually open a SECOND raw connection to test cross-conn WAL
    reader = sqlite3.connect(p, isolation_level=None)
    reader.execute("PRAGMA busy_timeout=2000;")

    # Begin a write transaction on `writer` (acquires write lock)
    writer.execute("BEGIN IMMEDIATE;")
    writer.execute("INSERT INTO t VALUES (1);")

    # In default (non-WAL) journal, the reader would block here. Under
    # WAL, reads see the pre-transaction snapshot — non-blocking.
    cur = reader.execute("SELECT count(*) FROM t;")
    pre_commit_count = cur.fetchone()[0]

    writer.execute("COMMIT;")

    cur = reader.execute("SELECT count(*) FROM t;")
    post_commit_count = cur.fetchone()[0]

    # The point: the SELECT didn't deadlock or time out. Exact values
    # don't matter — we just need the read to have succeeded.
    assert isinstance(pre_commit_count, int)
    assert isinstance(post_commit_count, int)

    reader.close()
