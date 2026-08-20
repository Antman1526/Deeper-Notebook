"""v0.8.35d — GmailIntegration.get() single-flight guard.

Found while sweeping the codebase for the same TTL-cache anti-pattern
fixed in v0.8.35b for `_local_chat_healthy_cached`. The Gmail
singleton fetch has the SAME race: cache miss → DB query (4-8s on
cold start per the v0.7.157 ticket) → cache write. Two concurrent
callers (the comment at gmail.py:31-34 explicitly names them:
sidebar button + setup panel mounting together) both miss, both run
the query, both write — duplicate ~4-8s SurrealDB work on every
cold load.

The pre-fix code was correct sequentially but raced under concurrent
first-callers — exactly the v0.7.157 ticket's stated motivation, which
the cache fixed for SECOND callers but not for the FIRST set of
concurrent callers.

Test pattern mirrors `test_v0_8_35_health_cache_single_flight.py`:
slow-stub the query so concurrent callers reliably overlap; assert
exactly one query runs.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from deeper_notebook.domain import gmail as gmail_mod
from deeper_notebook.domain.gmail import GmailIntegration


@pytest.fixture(autouse=True)
def _reset_cache_and_lock():
    """Reset both the cache and the v0.8.35d single-flight lock so
    each test starts from a known cold state. The lock is module-
    global and would otherwise leak state across tests."""
    gmail_mod._invalidate_cache()
    # _CACHE_LOCK is lazily constructed by _get_cache_lock(); reset to
    # None so each test exercises the lazy-init path too.
    gmail_mod._CACHE_LOCK = None
    yield
    gmail_mod._invalidate_cache()
    gmail_mod._CACHE_LOCK = None


@pytest.mark.asyncio
async def test_gmail_get_single_flight_under_concurrency():
    """N concurrent cold callers must share exactly 1 SurrealDB query.

    Without the single-flight guard, both the sidebar button and the
    setup panel firing GmailIntegration.get() on simultaneous mount
    each missed the cache and each fired `repo_query` — 2 × ~4-8s of
    duplicate DB work every cold load. With the guard, the second
    caller awaits the lock, re-checks the cache, finds the leader's
    write, and returns it without re-querying.
    """
    query_call_count = [0]

    async def _slow_query(*args, **kwargs):
        query_call_count[0] += 1
        # 100ms — much longer than the lock-acquisition latency, so
        # 5 concurrent callers all reliably enter the cache-miss
        # branch before the first one completes. Without the
        # single-flight guard, all 5 race into the query path.
        await asyncio.sleep(0.1)
        return [
            {
                "client_id_enc": None,
                "client_secret_enc": None,
                "access_token_enc": None,
                "refresh_token_enc": None,
                "token_expires_at": None,
                "email_address": "user@example.com",
                "enabled": True,
                "frequency": "daily",
            }
        ]

    with patch(
        "deeper_notebook.domain.gmail.repo_query",
        new=AsyncMock(side_effect=_slow_query),
    ):
        # 5 concurrent cache-miss callers; gather joins them.
        results = await asyncio.gather(*[GmailIntegration.get() for _ in range(5)])

    # All 5 returned the same shape — sanity check.
    assert all(r.email_address == "user@example.com" for r in results)
    # Exactly ONE query ran despite 5 concurrent callers.
    assert query_call_count[0] == 1, (
        f"Expected single-flight (1 query), got {query_call_count[0]} — "
        f"concurrent cache-miss callers thundering-herded the DB"
    )


@pytest.mark.asyncio
async def test_gmail_get_single_flight_lock_does_not_serialize_cache_hits():
    """Cache-HIT callers must NOT acquire the lock — every 60s frontend
    poll would otherwise pay lock-acquisition latency for no reason
    (the cache is fresh and there's no shared state to coordinate)."""
    # Pre-populate cache with a fresh entry.
    instance = GmailIntegration(email_address="cached@example.com", enabled=True)
    gmail_mod._CACHE["value"] = instance
    import time as _time

    gmail_mod._CACHE["ts"] = _time.monotonic()

    query_called = [False]

    async def _query_should_not_run(*args, **kwargs):
        query_called[0] = True
        return []

    with patch(
        "deeper_notebook.domain.gmail.repo_query",
        new=AsyncMock(side_effect=_query_should_not_run),
    ):
        results = await asyncio.gather(*[GmailIntegration.get() for _ in range(3)])

    assert all(r.email_address == "cached@example.com" for r in results)
    assert query_called[0] is False, "Cache-hit path must not call the DB query at all"
