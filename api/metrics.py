"""ONP v0.7.124 — Prometheus metrics surface.

Gives operators visibility into the RED-method classics (Rate / Errors
/ Duration) plus the open-notebook-specific signals that the
v0.7.88-v0.7.123 timeout-coverage cycle made interesting:

  * HTTP request counter + latency histogram (by route + method + status)
  * Database query latency histogram + slow-query counter (matches
    v0.7.120's `ONP_SLOW_QUERY_LOG_MS` threshold log line)
  * Memory-recall fall-through counter (v0.7.113 / v0.7.114 — counts
    times the chat-hot-path recall hit a timeout and returned empty)

Exposed at `/metrics` in standard Prometheus exposition format. The
endpoint is auth-exempt (operators / Prometheus scrapers / dashboards
poll it without credentials) and excluded from `RequestIDMiddleware`'s
log noise via short-circuit.

All counters use the canonical `_total` suffix per Prometheus naming
conventions; histograms use buckets sized for the typical p99 range
of each operation type.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Histogram,
    generate_latest,
)

# -------------------------------------------------------------------- #
# HTTP request metrics (set by the per-request middleware below)
# -------------------------------------------------------------------- #

http_requests_total = Counter(
    "onp_http_requests_total",
    "Total HTTP requests handled by the API.",
    ["method", "route", "status_code"],
)

# Buckets cover the realistic API latency range:
# 5ms (cache hit) → 30s (slow LLM). The 0.005-second floor captures
# fast healthcheck paths; the 30-second ceiling catches the
# almost-timed-out 504s.
http_request_duration_seconds = Histogram(
    "onp_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)


# -------------------------------------------------------------------- #
# Database query metrics (called from repository.repo_query)
# -------------------------------------------------------------------- #

db_query_duration_seconds = Histogram(
    "onp_db_query_duration_seconds",
    "SurrealQL query latency in seconds.",
    # Buckets tuned for SurrealDB: most queries 1-50ms; the long tail
    # is vector-search (50-500ms) and the occasional pool-acquire
    # delay or migration (1-5s).
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

db_slow_queries_total = Counter(
    "onp_db_slow_queries_total",
    "Number of SurrealQL queries that exceeded "
    "ONP_SLOW_QUERY_LOG_MS (default 500ms).",
)


# -------------------------------------------------------------------- #
# Memory recall metrics (called from memory_recall)
# -------------------------------------------------------------------- #

memory_recall_fallthrough_total = Counter(
    "onp_memory_recall_fallthrough_total",
    "Number of times chat-hot-path memory recall hit a timeout or "
    "error and fell through to empty (v0.7.113 / v0.7.114 paths).",
    ["reason"],   # 'embed_timeout' | 'embed_error' | 'query_timeout' | 'query_error'
)

memory_recall_seconds = Histogram(
    "onp_memory_recall_duration_seconds",
    "Total memory-recall duration (embed + DB queries) per chat turn.",
    # Most calls 5-200ms; cap at the ~15s worst-case ceiling (1 embed
    # at 5s + 2 queries at 5s each).
    buckets=(0.005, 0.025, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0),
)


# -------------------------------------------------------------------- #
# Helpers
# -------------------------------------------------------------------- #


def render_prometheus() -> tuple[bytes, str]:
    """Render the current registry to Prometheus exposition format.
    Returns (body_bytes, content_type) so the FastAPI handler can
    return both. Always reads from the global REGISTRY (one process,
    one set of metrics)."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


@contextmanager
def time_db_query():
    """Context manager that observes the elapsed time into the DB
    query histogram. Used inside repo_query to record EVERY query
    (slow or fast) — slow ones additionally increment
    `db_slow_queries_total`."""
    start = time.monotonic()
    try:
        yield
    finally:
        db_query_duration_seconds.observe(time.monotonic() - start)


@contextmanager
def time_memory_recall():
    """Context manager for memory-recall total duration."""
    start = time.monotonic()
    try:
        yield
    finally:
        memory_recall_seconds.observe(time.monotonic() - start)


def record_slow_query() -> None:
    """Called by repo_query when a query exceeded ONP_SLOW_QUERY_LOG_MS.
    Wrapper exists so call sites don't have to import the Counter
    directly (keeps the boundary clean for refactor)."""
    db_slow_queries_total.inc()


def record_memory_fallthrough(reason: str) -> None:
    """Bumps the memory-recall fall-through counter with a labeled
    reason. Reasons: 'embed_timeout', 'embed_error', 'query_timeout',
    'query_error'."""
    memory_recall_fallthrough_total.labels(reason=reason).inc()
