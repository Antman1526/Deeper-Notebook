"""Phase 1 — Local-model health module produces a structured
report the API can serve to the frontend."""
from __future__ import annotations
from unittest.mock import patch, MagicMock

import pytest


def test_probe_local_model_returns_unknown_for_zero_port():
    """A port of 0 means the supervisor never spawned this service;
    health must surface that as `status='not_configured'` rather
    than raising or returning a misleading 'down'."""
    from open_notebook.health.local_models import probe_local_model

    result = probe_local_model(
        name="whisper",
        kind="openai_compatible",
        base_url="http://127.0.0.1:0/v1",
    )
    assert result["status"] == "not_configured"
    assert result["name"] == "whisper"


def test_probe_openai_compatible_healthy(monkeypatch):
    """A live llama-cpp server returns 200 on /models; probe
    must report status='healthy' with measured latency."""
    from unittest.mock import MagicMock, patch
    from open_notebook.health.local_models import probe_local_model

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "object": "list",
        "data": [{"id": "Hermes-3-Llama-3.1-8B"}],
    }
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    fake_client.get.return_value = fake_resp

    with patch("open_notebook.health.local_models.httpx.Client",
               return_value=fake_client):
        result = probe_local_model(
            name="local_chat", kind="openai_compatible",
            base_url="http://127.0.0.1:5000/v1",
        )
    assert result["status"] == "healthy"
    assert result["latency_ms"] is not None
    assert "Hermes-3" in (result["detail"] or "")


def test_probe_openai_compatible_unhealthy_connect_refused():
    """When the port is closed (ConnectionRefused / unreachable),
    probe must report status='unhealthy' with a connect detail.
    Uses a port that's vanishingly unlikely to be in use on the
    test runner (1 is a privileged port that pytest won't bind)."""
    from open_notebook.health.local_models import probe_local_model

    result = probe_local_model(
        name="local_chat", kind="openai_compatible",
        base_url="http://127.0.0.1:1/v1",
    )
    assert result["status"] == "unhealthy"
    assert "connect" in (result["detail"] or "").lower()


def test_probe_all_iterates_credentials():
    """Given a list of credential dicts, probe_all returns one
    HealthResult per cred in input order."""
    from open_notebook.health.local_models import probe_all_local_models

    creds = [
        {"name": "chat", "kind": "openai_compatible",
         "base_url": "http://127.0.0.1:0/v1"},
        {"name": "embed", "kind": "openai_compatible",
         "base_url": "http://127.0.0.1:0/v1"},
    ]
    results = probe_all_local_models(creds)
    assert len(results) == 2
    assert [r["name"] for r in results] == ["chat", "embed"]
    assert all(r["status"] == "not_configured" for r in results)


def test_router_returns_health_payload(monkeypatch):
    """GET /api/local-models/health returns aggregated overall + per-model."""
    from fastapi.testclient import TestClient
    from api.main import app

    # Stub the probe to avoid real HTTP.
    from open_notebook.health import local_models as hm
    monkeypatch.setattr(
        hm, "probe_all_local_models",
        lambda creds: [{"name": "chat", "status": "healthy",
                        "detail": "ok", "latency_ms": 12.3}],
    )
    # Stub the credential fetch — in-test we have no SurrealDB.
    from api.routers import local_models as router_mod
    async def _stub_creds():
        return [{"name": "chat", "kind": "openai_compatible",
                 "base_url": "http://127.0.0.1:1234/v1"}]
    monkeypatch.setattr(
        router_mod, "_load_local_credentials", _stub_creds,
    )
    client = TestClient(app)
    r = client.get("/api/local-models/health")
    assert r.status_code == 200
    body = r.json()
    assert body["overall"] in {"healthy", "degraded", "down"}
    assert body["models"][0]["name"] == "chat"
