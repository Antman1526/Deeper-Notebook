"""v0.8.1 follow-up — /chat/stream must surface selected_provider too.

/chat/execute returns selected_provider in the response body since the
first v0.8.1 commit. The streaming endpoint /chat/stream emits the same
data (canonical messages, mcp_tool_calls) via NDJSON events but the
routing-decision field was deferred. Clients that use the SSE path
otherwise have to refetch /chat/sessions/{id} after `done` to discover
which side served the turn — silly given the data sits one dict-key
away in final_result.

This file asserts the `done` event includes `selected_provider` /
`selected_model_id` whenever the chat graph node populated them.
Companion to tests/test_v0_8_1_selected_provider.py (which covers the
non-streaming path).
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import chat as chat_router

# ---------------------------------------------------------------------------
# Fixtures (mirror the structure in tests/test_chat_stream.py)
# ---------------------------------------------------------------------------

class _FakeSession:
    def __init__(self, id: str = "chat_session:test", model_override=None):
        self.id = id
        self.model_override = model_override

    async def save(self):
        return None


class _FakeChunk:
    def __init__(self, content: str):
        self.content = content


def _make_app() -> FastAPI:
    a = FastAPI()
    a.include_router(chat_router.router, prefix="/api")
    return a


@pytest.fixture
def fake_graph(monkeypatch):
    class _FakeGraph:
        events: list[dict] = []

        def get_state(self, config):
            class _S:
                values = {"messages": []}
            return _S()

        async def astream_events(self, *, input, config, version):
            for e in self.events:
                yield e

    fake = _FakeGraph()
    monkeypatch.setattr(chat_router, "chat_graph", fake)

    async def _fake_get_async_graph():
        return fake
    monkeypatch.setattr(chat_router, "get_async_graph", _fake_get_async_graph)
    return fake


@pytest.fixture
def fake_session(monkeypatch):
    from deeper_notebook.domain import notebook as nb_mod
    sessions = {"chat_session:test": _FakeSession()}

    async def fake_get(session_id: str):
        return sessions.get(session_id)

    monkeypatch.setattr(nb_mod.ChatSession, "get", staticmethod(fake_get))
    return sessions


def _parse_ndjson(body: str) -> list[dict]:
    return [json.loads(line) for line in body.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_done_event_carries_selected_provider_local_when_dict_output(
    monkeypatch, fake_graph, fake_session
):
    """Dict-shaped on_chain_end output (the current TypedDict path) →
    done event includes selected_provider="local" and selected_model_id."""
    fake_graph.events = [
        {"event": "on_chat_model_stream",
         "data": {"chunk": _FakeChunk("hi")}},
        {"event": "on_chain_end",
         "data": {"output": {
             "messages": [
                 type("M", (), {"id": "m1", "type": "human",
                                "content": "Hi"})(),
                 type("M", (), {"id": "m2", "type": "ai",
                                "content": "hi"})(),
             ],
             "selected_provider": "local",
             "selected_model_id": "model:hermes",
             "mcp_tool_calls": None,
         }}},
    ]

    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            "/api/chat/stream",
            json={
                "session_id": "chat_session:test",
                "message": "Hi",
                "context": {},
            },
        )

    assert resp.status_code == 200
    events = _parse_ndjson(resp.text)
    done = [e for e in events if e.get("type") == "done"][0]
    assert done["selected_provider"] == "local"
    assert done["selected_model_id"] == "model:hermes"


def test_done_event_carries_selected_provider_cloud(
    monkeypatch, fake_graph, fake_session
):
    """Cloud routing decision propagates to the done event."""
    fake_graph.events = [
        {"event": "on_chain_end",
         "data": {"output": {
             "messages": [
                 type("M", (), {"id": "m2", "type": "ai",
                                "content": "ok"})(),
             ],
             "selected_provider": "cloud",
             "selected_model_id": "model:gpt4",
         }}},
    ]

    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            "/api/chat/stream",
            json={
                "session_id": "chat_session:test",
                "message": "Hi",
                "context": {},
            },
        )

    events = _parse_ndjson(resp.text)
    done = [e for e in events if e.get("type") == "done"][0]
    assert done["selected_provider"] == "cloud"
    assert done["selected_model_id"] == "model:gpt4"


def test_done_event_selected_provider_null_when_routing_disabled(
    monkeypatch, fake_graph, fake_session
):
    """Graph state without the keys (smart routing off, model_override
    path, or upstream state schema) → done event reports null instead
    of omitting the keys, so the wire shape is stable for clients."""
    fake_graph.events = [
        {"event": "on_chain_end",
         "data": {"output": {
             "messages": [
                 type("M", (), {"id": "m2", "type": "ai",
                                "content": "ok"})(),
             ],
             # selected_provider / selected_model_id intentionally absent
         }}},
    ]

    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            "/api/chat/stream",
            json={
                "session_id": "chat_session:test",
                "message": "Hi",
                "context": {},
            },
        )

    events = _parse_ndjson(resp.text)
    done = [e for e in events if e.get("type") == "done"][0]
    # Field present (stable wire shape) but value None.
    assert "selected_provider" in done
    assert done["selected_provider"] is None
    assert "selected_model_id" in done
    assert done["selected_model_id"] is None


def test_done_event_survives_pydantic_state_shape(
    monkeypatch, fake_graph, fake_session
):
    """v0.8.1 audit fix — when the on_chain_end output is a Pydantic
    model (not a dict), the synthetic dict the router builds must
    preserve selected_provider/selected_model_id, not just messages +
    mcp_tool_calls. Prior to the audit fix, the synthetic dict dropped
    them silently — frontends saw null even when routing happened."""

    class _PydanticState:
        """Stand-in for a future Pydantic-typed chat ThreadState. Only
        attribute access matters here (the router uses getattr)."""
        def __init__(self):
            self.messages = [
                type("M", (), {"id": "m2", "type": "ai",
                               "content": "ok"})(),
            ]
            self.selected_provider = "local"
            self.selected_model_id = "model:hermes"
            self.mcp_tool_calls = None

    fake_graph.events = [
        {"event": "on_chain_end",
         "data": {"output": _PydanticState()}},
    ]

    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            "/api/chat/stream",
            json={
                "session_id": "chat_session:test",
                "message": "Hi",
                "context": {},
            },
        )

    events = _parse_ndjson(resp.text)
    done = [e for e in events if e.get("type") == "done"][0]
    assert done["selected_provider"] == "local"
    assert done["selected_model_id"] == "model:hermes"
