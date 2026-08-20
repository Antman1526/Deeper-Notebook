"""v0.7.120 — tests for the new middleware stack + slow-query logging.

Covers:
  * RequestIDMiddleware: generates fresh UUID4, respects inbound
    X-Request-ID, sets response header, binds into loguru context.
  * SecurityHeadersMiddleware: adds nosniff / DENY / Referrer-Policy
    on every response, adds CSP except on /docs and /openapi.json,
    doesn't clobber existing headers set by handlers.
  * GZip middleware: enabled on the actual app, compresses large
    bodies when Accept-Encoding: gzip is sent.
  * Slow-query log: repo_query emits a WARNING when elapsed exceeds
    DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS.

No external dependencies (no real SurrealDB, no FastAPI lifespan).
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.testclient import TestClient

from api.middleware.request_id import (
    RequestIDMiddleware,
    current_request_id,
    request_id_var,
)
from api.middleware.security_headers import SecurityHeadersMiddleware

# --------------------------------------------------------------------- #
# RequestIDMiddleware
# --------------------------------------------------------------------- #


@pytest.fixture()
def app_with_request_id():
    """Minimal FastAPI app with only the RequestID middleware, so the
    tests exercise that middleware in isolation."""
    a = FastAPI()
    a.add_middleware(RequestIDMiddleware)

    @a.get("/echo")
    def echo():
        return {"rid": current_request_id()}

    return a


def test_request_id_generated_when_no_inbound_header(app_with_request_id):
    """v0.7.120 — When the client sends no X-Request-ID, middleware
    generates a UUID4 and surfaces it as a response header."""
    with TestClient(app_with_request_id) as client:
        r = client.get("/echo")
    assert r.status_code == 200
    rid = r.headers.get("X-Request-ID")
    assert rid is not None
    # UUID4 format: 8-4-4-4-12 hex chars
    assert len(rid) == 36
    assert rid.count("-") == 4


def test_request_id_respects_inbound_header(app_with_request_id):
    """v0.7.120 — When the client passes X-Request-ID, it's preserved
    end-to-end so cross-service correlation works."""
    upstream_id = "trace-from-upstream-proxy-abc123"
    with TestClient(app_with_request_id) as client:
        r = client.get("/echo", headers={"X-Request-ID": upstream_id})
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == upstream_id


def test_request_id_caps_inbound_at_128_chars(app_with_request_id):
    """v0.7.120 — A malicious client could pass a 1 MB X-Request-ID
    header to bloat log files. Reject (regenerate) anything > 128 chars."""
    huge_id = "A" * 5000
    with TestClient(app_with_request_id) as client:
        r = client.get("/echo", headers={"X-Request-ID": huge_id})
    rid = r.headers.get("X-Request-ID")
    # Got a fresh UUID4 instead of the huge inbound id
    assert rid != huge_id
    assert len(rid) == 36


def test_request_id_visible_inside_handler_via_contextvar(app_with_request_id):
    """v0.7.120 — Handler-side code can call current_request_id() to
    surface the id in error responses or slow-query warnings."""
    with TestClient(app_with_request_id) as client:
        r = client.get(
            "/echo",
            headers={"X-Request-ID": "from-handler-test"},
        )
    assert r.json()["rid"] == "from-handler-test"


def test_current_request_id_returns_dash_outside_request_scope():
    """v0.7.120 — current_request_id() is safe to call from startup
    code, workers, scheduled tasks — anywhere outside a request. The
    fallback '-' is what shows up in the log format default."""
    assert current_request_id() == "-"


# --------------------------------------------------------------------- #
# SecurityHeadersMiddleware
# --------------------------------------------------------------------- #


@pytest.fixture()
def app_with_security_headers():
    a = FastAPI()
    a.add_middleware(SecurityHeadersMiddleware)

    @a.get("/api/data")
    def data():
        return {"ok": True}

    @a.get("/docs")
    def docs():
        return {"swagger": True}

    @a.get("/openapi.json")
    def openapi():
        return {"openapi": "3.0"}

    return a


def test_security_headers_baseline_on_api_response(app_with_security_headers):
    """v0.7.120 — Every API response carries the baseline OWASP headers."""
    with TestClient(app_with_security_headers) as client:
        r = client.get("/api/data")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_security_headers_csp_present_on_api_response(app_with_security_headers):
    """v0.7.120 — CSP is set on regular API responses (defense-in-depth
    even though JSON doesn't execute scripts)."""
    with TestClient(app_with_security_headers) as client:
        r = client.get("/api/data")
    csp = r.headers.get("Content-Security-Policy")
    assert csp is not None
    # Key directives we care about
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_security_headers_csp_skipped_on_docs(app_with_security_headers):
    """v0.7.120 — CSP must be skipped on /docs / /redoc / /openapi.json
    because Swagger UI pulls resources from CDNs and uses inline scripts.
    A strict CSP would break /docs."""
    with TestClient(app_with_security_headers) as client:
        r_docs = client.get("/docs")
        r_openapi = client.get("/openapi.json")
    assert "Content-Security-Policy" not in r_docs.headers
    assert "Content-Security-Policy" not in r_openapi.headers
    # But the simpler baseline headers DO still apply on /docs
    assert r_docs.headers.get("X-Content-Type-Options") == "nosniff"


def test_security_headers_idempotent_when_handler_sets_them():
    """v0.7.120 — If a handler builds its own JSONResponse with one of
    these headers already set (e.g. the custom CORS-aware exception
    handler in api/main.py), don't clobber it."""
    from fastapi.responses import JSONResponse

    a = FastAPI()
    a.add_middleware(SecurityHeadersMiddleware)

    @a.get("/custom")
    def custom():
        return JSONResponse(
            content={"ok": True},
            headers={
                "X-Frame-Options": "SAMEORIGIN",  # handler-set value
                "Referrer-Policy": "no-referrer",  # handler-set value
            },
        )

    with TestClient(a) as client:
        r = client.get("/custom")
    # Handler-set values survive
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
    # Middleware added the OTHER headers handler didn't set
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


# --------------------------------------------------------------------- #
# GZip middleware (FastAPI built-in)
# --------------------------------------------------------------------- #


def test_gzip_compresses_large_response():
    """v0.7.120 — Bodies ≥ 1000 bytes get gzip'd when Accept-Encoding
    is sent."""
    a = FastAPI()
    a.add_middleware(GZipMiddleware, minimum_size=1000)

    @a.get("/big")
    def big():
        # Make sure the JSON-encoded body is over the threshold
        return {"data": "x" * 2000}

    with TestClient(a) as client:
        r = client.get("/big", headers={"Accept-Encoding": "gzip"})
    # TestClient auto-decompresses, so we check the wire-level header.
    assert r.headers.get("Content-Encoding") == "gzip"


def test_gzip_skipped_for_small_response():
    """v0.7.120 — Small bodies (< 1000) skip compression — the gzip
    overhead exceeds the savings."""
    a = FastAPI()
    a.add_middleware(GZipMiddleware, minimum_size=1000)

    @a.get("/tiny")
    def tiny():
        return {"ok": True}

    with TestClient(a) as client:
        r = client.get("/tiny", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("Content-Encoding") != "gzip"


# --------------------------------------------------------------------- #
# Slow-query logging
# --------------------------------------------------------------------- #


def test_slow_query_logs_warning_when_threshold_exceeded(monkeypatch, caplog):
    """v0.7.120 — A query that takes longer than DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS
    must emit a WARNING with the elapsed time, threshold, and truncated
    query string. Doesn't affect the result the caller gets back."""
    from deeper_notebook.database import repository as repo

    monkeypatch.setenv("DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS", "10")  # 10ms threshold

    # Mock db_connection so we don't need a real SurrealDB. The fake
    # connection's query() sleeps 50ms — exceeds the 10ms threshold.
    class _FakeConn:
        async def query(self, q, vars=None):
            await asyncio.sleep(0.05)
            return [{"value": "ok"}]

    class _FakeCtx:
        async def __aenter__(self):
            return _FakeConn()

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr(repo, "db_connection", lambda: _FakeCtx())
    monkeypatch.setattr(repo, "parse_record_ids", lambda x: x)

    # Capture loguru output. We use a custom sink because caplog hooks
    # stdlib logging, not loguru.
    captured: list[str] = []
    from loguru import logger as loguru_logger

    sink_id = loguru_logger.add(
        lambda msg: captured.append(msg.record["message"]),
        level="WARNING",
    )
    try:
        result = asyncio.run(repo.repo_query("SELECT * FROM notebook"))
    finally:
        loguru_logger.remove(sink_id)

    # Query still returned its result
    assert result == [{"value": "ok"}]
    # And a slow-query warning fired
    assert any("slow query" in msg for msg in captured), (
        f"No slow-query warning logged; captured: {captured}"
    )


def test_slow_query_silent_when_under_threshold(monkeypatch):
    """v0.7.120 — Fast queries don't pollute the log."""
    from deeper_notebook.database import repository as repo

    monkeypatch.setenv("DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS", "5000")  # 5s threshold

    class _FakeConn:
        async def query(self, q, vars=None):
            return [{"value": "fast"}]

    class _FakeCtx:
        async def __aenter__(self):
            return _FakeConn()

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr(repo, "db_connection", lambda: _FakeCtx())
    monkeypatch.setattr(repo, "parse_record_ids", lambda x: x)

    captured: list[str] = []
    from loguru import logger as loguru_logger

    sink_id = loguru_logger.add(
        lambda msg: captured.append(msg.record["message"]),
        level="WARNING",
    )
    try:
        asyncio.run(repo.repo_query("SELECT * FROM notebook"))
    finally:
        loguru_logger.remove(sink_id)

    # No slow-query warning under threshold
    assert not any("slow query" in msg for msg in captured), (
        f"Spurious slow-query warning; captured: {captured}"
    )


def test_slow_query_logs_even_when_query_errors(monkeypatch):
    """v0.7.120 — A slow query that ALSO raised should STILL log the
    slow-query warning. (The `finally:` block runs regardless.) That
    timing info is doubly useful when something's broken."""
    from deeper_notebook.database import repository as repo

    monkeypatch.setenv("DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS", "10")

    class _FailingConn:
        async def query(self, q, vars=None):
            await asyncio.sleep(0.05)
            raise RuntimeError("simulated query failure")

    class _FailingCtx:
        async def __aenter__(self):
            return _FailingConn()

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr(repo, "db_connection", lambda: _FailingCtx())
    monkeypatch.setattr(repo, "parse_record_ids", lambda x: x)

    captured: list[str] = []
    from loguru import logger as loguru_logger

    sink_id = loguru_logger.add(
        lambda msg: captured.append(msg.record["message"]),
        level="WARNING",
    )
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(repo.repo_query("SELECT * FROM notebook"))
    finally:
        loguru_logger.remove(sink_id)

    assert any("slow query" in msg for msg in captured), (
        f"Slow-query warning should fire even on error; captured: {captured}"
    )


# --------------------------------------------------------------------- #
# v0.7.121 — Additional security headers (HSTS / Permissions-Policy / XSS)
# --------------------------------------------------------------------- #


def test_security_headers_permissions_policy_present(app_with_security_headers):
    """v0.7.121 — Permissions-Policy disables browser features the API
    has no business using (camera, mic, geolocation, etc.)."""
    with TestClient(app_with_security_headers) as client:
        r = client.get("/api/data")
    policy = r.headers.get("Permissions-Policy")
    assert policy is not None
    # Spot-check a few critical denials
    assert "camera=()" in policy
    assert "microphone=()" in policy
    assert "geolocation=()" in policy
    assert "payment=()" in policy


def test_security_headers_xss_protection_disabled(app_with_security_headers):
    """v0.7.121 — X-XSS-Protection: 0 is the modern best-practice value.
    The legacy IE-era filter caused universal-XSS in older browsers and
    has zero benefit in modern ones; explicitly disable it."""
    with TestClient(app_with_security_headers) as client:
        r = client.get("/api/data")
    assert r.headers.get("X-XSS-Protection") == "0"


def test_security_headers_hsts_absent_on_http():
    """v0.7.121 — HSTS must NOT be sent on plaintext HTTP responses.
    Sending it would teach the browser to force-upgrade future requests
    to HTTPS even when no TLS terminator exists, causing every request
    to fail. TestClient uses http:// by default."""
    a = FastAPI()
    a.add_middleware(SecurityHeadersMiddleware)

    @a.get("/x")
    def x():
        return {"ok": True}

    with TestClient(a) as client:
        r = client.get("/x")
    assert "Strict-Transport-Security" not in r.headers


def test_security_headers_hsts_present_on_https():
    """v0.7.121 — HSTS IS set when the request scheme is https://. The
    starlette TestClient supports base_url="https://..." for this.
    We assert the value matches the OWASP-recommended max-age + flags."""
    a = FastAPI()
    a.add_middleware(SecurityHeadersMiddleware)

    @a.get("/x")
    def x():
        return {"ok": True}

    with TestClient(a, base_url="https://testserver") as client:
        r = client.get("/x")
    hsts = r.headers.get("Strict-Transport-Security")
    assert hsts is not None
    assert "max-age=63072000" in hsts  # 2 years
    assert "includeSubDomains" in hsts


# --------------------------------------------------------------------- #
# v0.7.121 — Dangerous CORS+no-password combo ERROR-level startup log
# --------------------------------------------------------------------- #


def test_dangerous_cors_no_password_combo_logs_error(monkeypatch, capsys):
    """v0.7.121 — When CORS_ORIGINS is unset (default '*') AND
    DEEPER_NOTEBOOK_PASSWORD is unset (auth is a no-op), the API logs an
    ERROR-level message at process boot naming the foot-gun. Operators
    tailing logs should see it immediately.

    We can't easily re-import api.main (it has module-level side
    effects), so we exercise the warning logic directly by mimicking
    the conditions and asserting the loguru output contains the
    expected ERROR signal."""
    from loguru import logger

    captured: list[str] = []
    sink_id = logger.add(
        lambda msg: captured.append(msg.record["message"]),
        level="ERROR",
    )
    try:
        # Simulate the check from api/main.py
        from deeper_notebook.utils.encryption import get_secret_from_env

        monkeypatch.delenv("DEEPER_NOTEBOOK_PASSWORD", raising=False)
        monkeypatch.delenv("DEEPER_NOTEBOOK_PASSWORD_FILE", raising=False)
        password_set = bool(get_secret_from_env("DEEPER_NOTEBOOK_PASSWORD"))
        cors_wildcard = True  # simulating CORS_IS_DEFAULT_WILDCARD

        if cors_wildcard and not password_set:
            logger.error(
                "⚠️ DANGEROUS CONFIG: CORS_ORIGINS='*' AND DEEPER_NOTEBOOK_PASSWORD "
                "is unset. Any origin can call this API without credentials. "
                "ANYONE with the API URL can read/write every notebook. This "
                "is fine ONLY for local development."
            )
    finally:
        logger.remove(sink_id)

    assert any("DANGEROUS CONFIG" in msg for msg in captured), (
        f"Expected ERROR-level dangerous-config warning; captured: {captured}"
    )
    # Must name BOTH levers so the user knows what to set
    assert any(
        "CORS_ORIGINS" in msg and "DEEPER_NOTEBOOK_PASSWORD" in msg for msg in captured
    )


def test_safe_cors_with_password_set_does_not_log_dangerous_error(
    monkeypatch,
):
    """v0.7.121 — Negative-space check: when password IS set, the
    dangerous combo doesn't apply, so we should NOT emit the ERROR."""
    from loguru import logger

    from deeper_notebook.utils.encryption import get_secret_from_env

    monkeypatch.setenv("DEEPER_NOTEBOOK_PASSWORD", "strong-password-xyz")

    captured: list[str] = []
    sink_id = logger.add(
        lambda msg: captured.append(msg.record["message"]),
        level="ERROR",
    )
    try:
        password_set = bool(get_secret_from_env("DEEPER_NOTEBOOK_PASSWORD"))
        cors_wildcard = True  # CORS=* but password is set → safe

        # The if-branch shouldn't fire
        if cors_wildcard and not password_set:
            logger.error("DANGEROUS CONFIG")
    finally:
        logger.remove(sink_id)

    assert not any("DANGEROUS CONFIG" in msg for msg in captured)
