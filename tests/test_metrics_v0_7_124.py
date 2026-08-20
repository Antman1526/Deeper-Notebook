"""v0.7.124 — tests for the Prometheus metrics surface.

Covers:
  * /metrics endpoint returns Prometheus exposition format
  * Request middleware records counter + histogram per request
  * Route label is the FastAPI route TEMPLATE not the literal URL
    (so each notebook ID doesn't blow up cardinality)
  * 5xx responses are still recorded (not lost to the exception path)
  * /metrics itself is excluded from request-timing capture
  * Slow-query counter records when DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS exceeded
  * Memory-recall fall-through counter records reason-labeled events
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.metrics import (
    db_slow_queries_total,
    http_requests_total,
    memory_recall_fallthrough_total,
)
from api.middleware.metrics import PrometheusMetricsMiddleware

# prometheus-client doesn't expose a public reset for labeled counters
# without poking at private internals, and the API differs between
# labeled (Counter._metrics dict) and unlabeled (Counter._value)
# instances. Rather than fight the library, tests use delta-based
# assertions (read value before + after + assert delta == expected).
# That style is also more representative of how dashboards consume
# the counters (rates over time, not absolutes).


def _counter_value(counter, **labels) -> float:
    """Read a labeled or unlabeled Counter's current value.
    Unlabeled counters expose ._value.get(); labeled counters store
    per-label-set children in ._metrics keyed by the label tuple."""
    if labels:
        child = counter.labels(**labels)
        return child._value.get()
    return counter._value.get()


def _slow_query_counter_value() -> float:
    return db_slow_queries_total._value.get()


@pytest.fixture()
def app_with_metrics():
    """Tiny FastAPI app with the metrics middleware + /metrics
    endpoint wired up."""
    a = FastAPI()
    a.add_middleware(PrometheusMetricsMiddleware)

    @a.get("/echo")
    def echo():
        return {"ok": True}

    @a.get("/api/notebooks/{notebook_id}")
    def get_notebook(notebook_id: str):
        return {"id": notebook_id}

    @a.get("/api/boom")
    def boom():
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="simulated")

    @a.get("/metrics")
    def metrics():
        from fastapi.responses import Response

        from api.metrics import render_prometheus

        body, content_type = render_prometheus()
        return Response(content=body, media_type=content_type)

    return a


# -------------------------------------------------------------------- #
# /metrics endpoint format
# -------------------------------------------------------------------- #


def test_metrics_endpoint_returns_prometheus_format(app_with_metrics):
    """v0.7.124 — /metrics returns text in the Prometheus exposition
    format (text/plain with a version=0.0.4 hint or similar)."""
    with TestClient(app_with_metrics) as client:
        r = client.get("/metrics")
    assert r.status_code == 200
    # Content-Type should announce Prometheus / OpenMetrics format
    ct = r.headers.get("content-type", "")
    assert "text/plain" in ct or "openmetrics" in ct
    body = r.text
    # The default process_* metrics from prometheus-client are always
    # present — quick sanity check that we wired the registry right.
    assert "# HELP" in body
    assert "# TYPE" in body


def test_request_counter_increments_per_request(app_with_metrics):
    """v0.7.124 — Each HTTP request increments onp_http_requests_total
    labeled by method + route + status_code."""
    before = _counter_value(
        http_requests_total,
        method="GET",
        route="/echo",
        status_code="200",
    )
    with TestClient(app_with_metrics) as client:
        client.get("/echo")
        client.get("/echo")
        client.get("/echo")
    after = _counter_value(
        http_requests_total,
        method="GET",
        route="/echo",
        status_code="200",
    )
    assert after - before == 3


def test_route_label_uses_template_not_literal_url(app_with_metrics):
    """v0.7.124 — Cardinality protection: /api/notebooks/{notebook_id}
    must register as ONE label, not one-per-notebook-id. Otherwise
    Prometheus storage explodes on long-running deployments."""
    before = _counter_value(
        http_requests_total,
        method="GET",
        route="/api/notebooks/{notebook_id}",
        status_code="200",
    )
    with TestClient(app_with_metrics) as client:
        client.get("/api/notebooks/abc")
        client.get("/api/notebooks/def")
        client.get("/api/notebooks/notebook:xyz123")
        r = client.get("/metrics")
    after = _counter_value(
        http_requests_total,
        method="GET",
        route="/api/notebooks/{notebook_id}",
        status_code="200",
    )
    # All three literal URLs map to the same template label
    assert after - before == 3
    # And the literal IDs do NOT create their own label series
    body = r.text
    assert 'route="/api/notebooks/abc"' not in body
    assert 'route="/api/notebooks/def"' not in body


def test_5xx_responses_are_recorded(app_with_metrics):
    """v0.7.124 — A 500-returning route must still bump the counter
    (under the 'status_code=500' label) so error rate is visible."""
    before = _counter_value(
        http_requests_total,
        method="GET",
        route="/api/boom",
        status_code="500",
    )
    with TestClient(app_with_metrics) as client:
        client.get("/api/boom")
    after = _counter_value(
        http_requests_total,
        method="GET",
        route="/api/boom",
        status_code="500",
    )
    assert after - before == 1


def test_metrics_endpoint_excluded_from_request_timing(app_with_metrics):
    """v0.7.124 — Scraping /metrics shouldn't appear as user traffic
    in dashboards. The middleware short-circuits on /metrics paths."""
    with TestClient(app_with_metrics) as client:
        # Hit /metrics twice. Neither should show up as
        # onp_http_requests_total entries.
        client.get("/metrics")
        client.get("/metrics")
        client.get("/echo")  # This one SHOULD count
        r = client.get("/metrics")
    body = r.text
    # /echo appears with count 1
    assert 'route="/echo"' in body
    # /metrics does NOT appear in onp_http_requests_total at all
    counter_lines = [
        line for line in body.splitlines() if line.startswith("onp_http_requests_total")
    ]
    assert not any('route="/metrics"' in line for line in counter_lines)


# -------------------------------------------------------------------- #
# Slow-query counter wired into repo_query
# -------------------------------------------------------------------- #


def test_slow_query_counter_increments_when_threshold_exceeded(monkeypatch):
    """v0.7.124 — repo_query bumps onp_db_slow_queries_total when a
    query exceeds DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS. Matches the v0.7.120 log
    line one-for-one."""
    from deeper_notebook.database import repository as repo

    monkeypatch.setenv("DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS", "10")

    class _FakeConn:
        async def query(self, q, vars=None):
            await asyncio.sleep(0.05)  # 50ms — exceeds 10ms threshold
            return []

    class _FakeCtx:
        async def __aenter__(self):
            return _FakeConn()

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr(repo, "db_connection", lambda: _FakeCtx())
    monkeypatch.setattr(repo, "parse_record_ids", lambda x: x)

    before = _slow_query_counter_value()
    asyncio.run(repo.repo_query("SELECT * FROM notebook"))
    after = _slow_query_counter_value()

    assert after == before + 1, (
        f"Slow-query counter didn't increment: {before} → {after}"
    )


def test_slow_query_counter_silent_under_threshold(monkeypatch):
    """v0.7.124 — Negative-space check: fast queries don't pollute
    the slow counter."""
    from deeper_notebook.database import repository as repo

    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS", "5000"
    )  # 5s — never exceeded

    class _FakeConn:
        async def query(self, q, vars=None):
            return []

    class _FakeCtx:
        async def __aenter__(self):
            return _FakeConn()

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr(repo, "db_connection", lambda: _FakeCtx())
    monkeypatch.setattr(repo, "parse_record_ids", lambda x: x)

    before = _slow_query_counter_value()
    asyncio.run(repo.repo_query("SELECT * FROM notebook"))
    after = _slow_query_counter_value()
    assert after == before


# -------------------------------------------------------------------- #
# Memory-recall fall-through counter
# -------------------------------------------------------------------- #


def test_memory_recall_embed_timeout_bumps_counter(monkeypatch):
    """v0.7.124 — When recall_relevant_memory's embed call times out,
    we bump the fall-through counter with reason='embed_timeout'.
    Operators watching the counter can see when the embedding model
    is unhealthy and chat is silently degrading."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_RECALL_EMBED_TIMEOUT_SEC", "0.1")

    class _HangingEmbed:
        async def aembed(self, texts):
            await asyncio.sleep(5)
            return [[0.0] * 768]

    async def _get_emb():
        return _HangingEmbed()

    from deeper_notebook.ai import models as ai_models

    monkeypatch.setattr(ai_models.model_manager, "get_embedding_model", _get_emb)

    from deeper_notebook.utils.memory_recall import recall_relevant_memory

    # Capture the per-label value before + after
    before = _counter_value(
        memory_recall_fallthrough_total,
        reason="embed_timeout",
    )
    asyncio.run(recall_relevant_memory("test query"))
    after = _counter_value(
        memory_recall_fallthrough_total,
        reason="embed_timeout",
    )
    assert after == before + 1


def test_memory_recall_query_timeout_bumps_counter(monkeypatch):
    """v0.7.124 — When _safe_select times out, bump counter with
    reason='query_timeout'. Separate from the embed-timeout label so
    operators can tell WHICH part of recall is broken."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_RECALL_QUERY_TIMEOUT_SEC", "0.1")

    async def _hanging_query(q, params):
        await asyncio.sleep(5)
        return []

    from deeper_notebook.utils import memory_recall

    monkeypatch.setattr(memory_recall, "repo_query", _hanging_query)

    before = _counter_value(
        memory_recall_fallthrough_total,
        reason="query_timeout",
    )
    asyncio.run(memory_recall._safe_select("SELECT 1", {}))
    after = _counter_value(
        memory_recall_fallthrough_total,
        reason="query_timeout",
    )
    assert after == before + 1
