from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_shims.openchronicle_shim import build_app
from fastapi.testclient import TestClient


def _fake_mcp_client(recent_events=None, search_events=None):
    """Fake MCP client with canned tool responses."""
    client = MagicMock()
    client.call_tool = AsyncMock()

    async def fake_call_tool(name, args):
        if name == "recent_activity":
            return {
                "events": recent_events
                or [
                    {"title": "Edited foo.md", "ts": "2026-05-11T08:00Z"},
                ]
            }
        if name == "search":
            return {
                "events": search_events
                or [
                    {"title": "Read Self-RAG paper", "ts": "2026-05-11T07:00Z"},
                ]
            }
        return {"events": []}

    client.call_tool.side_effect = fake_call_tool
    return client


def test_openchronicle_detection_uses_canonical_mcp_client_name(monkeypatch):
    from desktop import app as app_mod

    observed: dict[str, object] = {}

    class _Socket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def settimeout(self, _timeout):
            return None

        def connect(self, address):
            observed["address"] = address

    def post(_url, **kwargs):
        observed["json"] = kwargs["json"]
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr("socket.socket", lambda *_args, **_kwargs: _Socket())
    monkeypatch.setattr("httpx.post", post)
    ctx = SimpleNamespace(
        openchronicle_available=False,
        progress_bus=None,
        log_dir=None,
    )

    app_mod._phase_detect_openchronicle(ctx)

    params = observed["json"]["params"]
    assert params["clientInfo"] == {
        "name": "deeper-notebook",
        "version": "0.5",
    }
    assert ctx.openchronicle_available is True


def test_health_returns_200_when_mcp_reachable():
    app = build_app(mcp_client=_fake_mcp_client())
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200


def test_context_recent_calls_recent_activity_tool():
    mcp = _fake_mcp_client()
    app = build_app(mcp_client=mcp)
    with TestClient(app) as c:
        r = c.get("/context/recent?minutes=10")
        assert r.status_code == 200
        body = r.json()
        assert "events" in body
        assert len(body["events"]) >= 1


def test_context_search_calls_search_tool():
    mcp = _fake_mcp_client()
    app = build_app(mcp_client=mcp)
    with TestClient(app) as c:
        r = c.get("/context/search?topic=self-RAG&limit=5")
        assert r.status_code == 200
        body = r.json()
        assert "events" in body
