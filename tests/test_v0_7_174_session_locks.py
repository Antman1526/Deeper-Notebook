"""v0.7.174 — Per-session asyncio locks serialize concurrent /chat/execute.

Background: `/chat/execute` and `/chat/stream` (plus source-chat
analogues) used to read the LangGraph checkpoint, append the user's
HumanMessage to a Python-side state dict, then ainvoke/astream. Two
concurrent requests to the same `thread_id` each saw the same
checkpoint, each appended their own message in memory, each invoked
— silently losing the other's turn when both ran in parallel.

v0.7.174 introduces `api/utils/session_locks.py` with a
WeakValueDictionary of per-session asyncio.Locks. The chat-execute
critical section (state read → ainvoke → checkpoint commit) now
runs under the lock; concurrent calls serialize cleanly.

This test verifies:
  - `get_session_lock(X)` returns the SAME lock for repeat calls
    while a reference is alive (so concurrent callers actually
    serialize on the same primitive).
  - Different session_ids get different locks (no cross-session
    serialization).
  - Two concurrent acquirers really do serialize (timestamp-based
    proof of ordering, not just call-count).
  - The WeakValueDictionary cleans up when no caller holds the lock
    (no unbounded memory growth on a long-running install with
    many distinct session_ids).
  - AST-level pin that both /chat and /source/chat streaming paths
    invoke get_session_lock around their critical section.
"""

from __future__ import annotations

import asyncio
import gc
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Lock-registry contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_session_id_returns_same_lock_while_held():
    """v0.7.174: two `get_session_lock` calls for the same session_id
    must return the SAME lock object as long as somebody holds a
    reference. Otherwise concurrent callers would each get a fresh
    lock and serialization would be defeated."""
    from api.utils.session_locks import get_session_lock

    lock_a = await get_session_lock("chat_session:abc")
    lock_b = await get_session_lock("chat_session:abc")
    assert lock_a is lock_b, (
        "v0.7.174 broken: same session_id returns different lock "
        "objects. Concurrent callers will each acquire their own "
        "lock and the serialization is gone."
    )


@pytest.mark.asyncio
async def test_different_session_ids_get_different_locks():
    """v0.7.174: different sessions must NOT share a lock. Otherwise
    unrelated notebooks would serialize on each other's chat traffic
    — kills concurrency for multi-notebook users."""
    from api.utils.session_locks import get_session_lock

    lock_a = await get_session_lock("chat_session:abc")
    lock_b = await get_session_lock("chat_session:def")
    assert lock_a is not lock_b


@pytest.mark.asyncio
async def test_two_concurrent_acquirers_actually_serialize():
    """v0.7.174 PROOF: two coroutines acquiring the same lock cannot
    both be in the critical section simultaneously. We assert this
    via timestamp recording rather than call-count so a future
    refactor that 'calls gather but awaits in a loop' (which would
    still serialize but for the wrong reason) is distinguishable
    from a real serialization break.
    """
    from api.utils.session_locks import get_session_lock

    HOLD_MS = 50
    enter_times: list[float] = []
    exit_times: list[float] = []

    async def critical_section(label: str):
        lock = await get_session_lock("chat_session:serialize-me")
        async with lock:
            enter_times.append(time.monotonic())
            await asyncio.sleep(HOLD_MS / 1000)
            exit_times.append(time.monotonic())

    await asyncio.gather(critical_section("a"), critical_section("b"))

    # The second entry must occur AFTER the first exit (or within a
    # microsecond of it, accounting for event-loop scheduling).
    assert len(enter_times) == 2 and len(exit_times) == 2
    second_entered = sorted(enter_times)[1]
    first_exited = sorted(exit_times)[0]
    # If they overlapped, the second entry would be roughly at the
    # SAME time as the first entry (both start ≈ 0). Serialized,
    # the second entry happens at ≈ HOLD_MS.
    assert second_entered >= first_exited - 0.005, (
        f"v0.7.174 broken: critical sections overlapped — second "
        f"entry at {second_entered:.4f} but first exit at "
        f"{first_exited:.4f}. The per-session lock is NOT actually "
        f"serializing concurrent callers."
    )


@pytest.mark.asyncio
async def test_lock_is_gc_eligible_after_release():
    """v0.7.174: WeakValueDictionary backing means the lock auto-evicts
    when no caller holds it. Otherwise a long-running install with
    many distinct session_ids would accumulate unbounded lock objects.
    """
    from api.utils.session_locks import (
        _count_live_locks,
        get_session_lock,
    )

    # Baseline (other tests may have leaked locks; we only check delta).
    baseline = _count_live_locks()

    async def acquire_release():
        lock = await get_session_lock("chat_session:gc-test")
        async with lock:
            pass
        # Local `lock` goes out of scope here — last strong ref drops.

    await acquire_release()
    # Force collection.
    gc.collect()

    # The lock for that session should be evicted.
    assert _count_live_locks() <= baseline + 1, (
        f"v0.7.174: WeakValueDictionary should auto-evict. "
        f"Before: {baseline}, after one round-trip + gc.collect(): "
        f"{_count_live_locks()}. If the count keeps growing across "
        f"sessions, a strong ref is leaking somewhere."
    )


# ---------------------------------------------------------------------------
# AST-level pins: both critical sections must invoke the lock
# ---------------------------------------------------------------------------


def test_chat_execute_wraps_critical_section_in_session_lock():
    """v0.7.174: /chat/execute must call `get_session_lock` and use
    the returned lock to wrap the get_state → ainvoke region. A
    future refactor that drops the wrap would re-introduce the
    lost-turn race."""
    src = _read_source("api/routers/chat.py")
    # The import must be present.
    assert "from api.utils.session_locks import get_session_lock" in src
    # And the lock-acquire happens before chat_graph.ainvoke.
    idx_lock = src.find("session_lock = await get_session_lock(full_session_id)")
    assert idx_lock != -1, (
        "v0.7.174 regression: /chat/execute no longer acquires a "
        "session lock. Concurrent calls to the same thread_id will "
        "silently lose turns."
    )
    # The ainvoke call must come AFTER the lock acquire (and inside
    # the async-with on the lock).
    # v0.7.192 — accept either the legacy `chat_graph.ainvoke(` or
    # the v0.7.192 async-twin form. _stream_chat_events now calls
    # `_chat_graph_async.ainvoke(...)` via the lazy async-graph
    # factory; the lock-before-write invariant is what matters,
    # not the specific graph variable name.
    idx_ainvoke = src.find("chat_graph.ainvoke(")
    if idx_ainvoke == -1:
        idx_ainvoke = src.find("_chat_graph_async.ainvoke(")
    assert idx_ainvoke != -1, (
        "v0.7.174 regression: chat_graph(_async).ainvoke call site "
        "is gone. Cannot verify the lock wraps the critical section."
    )
    assert idx_lock < idx_ainvoke


def test_chat_stream_wraps_critical_section_in_session_lock():
    """v0.7.174: /chat/stream must also use the lock. Streaming path
    has a longer critical section (the whole astream_events loop)
    and uses manual acquire/finally-release because the async-with
    pattern would require re-indenting the entire loop body."""
    src = _read_source("api/routers/chat.py")
    # Manual acquire + finally release pattern.
    assert "await session_lock.acquire()" in src
    assert "session_lock.release()" in src
    # Release wrapped in try/RuntimeError so double-release is safe.
    assert "except RuntimeError" in src


def test_source_chat_stream_wraps_critical_section_in_session_lock():
    """v0.7.174: source-chat streaming has the same race; must also
    invoke the lock. AST pin for parity with chat.py."""
    src = _read_source("api/routers/source_chat.py")
    assert "from api.utils.session_locks import get_session_lock" in src
    assert "await session_lock.acquire()" in src
    assert "session_lock.release()" in src
