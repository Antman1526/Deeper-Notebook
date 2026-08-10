"""v0.8.66 (audit H6) — regression test for the connection-pool deadlock.

When the pool is at capacity, an acquirer parks on `await _pool.get()`. The ONLY
thing that used to wake it was a NON-broken release's `put_nowait(conn)`. A
BROKEN release (the multi-connection-poisoning scenario the v0.8.65g
CancelledError fix targets) closed the connection and decremented `_pool_total`
WITHOUT enqueuing anything, so the parked acquirer was never signalled even
though a creation slot was now free — an unbounded hang.

The fix enqueues a `_SLOT_FREED` sentinel on a broken release; the parked
acquirer wakes, sees the sentinel, reserves the freed slot, and creates a new
connection.

These tests reuse the `fake_async_surreal` + `fresh_pool` fixtures from
test_db_pool.py.
"""
from __future__ import annotations

import asyncio

import pytest

from deeper_notebook.database import repository as repo

# Reuse the fakes/fixtures from the sibling pool test module.
from tests.test_db_pool import (  # noqa: F401
    fake_async_surreal,
    fresh_pool,
)


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_async_surreal", "fresh_pool")
async def test_broken_release_wakes_parked_acquirer(
    monkeypatch,
):
    """cap=1: A holds the only connection; B parks at cap; A releases BROKEN.
    B must then acquire a fresh connection instead of hanging forever."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_SIZE", "1")

    a_holding = asyncio.Event()
    a_should_break = asyncio.Event()
    b_acquired = asyncio.Event()
    b_conn_id = {}

    async def task_a():
        try:
            async with repo.db_connection():
                a_holding.set()
                await a_should_break.wait()
                raise RuntimeError("boom")  # → broken release
        except RuntimeError:
            pass

    async def task_b():
        async with repo.db_connection() as conn:
            b_conn_id["id"] = conn.id
            b_acquired.set()

    a = asyncio.create_task(task_a())
    await asyncio.wait_for(a_holding.wait(), timeout=2)  # A holds the 1 slot

    b = asyncio.create_task(task_b())
    await asyncio.sleep(0.05)  # let B park at cap
    assert not b_acquired.is_set(), "B should be blocked while A holds the conn"

    # A raises → broken release → frees the slot + enqueues _SLOT_FREED.
    a_should_break.set()

    # The assertion that fails WITHOUT the fix: B hangs and this times out.
    await asyncio.wait_for(b, timeout=2)
    assert b_acquired.is_set(), "B never acquired after the broken release"
    await a

    # Pool is consistent afterwards: B's connection returned idle, no leftover
    # sentinel, total accounted.
    assert repo._pool_total == 1
    assert repo._pool is not None and repo._pool.qsize() == 1
    # And a subsequent acquire returns a REAL connection (no sentinel leak).
    async with repo.db_connection() as c3:
        assert c3.id == b_conn_id["id"]  # reused B's idle conn


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_async_surreal", "fresh_pool")
async def test_broken_release_without_waiter_leaves_no_stray_sentinel(
    monkeypatch,
):
    """A broken release with NO parked waiter must NOT leave a sentinel in the
    idle queue — the sentinel is only for waking a parked acquirer. A stray
    sentinel would corrupt qsize-based bookkeeping (close_pool, the
    broken-conn-dropped invariant). The next acquire just reserves the freed
    slot and creates a real connection."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_SIZE", "1")

    with pytest.raises(RuntimeError, match="boom"):
        async with repo.db_connection():
            raise RuntimeError("boom")

    # No waiter was parked → queue is empty (no orphan sentinel), slot freed.
    assert repo._pool is not None and repo._pool.qsize() == 0
    assert repo._pool_total == 0

    # The next acquire hands back a REAL connection, never the sentinel.
    async with repo.db_connection() as conn:
        assert conn is not repo._SLOT_FREED
        assert hasattr(conn, "query"), "acquire returned the sentinel, not a conn"
    assert repo._pool_total == 1


def test_pool_deadlock_cases_register_shared_fixtures_without_shadowing():
    """Fixture setup must stay shared instead of parameter-shadowing imports."""
    import inspect

    for name in (
        "test_broken_release_wakes_parked_acquirer",
        "test_broken_release_without_waiter_leaves_no_stray_sentinel",
    ):
        test = globals()[name]
        fixture_names = {
            fixture
            for mark in getattr(test, "pytestmark", [])
            if mark.name == "usefixtures"
            for fixture in mark.args
        }
        assert {"fake_async_surreal", "fresh_pool"} <= fixture_names
        assert not {
            "fake_async_surreal",
            "fresh_pool",
        } & inspect.signature(test).parameters.keys()
