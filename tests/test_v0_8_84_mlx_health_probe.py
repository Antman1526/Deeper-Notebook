"""v0.8.84 — a 200 with an empty body counts as a live OpenAI-compatible server.

mlx-lm 0.31's server answers ``GET /v1/models`` with HTTP 200 and zero bytes
(verified live against the packaged app: 0 bytes both before and after a
successful chat completion on the same server). The probe's subject is "is the
server up", so a JSON parse failure on a 200 must not mark it unhealthy.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from deeper_notebook.health.local_models import _probe_openai_compatible


def _resp(status: int, body: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    if body:
        resp.json.return_value = {"data": [{"id": body}]}
    else:
        resp.json.side_effect = ValueError("Expecting value: line 1 column 1")
    return resp


def _probe_with(resp: MagicMock):
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get.return_value = resp
    with patch.object(httpx, "Client", return_value=client):
        return _probe_openai_compatible(
            name="MLX (local)", base_url="http://127.0.0.1:1/v1"
        )


def test_http_200_with_empty_body_is_healthy():
    result = _probe_with(_resp(200, ""))
    assert result["status"] == "healthy"
    assert result["detail"] == "no models listed"


def test_http_200_with_model_list_reports_models():
    result = _probe_with(_resp(200, "qwen3.8-27b"))
    assert result["status"] == "healthy"
    assert "qwen3.8-27b" in result["detail"]


def test_non_200_is_still_unhealthy():
    result = _probe_with(_resp(503, ""))
    assert result["status"] == "unhealthy"
    assert "503" in result["detail"]


def test_read_timeout_with_live_port_is_healthy():
    """mlx-lm 0.31 wedges GET /v1/models after its first completion while the
    server keeps serving chat. Timeout + live TCP port must read healthy."""
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get.side_effect = httpx.ReadTimeout("timed out")
    with patch.object(httpx, "Client", return_value=client), patch(
        "deeper_notebook.health.local_models._port_accepts_connection",
        return_value=True,
    ):
        result = _probe_openai_compatible(
            name="MLX (local)", base_url="http://127.0.0.1:1/v1"
        )
    assert result["status"] == "healthy"
    assert "timed out" in result["detail"]


def test_read_timeout_with_dead_port_is_unhealthy():
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get.side_effect = httpx.ReadTimeout("timed out")
    with patch.object(httpx, "Client", return_value=client), patch(
        "deeper_notebook.health.local_models._port_accepts_connection",
        return_value=False,
    ):
        result = _probe_openai_compatible(
            name="MLX (local)", base_url="http://127.0.0.1:1/v1"
        )
    assert result["status"] == "unhealthy"
