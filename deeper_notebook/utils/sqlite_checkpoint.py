"""Shared SQLite tuning + connection for LangGraph checkpointing.

v0.7.32 — closes a race that the prior audit flagged:

  deeper_notebook/graphs/chat.py and source_chat.py each did:
      conn = sqlite3.connect(LANGGRAPH_CHECKPOINT_FILE, check_same_thread=False)
      memory = SqliteSaver(conn)

  Three real problems:

  1. SQLite defaults to journal_mode=DELETE (rollback journal). Under
     two concurrent writers (notebook chat + source chat) both holding
     reservations on the same DB file, the second one hits "database
     is locked" within a few-millisecond window — and LangGraph's
     SqliteSaver does not retry busy errors. Lost checkpoints, or a
     500 surfaces to the user mid-chat.

  2. No busy_timeout — when contention DOES occur, the second writer
     gives up immediately instead of waiting briefly for the writer
     lock to free up.

  3. Both modules call `sqlite3.connect()` independently — two
     separate connections to the same file, no shared lock. The
     `memory` object is module-level so it survives the module's
     lifetime, but the connection is not safe for cross-process use
     (worker + API both touch this file).

This module:

  - WAL mode → concurrent readers + writer don't block each other.
    Writes are appended to a sidecar `-wal` file; readers see a
    consistent snapshot. This alone makes the "database is locked"
    class of errors largely vanish for our typical workload.
  - busy_timeout = 5000ms — when the rare write contention still
    occurs (e.g. checkpoint mid-restart), wait up to 5s for the lock
    rather than failing.
  - synchronous=NORMAL — WAL's default; fast and safe with
    journal_mode=WAL (full fsync on checkpoint only, not every
    transaction).
  - One shared connection per file, returned via a memoised getter
    so chat.py and source_chat.py share state.
  - Light corruption recovery: at startup we run PRAGMA integrity_check
    — if it fails, the file is renamed aside with a `.corrupt-<ts>`
    suffix and a fresh one is created. The user loses old chat
    history (rare) but the API doesn't refuse to start.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Dict

from loguru import logger

# Module-level cache of (path → Connection). Two graphs sharing the
# same checkpoint file get the same connection — eliminates the
# "two-writer race on one file" failure mode.
_CONNECTIONS: dict[str, sqlite3.Connection] = {}


def _verify_integrity(conn: sqlite3.Connection) -> bool:
    """Run PRAGMA integrity_check. Returns True if clean."""
    try:
        cur = conn.execute("PRAGMA integrity_check;")
        rows = cur.fetchall()
        # SQLite returns [("ok",)] when healthy; anything else is a
        # corruption report (often multiple rows).
        if rows == [("ok",)]:
            return True
        logger.warning(
            "LangGraph checkpoint DB integrity check failed: {} rows of "
            "report; first row: {}",
            len(rows),
            rows[0] if rows else "<empty>",
        )
        return False
    except Exception as exc:
        logger.warning("Could not run integrity_check: {}", exc)
        # Treat unknown errors as "probably bad" but don't auto-rename —
        # better to surface the issue to the caller than silently
        # discard data on a flaky filesystem.
        return False


def _rename_corrupted(path: Path) -> None:
    """Move a corrupted DB aside so the next open() creates a fresh one.

    The user loses chat history but the API doesn't refuse to boot.
    We keep the corrupt file so a future tool / manual recovery can
    inspect it.
    """
    ts = int(time.time())
    aside = path.with_suffix(f".corrupt-{ts}{path.suffix}")
    try:
        path.rename(aside)
        # Also move sidecar WAL/SHM files if they exist
        for sfx in ("-wal", "-shm"):
            sidecar = path.with_name(path.name + sfx)
            if sidecar.exists():
                sidecar.rename(sidecar.with_name(aside.name + sfx))
        logger.warning(
            "Renamed corrupted checkpoint DB → {}. A fresh DB will be "
            "created on next chat. Old chat history is preserved on disk "
            "for manual recovery.",
            aside,
        )
    except Exception as exc:
        logger.error("Could not rename corrupted DB at {}: {}", path, exc)


def _open_tuned(path: str) -> sqlite3.Connection:
    """Open a sqlite3 connection with our standard tuning."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        path,
        check_same_thread=False,
        # isolation_level=None lets the SqliteSaver manage its own
        # transactions (the default Python wrapper holds an implicit
        # one, which conflicts with explicit BEGIN).
        isolation_level=None,
    )
    try:
        # PRAGMAs are SET on the connection; survive only for its lifetime.
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        # A corrupt DB can fail while applying the first PRAGMA. Close this
        # handle before the caller quarantines the file; Windows rejects a
        # rename while the failed connection still has it open.
        conn.close()
        raise
    return conn


def get_checkpoint_connection(path: str) -> sqlite3.Connection:
    """Return a process-wide singleton connection for the given path.

    Two graphs sharing the same path share the connection — see
    module docstring for why.

    Performs PRAGMA integrity_check once at first open. If the file
    is corrupted (or the PRAGMA itself fails with `file is not a
    database`), renames it aside and creates a fresh one. The user
    loses old chat history but the API stays up.
    """
    if path in _CONNECTIONS:
        return _CONNECTIONS[path]

    p = Path(path)
    file_pre_existed = p.exists() and p.stat().st_size > 0

    # First-open attempt. A badly corrupted file can fail at the
    # initial PRAGMA call BEFORE integrity_check ever runs — in that
    # case treat the open itself as proof of corruption.
    corrupted = False
    try:
        conn = _open_tuned(path)
        if file_pre_existed and not _verify_integrity(conn):
            corrupted = True
    except sqlite3.DatabaseError as exc:
        logger.warning(
            "Open failed for checkpoint DB at {} ({!s}); treating as corrupted",
            path,
            exc,
        )
        corrupted = True
        conn = None  # type: ignore[assignment]

    if corrupted:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        _rename_corrupted(p)
        conn = _open_tuned(path)
        # Second integrity check — should be clean (new file). If not,
        # something is very wrong; raise so the caller / startup sees it.
        if not _verify_integrity(conn):
            raise RuntimeError(
                f"Could not create a clean checkpoint DB at {path}; "
                "filesystem may be read-only or corrupted."
            )

    _CONNECTIONS[path] = conn
    return conn


def _reset_for_tests() -> None:
    """Test-only — close + forget every cached connection."""
    for conn in list(_CONNECTIONS.values()):
        try:
            conn.close()
        except Exception:
            pass
    _CONNECTIONS.clear()
