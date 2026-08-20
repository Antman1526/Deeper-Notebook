"""Regression coverage for bounded optional rate-limit client state."""

from __future__ import annotations

import asyncio
from collections import deque

from starlette.requests import Request


def _request(ip: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/data",
            "raw_path": b"/api/data",
            "query_string": b"",
            "headers": [],
            "client": (ip, 1234),
            "server": ("127.0.0.1", 5055),
            "scheme": "http",
        }
    )


def test_rate_limiter_evicts_inactive_clients_at_a_bounded_table_size(
    monkeypatch,
):
    """Thousands of one-shot client addresses must not grow the table forever."""
    from api.rate_limit import RateLimitMiddleware

    monkeypatch.setattr("api.rate_limit._MAX_CLIENTS", 3)
    monkeypatch.setattr("api.rate_limit._limit_per_min", lambda: 10)
    middleware = RateLimitMiddleware(None)

    async def _call_next(request):
        return object()

    async def _run():
        for index in range(20):
            await middleware.dispatch(_request(f"192.0.2.{index}"), _call_next)

    asyncio.run(_run())

    assert len(middleware._hits) <= 3


def test_rate_limiter_prunes_expired_deques_before_capacity_eviction(monkeypatch):
    """Expired keys are reclaimed even when a new address is not yet needed."""
    from api.rate_limit import RateLimitMiddleware

    monkeypatch.setattr("api.rate_limit._MAX_CLIENTS", 3)
    monkeypatch.setattr("api.rate_limit._limit_per_min", lambda: 10)
    middleware = RateLimitMiddleware(None)
    middleware._hits["192.0.2.1"] = deque([0.0])
    middleware._hits["192.0.2.2"] = deque([0.0])

    async def _call_next(request):
        return object()

    monkeypatch.setattr("api.rate_limit.time.monotonic", lambda: 120.0)
    asyncio.run(middleware.dispatch(_request("192.0.2.3"), _call_next))

    assert set(middleware._hits) == {"192.0.2.3"}


def test_rate_limiter_amortizes_full_table_pruning(monkeypatch):
    """A normal burst must not scan every client on every request."""
    from api.rate_limit import RateLimitMiddleware

    monkeypatch.setattr("api.rate_limit._MAX_CLIENTS", 100)
    monkeypatch.setattr("api.rate_limit._PRUNE_INTERVAL_SEC", 1.0, raising=False)
    monkeypatch.setattr("api.rate_limit._limit_per_min", lambda: 10)
    middleware = RateLimitMiddleware(None)

    prune_calls: list[float] = []
    original_prune = middleware._prune_clients

    def _observe_prune(cutoff, now=None):
        prune_calls.append(cutoff)
        return original_prune(cutoff) if now is None else original_prune(cutoff, now)

    monkeypatch.setattr(middleware, "_prune_clients", _observe_prune)
    monkeypatch.setattr("api.rate_limit.time.monotonic", lambda: 120.0)

    async def _call_next(request):
        return object()

    async def _run():
        for index in range(3):
            await middleware.dispatch(_request(f"192.0.2.{index}"), _call_next)

    asyncio.run(_run())

    assert len(prune_calls) == 1
