"""v0.8.66 (audit S-4) — lightweight, env-gated in-memory rate limiter.

DEFAULT OFF (`DEEPER_NOTEBOOK_RATE_LIMIT_PER_MIN` unset / 0) so the single-user, local-first
desktop experience (127.0.0.1, one user) is completely unchanged. Set
`DEEPER_NOTEBOOK_RATE_LIMIT_PER_MIN=N` to cap requests per client IP per 60s window on the
exposed / Docker / multi-user path the audit flags — closing the
auth-brute-force and download/discover cost-amplification gaps (the
`RateLimitError` + 429 handler already existed; nothing raised it).

Sliding window, per-IP, in-memory, zero new dependencies.
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from deeper_notebook.environment import resolve_env

# Liveness/metrics probes must never be rate-limited (orchestrators poll them).
_EXEMPT_PREFIXES = (
    "/health",
    "/livez",
    "/readyz",
    "/metrics",
    "/api/healthz",
    "/api/version",
    "/api/config",
)
_WINDOW_SEC = 60.0
# Full-table cleanup is intentionally amortized.  The current client's deque
# is still cleaned on every request, while the O(table-size) sweep runs at most
# once per interval (or when a new client arrives at capacity).
_PRUNE_INTERVAL_SEC = 1.0
# The limiter is opt-in, but an exposed process must still tolerate a stream
# of one-shot source addresses.  Keep the in-memory client table finite even
# when no client sends a second request that would otherwise trigger cleanup.
_MAX_CLIENTS = 4096


def _limit_per_min() -> int:
    """Requests/IP/minute. 0 (default) disables the limiter entirely."""
    raw = (resolve_env("DEEPER_NOTEBOOK_RATE_LIMIT_PER_MIN") or "").strip()
    if not raw:
        return 0
    try:
        val = int(raw)
    except ValueError:
        return 0
    return val if val > 0 else 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # OrderedDict gives us a small LRU eviction policy when a new client
        # arrives at capacity while retaining the existing mapping-like test
        # and diagnostic surface.
        self._hits: OrderedDict[str, deque] = OrderedDict()
        self._last_prune_at = float("-inf")

    def _prune_clients(self, cutoff: float, now: float | None = None) -> None:
        """Drop clients whose whole sliding window has expired."""
        for key, dq in list(self._hits.items()):
            while dq and dq[0] < cutoff:
                dq.popleft()
            if not dq:
                self._hits.pop(key, None)
        self._last_prune_at = time.monotonic() if now is None else now

    def _client_hits(self, ip: str, cutoff: float, now: float | None = None) -> deque:
        if now is None:
            now = time.monotonic()
        # A full sweep is not needed to serve an existing client.  If a new
        # client arrives while at capacity, sweep first so expired entries can
        # be reclaimed before LRU eviction; otherwise retain the bounded table
        # and defer the sweep until the cadence elapses.
        if now - self._last_prune_at >= _PRUNE_INTERVAL_SEC or (
            ip not in self._hits and len(self._hits) >= _MAX_CLIENTS
        ):
            self._prune_clients(cutoff, now)
        dq = self._hits.get(ip)
        if dq is None:
            while len(self._hits) >= _MAX_CLIENTS:
                self._hits.popitem(last=False)
            dq = deque()
            self._hits[ip] = dq
        else:
            # Requests from an existing client make it the newest eviction
            # candidate; this does not alter the response/rate-limit shape.
            self._hits.move_to_end(ip)
        while dq and dq[0] < cutoff:
            dq.popleft()
        return dq

    async def dispatch(self, request: Request, call_next):
        limit = _limit_per_min()
        if limit <= 0:
            return await call_next(request)  # disabled — zero overhead path

        path = request.url.path
        if request.method == "OPTIONS" or path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - _WINDOW_SEC
        dq = self._client_hits(ip, cutoff, now)

        if len(dq) >= limit:
            retry = max(1, int(_WINDOW_SEC - (now - dq[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": str(retry)},
            )

        dq.append(now)
        return await call_next(request)
