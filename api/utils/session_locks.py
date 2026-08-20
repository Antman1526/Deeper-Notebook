"""v0.7.174 — Per-session asyncio locks for chat-execute serialization.

Background: `/chat/execute` and `/chat/stream` (plus their source-chat
analogues) follow this pattern:

    current_state = await asyncio.to_thread(chat_graph.get_state, ...)
    state_values["messages"].append(HumanMessage(...))
    result = await chat_graph.ainvoke(state_values, ...)

Two concurrent requests to the SAME `thread_id` (different tabs, an
SSE reconnect racing a fresh POST, an automated client retry) each
hit `get_state` independently, each append their own HumanMessage in
process memory, each invoke the graph. With the `add_messages`
reducer the LangGraph checkpoint does append both new messages —
but each ainvoke's INPUT state is missing the other's user-turn, so:

  - the LLM in request B never sees request A's question
  - the saved checkpoint may end up missing one of the AIMessages
    depending on the commit interleave

This module serializes per-session execution so a notebook with two
open tabs (or an aggressive client) can't lose turns.

## Design

`get_session_lock(session_id) -> asyncio.Lock` returns a singleton
per session_id. Backed by a `WeakValueDictionary` so locks GC
naturally when no caller holds them — no manual cleanup, no
unbounded memory growth on a long-running install with many
session_ids over the API's lifetime.

The weakref pattern is correct here because:

  - While a caller holds the lock (async-with), the local
    reference keeps it alive.
  - A concurrent caller's `get_session_lock` lookup hits the
    SAME live lock object.
  - Once both callers release, the lock has no strong refs and
    gets GC'd — a future call for the same session_id gets a
    fresh lock, which is semantically identical (no contention
    if nobody's currently executing).

## Why not a global lock?

Global lock serializes ALL chat traffic — kills concurrency for
users running multiple notebooks. The race is per-session, so the
lock is per-session.

## Why not `redis-lock` / SurrealDB advisory locks?

The Plus desktop fork is single-process (the launcher's
uvicorn + worker share the launcher's process tree). Cross-
process locking would be overkill. If a future deployment ever
runs multiple API replicas behind a load balancer, the
serialization will need to move to a shared store — file a
follow-up at that point.
"""

from __future__ import annotations

import asyncio
import weakref

# WeakValueDictionary: keys are str (session_id), values are
# asyncio.Lock. When a Lock has no strong refs, the entry
# auto-evicts. This is the correct memory model for "the lock
# exists iff somebody's currently executing in that session".
_session_locks: "weakref.WeakValueDictionary[str, asyncio.Lock]" = (
    weakref.WeakValueDictionary()
)

# Guards `_session_locks` itself during the get-or-create operation.
# Without this, two callers entering get_session_lock simultaneously
# for a never-before-seen session could both create their OWN lock
# objects — defeating the whole serialization. asyncio.Lock at the
# module level is fine: this Python interpreter only ever has one
# event loop in our deployment, so the lock is event-loop-scoped.
_registry_lock = asyncio.Lock()


async def get_session_lock(session_id: str) -> asyncio.Lock:
    """Return the asyncio.Lock for `session_id`, creating it on
    first call. Subsequent calls during the lifetime of any holder
    return the SAME lock so concurrent callers actually serialize.

    Usage:

        lock = await get_session_lock(full_session_id)
        async with lock:
            # state-read + ainvoke critical section
            ...

    Callers must hold a STRONG reference to the returned lock for
    the duration of the critical section (the `async with` does
    this implicitly; the WeakValueDictionary entry survives only
    as long as that strong ref exists).
    """
    async with _registry_lock:
        lock = _session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            _session_locks[session_id] = lock
        return lock


def _count_live_locks() -> int:
    """Diagnostic: how many session locks are currently alive in the
    registry. Useful in tests to verify the WeakValueDictionary is
    GC'ing properly. Not for production code paths."""
    return len(_session_locks)
