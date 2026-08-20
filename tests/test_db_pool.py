"""v0.7.18 — regression tests for the SurrealDB connection pool.

Before v0.7.18, every repo_query / repo_create opened a fresh
AsyncSurreal WebSocket + did SCRAM auth + ns/db select, then closed.
A single chat turn fanned out dozens of calls through ContextBuilder,
adding 50-200 ms of per-query handshake overhead to every LLM turn.

The pool eliminates the per-call open/close in the steady state by
keeping a small set of pre-authenticated clients (default 4). These
tests pin:
  - acquire/release semantics
  - lazy growth up to the cap
  - blocking when at cap
  - broken connections are dropped, not returned
  - DEEPER_NOTEBOOK_DB_POOL_DISABLED falls back to per-query behavior
  - close_pool() drains everything
"""

from __future__ import annotations

import asyncio
import os

import pytest

from deeper_notebook.database import repository as repo


class _FakeConn:
    """Minimal AsyncSurreal stand-in for pool tests.

    Tracks signin/use/close calls so tests can verify the pool reuses
    clients instead of re-handshaking, and so a "broken" connection
    can raise on use.
    """

    _id_counter = 0

    def __init__(self, broken_on_use: bool = False):
        type(self)._id_counter += 1
        self.id = type(self)._id_counter
        self.closed = False
        self.signin_count = 0
        self.use_count = 0
        self.query_count = 0
        self.broken_on_use = broken_on_use

    async def signin(self, _):
        self.signin_count += 1

    async def use(self, *_):
        self.use_count += 1

    async def query(self, *_, **__):
        self.query_count += 1
        if self.broken_on_use:
            raise RuntimeError("simulated dead connection")
        return []

    async def close(self):
        self.closed = True


@pytest.fixture
def fake_async_surreal(monkeypatch):
    """Replace the real AsyncSurreal client with a fake.

    The fake's id increments per construction so tests can assert
    pool reuse (same id = same client = pooled).
    """
    _FakeConn._id_counter = 0
    monkeypatch.setattr(repo, "AsyncSurreal", lambda url: _FakeConn())
    # Provide minimal env so signin/use don't blow up
    monkeypatch.setenv("SURREAL_URL", "ws://localhost:8000/rpc")
    monkeypatch.setenv("SURREAL_USER", "root")
    monkeypatch.setenv("SURREAL_PASSWORD", "root")
    monkeypatch.setenv("SURREAL_NAMESPACE", "test")
    monkeypatch.setenv("SURREAL_DATABASE", "test")
    yield


@pytest.fixture
async def fresh_pool():
    """Reset pool state before AND after each test."""
    await repo._reset_pool_for_tests()
    yield
    await repo._reset_pool_for_tests()


# ---------------------------------------------------------------------------
# _db_pool_size — env-driven cap
# ---------------------------------------------------------------------------


def test_pool_size_default_is_4(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_DB_POOL_SIZE", raising=False)
    assert repo._db_pool_size() == 4


def test_pool_size_respects_env(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_SIZE", "8")
    assert repo._db_pool_size() == 8


def test_pool_size_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_SIZE", "not-a-number")
    assert repo._db_pool_size() == 4


def test_pool_size_falls_back_outside_range(monkeypatch):
    """Below min (1) or above max (32) → default."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_SIZE", "0")
    assert repo._db_pool_size() == 4
    monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_SIZE", "100")
    assert repo._db_pool_size() == 4


# ---------------------------------------------------------------------------
# Pool reuse — the perf win we're paying for
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_is_reused_across_acquires(
    monkeypatch, fake_async_surreal, fresh_pool
):
    """Two serial acquires must return the SAME client — that's the
    whole point of pooling."""
    async with repo.db_connection() as c1:
        first_id = c1.id

    async with repo.db_connection() as c2:
        assert c2.id == first_id, (
            "Second acquire returned a new client — pool not reusing"
        )


@pytest.mark.asyncio
async def test_cancelled_query_marks_connection_broken(
    monkeypatch, fake_async_surreal, fresh_pool
):
    """v0.8.65g — asyncio.CancelledError is a BaseException (not Exception), so
    the old `except Exception` MISSED cancellation: a cancelled query (chat-
    stream client disconnect, wait_for timeout, route-handler cancel) returned
    a connection to the pool with a PENDING in-flight request, and the next
    acquirer's query collided with the stale response → KeyError(<uuid>) in the
    SurrealDB driver → the chatbot's model fetch failed and stayed broken until
    restart. A cancelled query MUST mark the connection broken so the dirty
    connection is closed + dropped, never reused.
    """
    broken_conn = None
    with pytest.raises(asyncio.CancelledError):
        async with repo.db_connection() as conn:
            broken_conn = conn
            raise asyncio.CancelledError()

    assert broken_conn is not None
    # Dirty connection must be CLOSED (broken path), not returned to the pool.
    assert broken_conn.closed is True, (
        "Cancelled-query connection was returned to the pool dirty — the bug "
        "that poisoned the next acquirer with KeyError(uuid)"
    )
    # Pool is empty (broken conn dropped, not requeued).
    assert repo._pool is not None and repo._pool.qsize() == 0
    # Next acquire gets a FRESH connection, not the poisoned one.
    async with repo.db_connection() as c2:
        assert c2.id != broken_conn.id


@pytest.mark.asyncio
async def test_pool_grows_lazily_up_to_cap(monkeypatch, fake_async_surreal, fresh_pool):
    """Concurrent acquires force new connections up to the cap."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_SIZE", "3")

    seen_ids = set()
    # Capture all three in flight at once so the pool MUST grow to 3.
    started = asyncio.Event()
    proceed = asyncio.Event()

    async def hold_a_connection():
        async with repo.db_connection() as conn:
            seen_ids.add(conn.id)
            started.set()
            await proceed.wait()

    tasks = [asyncio.create_task(hold_a_connection()) for _ in range(3)]
    # Wait for them all to hold their conns
    await asyncio.sleep(0.05)
    proceed.set()
    await asyncio.gather(*tasks)
    assert len(seen_ids) == 3, f"Expected 3 distinct clients, got {len(seen_ids)}"


@pytest.mark.asyncio
async def test_pool_blocks_at_cap(monkeypatch, fake_async_surreal, fresh_pool):
    """A 4th acquire at cap=3 must wait until someone releases."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_SIZE", "2")

    proceed = asyncio.Event()
    fourth_started = asyncio.Event()

    async def hold():
        async with repo.db_connection():
            await proceed.wait()

    async def fourth():
        async with repo.db_connection():
            fourth_started.set()

    h1 = asyncio.create_task(hold())
    h2 = asyncio.create_task(hold())
    # Let h1/h2 settle into "holding" state
    await asyncio.sleep(0.05)

    f = asyncio.create_task(fourth())
    # Should NOT have started yet
    await asyncio.sleep(0.05)
    assert not fourth_started.is_set(), "4th acquire should be blocked at cap"

    # Release h1/h2 — fourth should immediately get a connection.
    proceed.set()
    await asyncio.wait_for(f, timeout=2)
    assert fourth_started.is_set()
    await asyncio.gather(h1, h2)


# ---------------------------------------------------------------------------
# Broken-connection handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exception_in_block_marks_connection_broken(
    monkeypatch, fake_async_surreal, fresh_pool
):
    """If the wrapped block raises, the connection is dropped (closed)
    and a fresh one comes from the next acquire. Protects against
    server-side closed sockets the client doesn't know about."""
    first_id = None
    with pytest.raises(RuntimeError, match="boom"):
        async with repo.db_connection() as c:
            first_id = c.id
            raise RuntimeError("boom")

    # Next acquire must NOT reuse the broken one
    async with repo.db_connection() as c2:
        assert c2.id != first_id, (
            "Broken connection was reused — release() did not mark it broken"
        )


# ---------------------------------------------------------------------------
# Disable flag — fallback to pre-v0.7.18 behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_disabled_opens_and_closes_per_call(
    monkeypatch, fake_async_surreal, fresh_pool
):
    """DEEPER_NOTEBOOK_DB_POOL_DISABLED=1 means every acquire creates a NEW client
    and closes it on release (legacy behavior). Useful for debugging
    a pool-related regression."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_DISABLED", "1")

    async with repo.db_connection() as c1:
        first_id = c1.id
        # The connection should not be closed mid-use
        assert not c1.closed
    # After release, it should be closed (no pooling)
    assert c1.closed

    async with repo.db_connection() as c2:
        # Distinct client — no reuse
        assert c2.id != first_id


# ---------------------------------------------------------------------------
# close_pool — graceful shutdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_pool_closes_all_idle_connections(
    monkeypatch, fake_async_surreal, fresh_pool
):
    """After close_pool(), every previously-pooled client is closed
    and the pool state is reset."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_SIZE", "3")

    held: list = []
    proceed = asyncio.Event()

    async def grab_and_hold():
        async with repo.db_connection() as conn:
            held.append(conn)
            await proceed.wait()

    # Hold 3 connections simultaneously — forces the pool to grow to 3.
    tasks = [asyncio.create_task(grab_and_hold()) for _ in range(3)]
    # Let them all settle into "holding" state
    while len(held) < 3:
        await asyncio.sleep(0.01)
    # Release them — all three return to the pool idle
    proceed.set()
    await asyncio.gather(*tasks)

    assert repo._pool is not None and repo._pool.qsize() == 3
    assert repo._pool_total == 3

    await repo.close_pool()

    for c in held:
        assert c.closed, f"close_pool() left client {c.id} open"
    assert repo._pool is None
    assert repo._pool_total == 0
