"""v0.7.132 regression tests covering:

  * /healthz/deep upstream-provider probe (Area for Review #12)
  * _brief() smarter exception-message truncation (#10)

Hermetic — no SurrealDB, no real upstream providers. The probe is
exercised against a mocked Credential + connection_tester.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------- #
# _brief() smarter truncation
# ---------------------------------------------------------------------- #


class TestBriefTruncation:
    """v0.7.132 — Area for Review #10. The single-line behavior is
    unchanged; multi-line exceptions now preserve the first line +
    indicate "(… N more lines)" so the operator sees the actual head
    of the error."""

    def test_single_line_short_passthrough(self):
        from api.routers.studio import _brief

        exc = ValueError("oh no")
        assert _brief(exc) == "oh no"

    def test_single_line_long_truncated_with_ellipsis(self):
        from api.routers.studio import _brief

        long_msg = "x" * 500
        result = _brief(ValueError(long_msg))
        assert len(result) <= 200
        assert result.endswith("…")
        # No multi-line suffix (it's a single-line case)
        assert "more line" not in result

    def test_multi_line_preserves_first_line(self):
        from api.routers.studio import _brief

        msg = "TypeError: cannot convert int to str\n  at line 42\n  at line 50"
        result = _brief(TypeError(msg))
        # First line preserved verbatim
        assert "TypeError: cannot convert int to str" in result
        # Suffix indicates two more lines
        assert "(… 2 more lines)" in result

    def test_multi_line_singular_pluralization(self):
        from api.routers.studio import _brief

        msg = "Error\nOne extra line"
        result = _brief(RuntimeError(msg))
        # Should say "1 more line" (singular), not "1 more lines"
        assert "(… 1 more line)" in result
        assert "more lines" not in result

    def test_multi_line_long_first_truncated_to_fit_suffix(self):
        """When the first line itself is over budget, it gets
        ellipsized, but room is reserved for the multi-line suffix
        so the operator still sees the line count."""
        from api.routers.studio import _brief

        first = "x" * 500
        msg = f"{first}\nline 2\nline 3"
        result = _brief(RuntimeError(msg))
        assert "(… 2 more lines)" in result
        # Total length stays within the cap
        assert len(result) <= 200
        # First line was truncated with ellipsis
        assert "…" in result


# ---------------------------------------------------------------------- #
# /healthz/deep upstream-provider probe
# ---------------------------------------------------------------------- #


class _FakeCredential:
    def __init__(self, idx: int, provider: str = "openai"):
        self.id = f"credential:fake{idx}"
        self.name = f"Test Cred {idx}"
        self.provider = provider


class TestUpstreamProbe:
    """v0.7.132 — Area for Review #12. Tests the _probe_upstream_providers
    helper directly so we can exercise edge cases (no creds, mixed
    success, timeout, raise) without standing up a real HTTP server."""

    @pytest.mark.asyncio
    async def test_no_credentials_returns_ok_status(self):
        from api.main import _probe_upstream_providers

        with patch(
            "deeper_notebook.domain.credential.Credential.get_all",
            AsyncMock(return_value=[]),
        ):
            result = await _probe_upstream_providers(timeout_seconds=1.0)
        assert result["status"] == "no_credentials"
        assert result["ok"] is True
        assert result["credentials"] == []

    @pytest.mark.asyncio
    async def test_credential_list_failure_returns_error(self):
        from api.main import _probe_upstream_providers

        with patch(
            "deeper_notebook.domain.credential.Credential.get_all",
            AsyncMock(side_effect=RuntimeError("db down")),
        ):
            result = await _probe_upstream_providers(timeout_seconds=1.0)
        assert result["status"] == "error"
        assert result["ok"] is False
        assert "db down" in result["error"]

    @pytest.mark.asyncio
    async def test_all_providers_healthy(self):
        from api.main import _probe_upstream_providers

        creds = [_FakeCredential(1, "openai"), _FakeCredential(2, "anthropic")]
        with (
            patch(
                "deeper_notebook.domain.credential.Credential.get_all",
                AsyncMock(return_value=creds),
            ),
            patch(
                "deeper_notebook.ai.connection_tester.test_provider_connection",
                AsyncMock(return_value=(True, "Connection successful")),
            ),
        ):
            result = await _probe_upstream_providers(timeout_seconds=1.0)
        assert result["status"] == "ok"
        assert result["ok"] is True
        assert len(result["credentials"]) == 2
        assert all(c["ok"] for c in result["credentials"])

    @pytest.mark.asyncio
    async def test_mixed_health_returns_degraded(self):
        from api.main import _probe_upstream_providers

        creds = [_FakeCredential(1, "openai"), _FakeCredential(2, "anthropic")]

        # First returns success, second returns failure.
        # `test_provider_connection` returns a tuple, so the AsyncMock
        # needs side_effect to return different values per call.
        async def fake_probe(provider, config_id=None):
            return (True, "ok") if provider == "openai" else (False, "401")

        with (
            patch(
                "deeper_notebook.domain.credential.Credential.get_all",
                AsyncMock(return_value=creds),
            ),
            patch(
                "deeper_notebook.ai.connection_tester.test_provider_connection",
                new=fake_probe,
            ),
        ):
            result = await _probe_upstream_providers(timeout_seconds=1.0)
        assert result["status"] == "degraded"
        assert result["ok"] is False
        oks = {c["provider"]: c["ok"] for c in result["credentials"]}
        assert oks == {"openai": True, "anthropic": False}

    @pytest.mark.asyncio
    async def test_timeout_surfaces_per_credential(self):
        from api.main import _probe_upstream_providers

        async def slow_probe(provider, config_id=None):
            await asyncio.sleep(10)  # Longer than the test's timeout
            return (True, "would have succeeded")

        creds = [_FakeCredential(1, "openai")]
        with (
            patch(
                "deeper_notebook.domain.credential.Credential.get_all",
                AsyncMock(return_value=creds),
            ),
            patch(
                "deeper_notebook.ai.connection_tester.test_provider_connection",
                new=slow_probe,
            ),
        ):
            result = await _probe_upstream_providers(timeout_seconds=0.2)
        assert result["ok"] is False
        c = result["credentials"][0]
        assert c["ok"] is False
        assert "Timed out" in c["message"]

    @pytest.mark.asyncio
    async def test_probe_raise_caught_per_credential(self):
        """A raising probe must produce an entry, not crash the whole
        gather. Other credentials still get evaluated."""
        from api.main import _probe_upstream_providers

        async def raising_probe(provider, config_id=None):
            if provider == "openai":
                raise RuntimeError("network refused")
            return (True, "ok")

        creds = [_FakeCredential(1, "openai"), _FakeCredential(2, "anthropic")]
        with (
            patch(
                "deeper_notebook.domain.credential.Credential.get_all",
                AsyncMock(return_value=creds),
            ),
            patch(
                "deeper_notebook.ai.connection_tester.test_provider_connection",
                new=raising_probe,
            ),
        ):
            result = await _probe_upstream_providers(timeout_seconds=1.0)
        assert result["status"] == "degraded"
        results_by_provider = {c["provider"]: c for c in result["credentials"]}
        assert results_by_provider["openai"]["ok"] is False
        assert "network refused" in results_by_provider["openai"]["message"]
        assert results_by_provider["anthropic"]["ok"] is True


class TestHealthzDeepProbeFlag:
    """v0.7.132 — /healthz/deep?probe_providers=true must include the
    upstream_providers key; default (no flag) must NOT include it."""

    def _make_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # Patch every dependency the route reaches so we can hit the
        # endpoint without a real DB / migrations / model setup.
        from api.main import healthz_deep

        app = FastAPI()
        app.add_api_route("/healthz/deep", healthz_deep, methods=["GET"])
        return TestClient(app)

    def test_default_omits_upstream_providers_key(self):
        client = self._make_client()
        with (
            patch(
                "api.routers.config.check_database_health",
                AsyncMock(return_value={"status": "online"}),
            ),
            patch(
                "deeper_notebook.database.async_migrate.AsyncMigrationManager"
            ) as mgr_cls,
        ):
            mgr = MagicMock()
            mgr.needs_migration = AsyncMock(return_value=False)
            mgr_cls.return_value = mgr
            with (
                patch(
                    "deeper_notebook.ai.models.model_manager.get_embedding_model",
                    AsyncMock(return_value=MagicMock()),
                ),
                patch(
                    "deeper_notebook.ai.models.model_manager.get_default_model",
                    AsyncMock(return_value=MagicMock()),
                ),
            ):
                r = client.get("/healthz/deep")
        assert r.status_code in (200, 503)
        body = r.json()
        assert "upstream_providers" not in body["checks"], (
            "Default request must NOT include upstream_providers key"
        )

    def test_probe_flag_includes_upstream_providers_key(self):
        client = self._make_client()
        with (
            patch(
                "api.routers.config.check_database_health",
                AsyncMock(return_value={"status": "online"}),
            ),
            patch(
                "deeper_notebook.database.async_migrate.AsyncMigrationManager"
            ) as mgr_cls,
        ):
            mgr = MagicMock()
            mgr.needs_migration = AsyncMock(return_value=False)
            mgr_cls.return_value = mgr
            with (
                patch(
                    "deeper_notebook.ai.models.model_manager.get_embedding_model",
                    AsyncMock(return_value=MagicMock()),
                ),
                patch(
                    "deeper_notebook.ai.models.model_manager.get_default_model",
                    AsyncMock(return_value=MagicMock()),
                ),
                patch(
                    "deeper_notebook.domain.credential.Credential.get_all",
                    AsyncMock(return_value=[]),
                ),
            ):
                r = client.get("/healthz/deep?probe_providers=true")
        body = r.json()
        assert "upstream_providers" in body["checks"]
        assert body["checks"]["upstream_providers"]["status"] == "no_credentials"
