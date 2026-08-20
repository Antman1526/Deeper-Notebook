"""v0.7.131 regression tests covering deferred-item improvements:

  * Request-ID middleware character-set validation (Area for Review #25)
  * /metrics optional bearer-token auth via DEEPER_NOTEBOOK_METRICS_AUTH_TOKEN (#19)
  * Integration suite dynamic table-discovery helper (#17) — pure unit
    tests of the _discover_tables shape-parsing logic; the real
    INFO FOR DB exercise happens in the integration suite itself

Hermetic — no SurrealDB, no surreal-commands worker, no external services.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------- #
# Request-ID middleware character-set validation
# ---------------------------------------------------------------------- #


class TestRequestIDValidation:
    """v0.7.131 — Area for Review #25.

    The middleware previously only enforced length on inbound
    X-Request-ID; a value containing newlines or control characters
    would land in the loguru `req=` column verbatim and could let an
    attacker forge fake log lines once a log-aggregation tool split
    on \\n. Now the inbound value is checked against
    `^[A-Za-z0-9_\\-.:]+$`; mismatches fall back to a fresh uuid4.
    """

    def _make_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.middleware.request_id import RequestIDMiddleware, current_request_id

        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/echo-request-id")
        async def echo_request_id():
            # current_request_id() reads from the ContextVar that the
            # middleware set; we don't need the Request object itself.
            return {"request_id": current_request_id()}

        return TestClient(app)

    def test_valid_uuid_inbound_preserved(self):
        client = self._make_client()
        rid = "abc-DEF_123.xyz:0"  # mixes every allowed-set char class
        r = client.get("/echo-request-id", headers={"X-Request-ID": rid})
        assert r.status_code == 200
        assert r.json()["request_id"] == rid
        assert r.headers["X-Request-ID"] == rid

    def test_newline_injection_rejected(self):
        """The canonical log-injection payload: \\n followed by a fake
        log line prefix. Must be rejected; middleware mints fresh UUID."""
        client = self._make_client()
        malicious = "valid-prefix\n[CRITICAL] forged log entry"
        r = client.get("/echo-request-id", headers={"X-Request-ID": malicious})
        assert r.status_code == 200
        # New UUID4 (36-char hex with dashes) — should not contain newlines
        # and definitely should not equal the injected value.
        returned = r.json()["request_id"]
        assert "\n" not in returned
        assert returned != malicious
        # Should match uuid4 shape
        assert re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            returned,
        )

    def test_control_chars_rejected(self):
        client = self._make_client()
        for malicious in ("a\rb", "a\tb", "a\x00b", "<script>alert(1)</script>"):
            r = client.get("/echo-request-id", headers={"X-Request-ID": malicious})
            returned = r.json()["request_id"]
            assert returned != malicious, (
                f"Expected {malicious!r} to be rejected, got it back verbatim"
            )

    def test_overlong_rejected(self):
        """129+ char IDs hit the existing length cap; the regex check
        is downstream of that. Verify both gates work."""
        client = self._make_client()
        too_long = "a" * 200  # 200 chars, all valid chars, but over length cap
        r = client.get("/echo-request-id", headers={"X-Request-ID": too_long})
        returned = r.json()["request_id"]
        assert returned != too_long
        assert len(returned) <= 128

    def test_no_inbound_mints_fresh_uuid(self):
        """Baseline: no header → fresh UUID4 (unchanged behavior)."""
        client = self._make_client()
        r = client.get("/echo-request-id")
        assert r.status_code == 200
        returned = r.json()["request_id"]
        assert re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            returned,
        )


# ---------------------------------------------------------------------- #
# /metrics bearer-token auth
# ---------------------------------------------------------------------- #


class TestMetricsAuth:
    """v0.7.131 — Area for Review #19.

    Default: unauthenticated (no env var set). Set
    DEEPER_NOTEBOOK_METRICS_AUTH_TOKEN to require Authorization: Bearer <token>.
    """

    def _make_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # The /metrics endpoint is defined on app object in api/main.py;
        # for testability we re-create the handler inline against a
        # fresh FastAPI app. The handler's auth logic doesn't depend on
        # any other middleware so this works as a pure unit test.
        from api.main import metrics as metrics_handler

        app = FastAPI()
        app.add_api_route("/metrics", metrics_handler, methods=["GET"])
        return TestClient(app)

    def test_no_token_set_endpoint_open(self, monkeypatch):
        """Backward compatibility: with no DEEPER_NOTEBOOK_METRICS_AUTH_TOKEN,
        /metrics works without any auth header."""
        monkeypatch.delenv("DEEPER_NOTEBOOK_METRICS_AUTH_TOKEN", raising=False)
        client = self._make_client()
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "onp_http_requests_total" in r.text or "process_" in r.text

    def test_token_set_no_header_rejected(self, monkeypatch):
        monkeypatch.setenv(
            "DEEPER_NOTEBOOK_METRICS_AUTH_TOKEN", "secret-scrape-token-abc"
        )
        client = self._make_client()
        r = client.get("/metrics")
        assert r.status_code == 401
        # WWW-Authenticate header should be set so an HTTP-aware scraper
        # could conceivably auto-discover the auth method.
        assert "Bearer" in r.headers.get("WWW-Authenticate", "")

    def test_token_set_wrong_token_rejected(self, monkeypatch):
        monkeypatch.setenv(
            "DEEPER_NOTEBOOK_METRICS_AUTH_TOKEN", "secret-scrape-token-abc"
        )
        client = self._make_client()
        r = client.get("/metrics", headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401

    def test_token_set_correct_token_accepted(self, monkeypatch):
        monkeypatch.setenv(
            "DEEPER_NOTEBOOK_METRICS_AUTH_TOKEN", "secret-scrape-token-abc"
        )
        client = self._make_client()
        r = client.get(
            "/metrics",
            headers={"Authorization": "Bearer secret-scrape-token-abc"},
        )
        assert r.status_code == 200
        assert "process_" in r.text or "onp_" in r.text

    def test_malformed_header_rejected(self, monkeypatch):
        """No 'Bearer ' prefix → 401, even if the literal token follows."""
        monkeypatch.setenv(
            "DEEPER_NOTEBOOK_METRICS_AUTH_TOKEN", "secret-scrape-token-abc"
        )
        client = self._make_client()
        # Common mistakes a hand-written scraper might make:
        for bad in (
            "secret-scrape-token-abc",  # no scheme
            "bearer secret-scrape-token-abc",  # lowercase scheme
            "Basic c2VjcmV0",  # wrong scheme
        ):
            r = client.get("/metrics", headers={"Authorization": bad})
            assert r.status_code == 401, f"Expected 401 for {bad!r}"

    def test_empty_token_env_treated_as_unset(self, monkeypatch):
        """An empty-string env var should NOT enable auth — that would
        be a footgun where setting `DEEPER_NOTEBOOK_METRICS_AUTH_TOKEN=` in .env
        accidentally locks down /metrics. Treat empty == unset."""
        monkeypatch.setenv("DEEPER_NOTEBOOK_METRICS_AUTH_TOKEN", "")
        client = self._make_client()
        r = client.get("/metrics")
        assert r.status_code == 200


# ---------------------------------------------------------------------- #
# Integration suite — _discover_tables shape parsing
# ---------------------------------------------------------------------- #


class TestDiscoverTablesShapeParsing:
    """v0.7.131 — Area for Review #17.

    `_discover_tables()` parses the result of `INFO FOR DB`. Different
    SurrealDB versions return slightly different shapes; we accept
    either `tables` (v2) or `tb` (older) and exclude system / protected
    tables via the deny list. These tests pin those parsing rules
    without needing a live SurrealDB instance.
    """

    @pytest.mark.asyncio
    async def test_v2_shape_tables_key(self):
        from tests.integration.conftest import _discover_tables

        # SurrealDB v2 returns {"tables": {<name>: <ddl>, ...}, ...}
        fake_rows = [
            {
                "tables": {
                    "notebook": "DEFINE TABLE notebook ...",
                    "source": "DEFINE TABLE source ...",
                    "reference": "DEFINE TABLE reference ...",
                },
                "functions": {},
                "scopes": {},
            }
        ]
        with patch(
            "deeper_notebook.database.repository.repo_query",
            AsyncMock(return_value=fake_rows),
        ):
            tables = await _discover_tables()
        assert sorted(tables) == ["notebook", "reference", "source"]

    @pytest.mark.asyncio
    async def test_older_shape_tb_key(self):
        from tests.integration.conftest import _discover_tables

        # Older SurrealDB returned the alias key `tb`.
        fake_rows = [{"tb": {"notebook": "...", "source": "..."}}]
        with patch(
            "deeper_notebook.database.repository.repo_query",
            AsyncMock(return_value=fake_rows),
        ):
            tables = await _discover_tables()
        assert sorted(tables) == ["notebook", "source"]

    @pytest.mark.asyncio
    async def test_protected_tables_excluded(self):
        """`_sbl_migrations` and any underscore-prefixed system table
        must never be returned — they'd force migration re-run if
        truncated between tests."""
        from tests.integration.conftest import _discover_tables

        fake_rows = [
            {
                "tables": {
                    "notebook": "...",
                    "_sbl_migrations": "...",  # must be skipped
                    "_audit_log": "...",  # future-proofing — any "_*"
                    "source": "...",
                },
            }
        ]
        with patch(
            "deeper_notebook.database.repository.repo_query",
            AsyncMock(return_value=fake_rows),
        ):
            tables = await _discover_tables()
        assert sorted(tables) == ["notebook", "source"]

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_list(self):
        from tests.integration.conftest import _discover_tables

        for empty in ([], [{"tables": {}}], [{}]):
            with patch(
                "deeper_notebook.database.repository.repo_query",
                AsyncMock(return_value=empty),
            ):
                tables = await _discover_tables()
            assert tables == [], f"Expected [] for empty result {empty!r}"
