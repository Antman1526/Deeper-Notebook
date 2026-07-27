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
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from deeper_notebook.environment import resolve_env

# Liveness/metrics probes must never be rate-limited (orchestrators poll them).
_EXEMPT_PREFIXES = (
    "/health", "/livez", "/readyz", "/metrics", "/api/healthz",
    "/api/version", "/api/config",
)
_WINDOW_SEC = 60.0


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
        self._hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        limit = _limit_per_min()
        if limit <= 0:
            return await call_next(request)  # disabled — zero overhead path

        path = request.url.path
        if request.method == "OPTIONS" or path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        dq = self._hits[ip]
        cutoff = now - _WINDOW_SEC
        while dq and dq[0] < cutoff:
            dq.popleft()

        if len(dq) >= limit:
            retry = max(1, int(_WINDOW_SEC - (now - dq[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": str(retry)},
            )

        dq.append(now)
        # Bound memory: drop emptied per-IP deques once the table gets large.
        if len(self._hits) > 4096:
            for k in [k for k, v in self._hits.items() if not v]:
                self._hits.pop(k, None)
        return await call_next(request)
