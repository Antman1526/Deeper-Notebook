"""ONP v0.7.125 — LangGraph SQLite checkpoint pruning.

LangGraph persists chat-graph state to
`~/.deeper-notebook/data/sqlite-db/checkpoints.sqlite` via
SqliteSaver. Every chat turn appends rows to:

  * `checkpoints` — one row per saved state snapshot
  * `writes`      — one row per write event within a turn

Without pruning, both tables grow forever. A single-user install with
moderate chat use (20 turns/day) accumulates ~7300 rows/year in
`checkpoints` alone — which is fine for query performance (SQLite
handles millions of rows with the right indexes) but consumes
hundreds of MB on disk for blobs nobody ever needs again.

Strategy:
  * Per-thread retention: keep the N most recent checkpoints per
    thread_id (default 50). LangGraph only ever reads the LATEST
    checkpoint for a thread when resuming; older snapshots are
    history we never query.
  * Cascade `writes` rows to match — orphans serve no purpose.

We use a window-function-based DELETE in a single transaction so
pruning is atomic and fast even on a multi-GB checkpoint DB. SQLite
3.25+ (Python 3.7+) supports `ROW_NUMBER() OVER (PARTITION BY …)`.

The function is safe to call concurrently with LangGraph reads:
SQLite's WAL journal mode (set in
`deeper_notebook/utils/sqlite_checkpoint.py`) serializes writers but
allows concurrent readers, and our DELETE acquires a short write
lock that yields back as soon as the transaction commits.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from deeper_notebook.environment import resolve_env

# Default retention values. Tuned for the desktop-bundle's typical
# single-user usage pattern (20-50 turns/day). Operators with heavier
# usage or special requirements can override via env knobs.
_DEFAULT_KEEP_PER_THREAD = 50
_DEFAULT_PRUNE_INTERVAL_HOURS = 24


def _keep_per_thread() -> int:
    """How many recent checkpoints to retain per thread_id. Below this
    count, all checkpoints are kept; above, the oldest are pruned."""
    raw = resolve_env("DEEPER_NOTEBOOK_CHECKPOINT_KEEP_PER_THREAD", "").strip()
    if not raw:
        return _DEFAULT_KEEP_PER_THREAD
    try:
        n = int(raw)
        if n < 1:
            logger.warning(
                "DEEPER_NOTEBOOK_CHECKPOINT_KEEP_PER_THREAD={} is < 1; using default {}",
                raw,
                _DEFAULT_KEEP_PER_THREAD,
            )
            return _DEFAULT_KEEP_PER_THREAD
        return n
    except ValueError:
        logger.warning(
            "DEEPER_NOTEBOOK_CHECKPOINT_KEEP_PER_THREAD={!r} is not an integer; using default {}",
            raw,
            _DEFAULT_KEEP_PER_THREAD,
        )
        return _DEFAULT_KEEP_PER_THREAD


def prune_old_checkpoints(
    sqlite_path: str | Path,
    *,
    keep_per_thread: Optional[int] = None,
) -> dict[str, int]:
    """Delete old checkpoints + orphaned writes from the LangGraph
    SQLite store.

    Args:
        sqlite_path: Path to `checkpoints.sqlite`. If the file doesn't
            exist (fresh install, no chat history yet), returns counts
            of 0 without raising.
        keep_per_thread: Override the env-configured retention. Useful
            for testing; production code should rely on the env knob.

    Returns:
        dict with the counts (always present, may be 0):
          * `checkpoints_deleted` — rows removed from `checkpoints`
          * `writes_deleted` — rows removed from `writes`
          * `threads_seen` — distinct thread_ids found before pruning
          * `elapsed_ms` — wall-clock time taken

    Safe to call from a background task. Failures are logged + an
    empty result dict is returned so the scheduler doesn't crash.
    """
    keep = keep_per_thread if keep_per_thread is not None else _keep_per_thread()
    path = Path(sqlite_path)
    result = {
        "checkpoints_deleted": 0,
        "writes_deleted": 0,
        "threads_seen": 0,
        "elapsed_ms": 0,
    }

    if not path.exists():
        logger.debug(
            "Checkpoint prune: {} doesn't exist (no chat history yet); skipping",
            path,
        )
        return result

    start = time.monotonic()
    conn: sqlite3.Connection | None = None
    try:
        # Open with the same tuning as the rest of the codebase (WAL +
        # busy_timeout + NORMAL sync) so we play nicely with the
        # SqliteSaver's concurrent reads from chat-graph requests.
        conn = sqlite3.connect(str(path), isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")

        # Sanity-check: the tables LangGraph creates should exist
        # before we try to delete from them. On a fresh DB where the
        # SqliteSaver hasn't been initialized yet, both tables are
        # missing and we'd hit "no such table" errors.
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('checkpoints', 'writes')"
        )
        existing = {row[0] for row in cur.fetchall()}
        if "checkpoints" not in existing or "writes" not in existing:
            logger.debug(
                "Checkpoint prune: tables not yet created in {} "
                "(no chat turns recorded yet); skipping",
                path,
            )
            return result

        # Count distinct threads for the observability counter.
        cur = conn.execute("SELECT COUNT(DISTINCT thread_id) FROM checkpoints")
        result["threads_seen"] = int(cur.fetchone()[0])

        # Atomic delete in a single transaction. The window function
        # PARTITION BY thread_id ordered by checkpoint_id DESC gives
        # us each row's recency rank within its thread. Anything past
        # `keep_per_thread` is fair game.
        #
        # checkpoint_id is a uuid6/xid-style time-prefixed string in
        # LangGraph 1.0+, so lexicographic DESC == newest-first.
        conn.execute("BEGIN")
        try:
            # 1) Delete old checkpoints.
            cur = conn.execute(
                """
                DELETE FROM checkpoints
                WHERE (thread_id, checkpoint_ns, checkpoint_id) IN (
                    SELECT thread_id, checkpoint_ns, checkpoint_id FROM (
                        SELECT
                            thread_id, checkpoint_ns, checkpoint_id,
                            ROW_NUMBER() OVER (
                                PARTITION BY thread_id, checkpoint_ns
                                ORDER BY checkpoint_id DESC
                            ) AS rn
                        FROM checkpoints
                    )
                    WHERE rn > ?
                )
                """,
                (keep,),
            )
            result["checkpoints_deleted"] = cur.rowcount or 0

            # 2) Cascade: delete orphaned writes (those whose
            #    checkpoint_id no longer exists). This is the second
            #    DELETE rather than a JOIN because SQLite's
            #    DELETE...FROM syntax is more limited than Postgres's.
            cur = conn.execute(
                """
                DELETE FROM writes
                WHERE (thread_id, checkpoint_ns, checkpoint_id) NOT IN (
                    SELECT thread_id, checkpoint_ns, checkpoint_id FROM checkpoints
                )
                """,
            )
            result["writes_deleted"] = cur.rowcount or 0

            conn.execute("COMMIT")
        except Exception:
            # If anything inside the transaction failed, roll back so
            # the DB is unchanged. Caller still gets an exception log.
            conn.execute("ROLLBACK")
            raise

        # Reclaim free pages from disk. VACUUM acquires a full DB
        # lock and rewrites the file; on a multi-GB checkpoint store
        # that's expensive. Use incremental_vacuum so we only reclaim
        # what was freed by the DELETE. Safe to no-op if auto_vacuum
        # wasn't enabled.
        try:
            conn.execute("PRAGMA incremental_vacuum(1000)")
        except sqlite3.OperationalError:
            # auto_vacuum mode not set — skip silently
            pass

    except Exception as exc:
        logger.warning(
            "Checkpoint prune failed for {}: {}. Will retry on next interval.",
            path,
            exc,
        )
        return result
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        result["elapsed_ms"] = int((time.monotonic() - start) * 1000)

    if result["checkpoints_deleted"] or result["writes_deleted"]:
        logger.info(
            "Checkpoint prune: removed {} checkpoint rows + {} write rows "
            "across {} thread(s) in {}ms (keep_per_thread={})",
            result["checkpoints_deleted"],
            result["writes_deleted"],
            result["threads_seen"],
            result["elapsed_ms"],
            keep,
        )
    else:
        logger.debug(
            "Checkpoint prune: nothing to remove ({} threads under cap of {})",
            result["threads_seen"],
            keep,
        )

    # v0.7.125 — Prometheus counters. Best-effort so a metrics-import
    # failure can never break the pruning path.
    try:
        from api.metrics import (
            checkpoint_prune_rows_deleted_total,
            checkpoint_prune_runs_total,
        )

        checkpoint_prune_runs_total.inc()
        checkpoint_prune_rows_deleted_total.labels(table="checkpoints").inc(
            result["checkpoints_deleted"]
        )
        checkpoint_prune_rows_deleted_total.labels(table="writes").inc(
            result["writes_deleted"]
        )
    except Exception:
        pass

    return result


async def run_prune_loop(stop_event, *, interval_hours: Optional[float] = None) -> None:
    """Background-task loop. Prunes once on entry, then sleeps for the
    configured interval, then prunes again, repeating until the stop
    event is set.

    Mirrors the digest_scheduler's lifespan pattern (see
    `deeper_notebook/digest/scheduler.py`). Safe to cancel mid-sleep.
    """
    import asyncio

    from deeper_notebook.config import LANGGRAPH_CHECKPOINT_FILE

    if interval_hours is None:
        raw = (
            resolve_env(
                "DEEPER_NOTEBOOK_CHECKPOINT_PRUNE_INTERVAL_HOURS",
                "",
            )
            or ""
        ).strip()
        if raw:
            try:
                interval_hours = float(raw)
            except ValueError:
                interval_hours = float(_DEFAULT_PRUNE_INTERVAL_HOURS)
        else:
            interval_hours = float(_DEFAULT_PRUNE_INTERVAL_HOURS)

    interval_seconds = max(interval_hours, 0.001) * 3600

    while not stop_event.is_set():
        # Run prune in a thread so the sqlite3 calls don't block the
        # event loop. The pruning function is sync (sqlite3 driver
        # is sync); without to_thread, a multi-GB DB scan would
        # block every other concurrent HTTP request for the duration.
        try:
            await asyncio.to_thread(
                prune_old_checkpoints,
                LANGGRAPH_CHECKPOINT_FILE,
            )
        except Exception as exc:
            logger.warning("Checkpoint prune loop iteration failed: {}", exc)

        # Sleep until next interval OR until stop_event is set,
        # whichever comes first. Lets shutdown be snappy.
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            # Normal path — interval elapsed, loop again.
            continue
