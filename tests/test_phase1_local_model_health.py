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
