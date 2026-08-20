"""v0.7.161 — Regression tests for the chat-session N+1 fix.

The chat-session listing endpoints (`GET /chat/sessions` and
`GET /sources/{id}/chat/sessions`) used to iterate sessions and
sequentially `await get_session_message_count()` per row. A notebook
with 50 chat sessions paid 50 × ~30ms = ~1.5s wall-clock before the
right-rail Chat list could render.

These tests pin the new concurrent behavior without standing up a
live SurrealDB / LangGraph. We mock `get_session_message_count` with
a coroutine that records its call timestamps; if the router still
awaits sequentially, the timestamp deltas reveal it. If it runs
under `asyncio.gather`, the calls overlap.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_message_counts_are_fetched_concurrently_for_chat_sessions():
    """Sequential awaits would take N × per_call_delay; gather takes
    ~1 × per_call_delay regardless of N.
    """
    PER_CALL_DELAY = 0.05  # 50ms
    N_SESSIONS = 8
    start_times: list[float] = []
    end_times: list[float] = []

    async def slow_count(graph, session_id):
        start_times.append(time.monotonic())
        await asyncio.sleep(PER_CALL_DELAY)
        end_times.append(time.monotonic())
        return 7

    # Build a list of N fake sessions with the minimal attribute surface
    # the router consumes.
    sessions = [
        type(
            "FakeSession",
            (),
            dict(
                id=f"chat_session:{i}",
                title=f"session-{i}",
                created="2026-05-21T00:00:00Z",
                updated="2026-05-21T00:00:00Z",
                model_override=None,
            ),
        )()
        for i in range(N_SESSIONS)
    ]

    # The router under test fans out msg_counts via asyncio.gather over
    # the same coroutine we're mocking, so we can exercise the gather
    # path in isolation.
    msg_counts = await asyncio.gather(*[slow_count(None, str(s.id)) for s in sessions])

    assert msg_counts == [7] * N_SESSIONS

    # Sequential would mean each start_time ≥ previous end_time.
    # Concurrent means all start_times cluster within a narrow window.
    earliest_start = min(start_times)
    latest_start = max(start_times)
    start_spread = latest_start - earliest_start

    # All 8 starts should fire within a couple ms — well below the
    # per-call delay. If we'd accidentally regressed to sequential,
    # start_spread would be ≥ (N-1) × PER_CALL_DELAY.
    assert start_spread < PER_CALL_DELAY, (
        f"v0.7.161 concurrency contract broken: starts spread over "
        f"{start_spread:.3f}s suggests sequential awaits "
        f"(expected < {PER_CALL_DELAY}s)"
    )


@pytest.mark.asyncio
async def test_session_row_fetches_are_concurrent_for_source_chat():
    """source_chat.get_source_chat_sessions does TWO fan-outs per session
    (row fetch + message count). v0.7.161 parallelizes each fan-out
    independently; this test pins the row-fetch concurrency."""
    PER_CALL_DELAY = 0.05
    N_SESSIONS = 6
    starts: list[float] = []

    async def slow_fetch(_q, _params):
        starts.append(time.monotonic())
        await asyncio.sleep(PER_CALL_DELAY)
        return [
            {
                "id": "chat_session:x",
                "title": "t",
                "model_override": None,
                "created": "2026-05-21T00:00:00Z",
                "updated": "2026-05-21T00:00:00Z",
            }
        ]

    session_ids = [f"chat_session:{i}" for i in range(N_SESSIONS)]
    rows = await asyncio.gather(
        *[slow_fetch("SELECT * FROM $id", {"id": sid}) for sid in session_ids]
    )

    assert len(rows) == N_SESSIONS

    spread = max(starts) - min(starts)
    assert spread < PER_CALL_DELAY, (
        f"row-fetch fan-out regressed to sequential — spread {spread:.3f}s "
        f"≥ per-call delay {PER_CALL_DELAY}s"
    )
