"""ONP v0.7.124 — Prometheus request-timing middleware.

Captures every HTTP request's method + route + status + duration into
the `onp_http_requests_total` counter and `onp_http_request_duration_
seconds` histogram. The metrics module owns the metric definitions
(see api/metrics.py); this module only wires them into Starlette's
middleware chain.

Routing label: We use the FastAPI ROUTE PATH (e.g.
`/api/notebooks/{notebook_id}/export`) rather than the literal URL
(e.g. `/api/notebooks/notebook:abc123/export`). Otherwise every
notebook id creates a new cardinality bucket and Prometheus
storage explodes. We extract the route via `request.scope.get(
'route').path` when the route is found; for unmatched paths (404s)
we fall back to a single `__not_found__` label so unmatched URLs
don't blow up cardinality either.

The /metrics endpoint itself is excluded from timing capture — we
don't want Prometheus's own scrape to appear as request traffic.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from api.metrics import http_request_duration_seconds, http_requests_total

# Paths excluded from request-timing capture. Scraping /metrics
# shouldn't appear as user traffic in dashboards.
_EXCLUDED_PATHS = ("/metrics",)


def _route_label(request: Request) -> str:
    """Resolve the FastAPI route path for the current request.

    FastAPI populates `request.scope['route']` after route matching;
    the `.path` attribute is the parameterized template (e.g.
    `/api/notebooks/{notebook_id}`). For unmatched paths (404 from a
    typo / probe), we collapse to a single label to prevent unbounded
    cardinality.
    """
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return route.path
    # Unmatched path or middleware running before route resolution.
    return "__not_found__"


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Capture per-request method + route + status + duration into
    Prometheus counter + histogram."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Skip /metrics scrapes so Prometheus's own polling doesn't
        # show up as request traffic.
        if any(path.startswith(p) for p in _EXCLUDED_PATHS):
            return await call_next(request)

        start = time.monotonic()
        method = request.method
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            # An unhandled exception will be turned into a 500 by
            # FastAPI's exception handlers, but those handlers run
            # AFTER this middleware returns. Record 500 here so the
            # counter still increments. The exception re-raises so
            # FastAPI's handler chain still runs.
            status_code = 500
            elapsed = time.monotonic() - start
            route_label = _route_label(request)
            http_requests_total.labels(
                method=method,
                route=route_label,
                status_code=str(status_code),
            ).inc()
            http_request_duration_seconds.labels(
                method=method,
                route=route_label,
            ).observe(elapsed)
            raise

        elapsed = time.monotonic() - start
        route_label = _route_label(request)
        http_requests_total.labels(
            method=method,
            route=route_label,
            status_code=str(status_code),
        ).inc()
        http_request_duration_seconds.labels(
            method=method,
            route=route_label,
        ).observe(elapsed)
        return response
