"""v0.7.38 — regression tests for the streaming /chat/stream endpoint.

The non-streaming /chat/execute path is unchanged; this file verifies:

  - Event wire format: NDJSON, one JSON object per line
  - The discriminated-union event types: start / token / done / error
  - Token events carry .content; done event carries .messages
  - Errors surface as {"type":"error"} instead of HTTP 500 mid-stream
  - Client disconnect halts the stream early (resource safety)

The endpoint is exercised end-to-end via TestClient with the graph
stubbed out; we don't spin up a real LLM.
"""

from __future__ import annotations

import json
from typing import Any, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import chat as chat_router

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeSession:
    """Stand-in for ChatSession used by /chat/stream startup."""

    def __init__(self, id: str = "chat_session:test", model_override=None):
        self.id = id
        self.model_override = model_override

    async def save(self):
        # called at the end of the stream; no-op for tests
        return None


class _FakeChunk:
    def __init__(self, content: str):
        self.content = content


class _FakeChatSessionGet:
    """Drop-in replacement for ChatSession.get; returns a session or None."""

    def __init__(self, returning):
        self._returning = returning
        self.called_with: list = []

    async def __call__(self, session_id: str):
        self.called_with.append(session_id)
        return self._returning


def _make_app(stream_events, session_for_get=None) -> FastAPI:
    """Build a minimal FastAPI app exposing only /chat/stream and
    /chat/execute, with the LangGraph stubbed to yield `stream_events`."""
    a = FastAPI()
    a.include_router(chat_router.router, prefix="/api")
    return a


@pytest.fixture
def fake_graph(monkeypatch):
    """Patch chat_router.chat_graph with a fake whose astream_events
    yields the given iterable. Tests set `fake_graph.events`."""

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

    # v0.7.192 — chat_router.get_async_graph (added in v0.7.192) is
    # what _stream_chat_events actually calls for astream_events.
    # The pre-v0.7.192 code did `chat_graph.astream_events(...)`
    # directly; the lazy async-graph factory returns the
    # AsyncSqliteSaver-backed twin. Patch both so the fake intercepts
    # the streaming path.
    async def _fake_get_async_graph():
        return fake

    monkeypatch.setattr(chat_router, "get_async_graph", _fake_get_async_graph)
    return fake


@pytest.fixture
def fake_session(monkeypatch):
    """Patch the ChatSession.get so it returns a session for any id
    that starts with chat_session:test, else None."""
    from deeper_notebook.domain import notebook as nb_mod

    sessions = {"chat_session:test": _FakeSession()}

    async def fake_get(session_id: str):
        return sessions.get(session_id)

    monkeypatch.setattr(nb_mod.ChatSession, "get", staticmethod(fake_get))
    return sessions


def _parse_ndjson(body: str) -> list[dict]:
    """Parse an NDJSON response body into a list of dicts."""
    return [json.loads(line) for line in body.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Wire format
# ---------------------------------------------------------------------------


def test_stream_returns_ndjson_with_start_token_done_events(
    monkeypatch, fake_graph, fake_session
):
    """Happy path: start → 3 token events → done. Wire format is one
    JSON object per line (NDJSON)."""
    fake_graph.events = [
        {"event": "on_chat_model_stream", "data": {"chunk": _FakeChunk("Hello ")}},
        {"event": "on_chat_model_stream", "data": {"chunk": _FakeChunk("world")}},
        {"event": "on_chat_model_stream", "data": {"chunk": _FakeChunk("!")}},
        # Outer chain emits the final messages
        {
            "event": "on_chain_end",
            "data": {
                "output": {
                    "messages": [
                        type("M", (), {"id": "m1", "type": "human", "content": "Hi"})(),
                        type(
                            "M",
                            (),
                            {"id": "m2", "type": "ai", "content": "Hello world!"},
                        )(),
                    ]
                }
            },
        },
    ]

    app = _make_app(fake_graph.events)
    with TestClient(app) as client:
        resp = client.post(
            "/api/chat/stream",
            json={"session_id": "chat_session:test", "message": "Hi", "context": {}},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    events = _parse_ndjson(resp.text)
    types = [e["type"] for e in events]

    # start, three tokens, done
    assert types[0] == "start"
    assert types[-1] == "done"
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) == 3
    assert "".join(e["content"] for e in token_events) == "Hello world!"

    # done event carries the canonical messages list
    done = events[-1]
    assert "messages" in done
    assert len(done["messages"]) == 2
    assert done["messages"][1]["content"] == "Hello world!"


def test_stream_emits_error_event_on_missing_session(monkeypatch, fake_graph):
    """No session matches → the FIRST event is {"type":"error"}.
    We do NOT return HTTP 4xx because we've already committed to a
    streaming response by the time we know."""
    from deeper_notebook.domain import notebook as nb_mod

    async def fake_get(_id):
        return None  # session not found

    monkeypatch.setattr(nb_mod.ChatSession, "get", staticmethod(fake_get))

    app = _make_app(fake_graph.events)
    with TestClient(app) as client:
        resp = client.post(
            "/api/chat/stream",
            json={"session_id": "chat_session:missing", "message": "hi", "context": {}},
        )
    assert resp.status_code == 200  # stream itself succeeded
    events = _parse_ndjson(resp.text)
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "Session not found" in events[0]["detail"]


def test_stream_emits_error_event_on_graph_exception(
    monkeypatch, fake_graph, fake_session
):
    """If the graph raises mid-stream, we surface it as a final
    {"type":"error"} event rather than ending the HTTP response with
    a partial body."""

    async def boom(*args, **kw):
        # First yield a token, then raise
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": _FakeChunk("partial")},
        }
        raise RuntimeError("LLM provider unreachable")

    fake_graph.astream_events = boom  # type: ignore[method-assign]

    app = _make_app([])
    with TestClient(app) as client:
        resp = client.post(
            "/api/chat/stream",
            json={"session_id": "chat_session:test", "message": "hi", "context": {}},
        )

    events = _parse_ndjson(resp.text)
    types = [e["type"] for e in events]
    # We saw the start, the first token, then error
    assert "start" in types
    assert "token" in types
    assert "error" in types
    err = next(e for e in events if e["type"] == "error")
    # v0.7.184 — sanitised generic detail (no raw exception text).
    # Previously this asserted "LLM provider unreachable" in detail,
    # which was effectively asserting the str(e) info leak the
    # v0.7.184 audit closed. The raw exception is now in the log
    # only; the client gets a generic message. Same class of
    # tightening v0.7.168 / v0.7.177 applied to non-streaming routes.
    assert err["detail"] == "Chat stream failed unexpectedly."
    # And we did NOT leak the raw exception text into the wire body.
    assert "LLM provider unreachable" not in resp.text


def test_stream_surfaces_context_overflow_message(
    monkeypatch, fake_graph, fake_session
):
    """v0.8.67i — a context_length_exceeded (the all-sources-too-large case)
    surfaces as the ACTIONABLE classify_error() message, NOT the generic
    'Chat stream failed unexpectedly.'. The crafted message is the user's
    only hint to deselect sources or pick a larger-context model, so it must
    reach the wire. It is a safe, app-crafted string (not raw provider text),
    so echoing it does not regress the v0.7.184 info-leak tightening."""
    from deeper_notebook.exceptions import ExternalServiceError

    overflow_msg = (
        "Content too large for the selected model. Try using a smaller "
        "selection or a model with a larger context window."
    )

    async def boom(*args, **kw):
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": _FakeChunk("partial")},
        }
        raise ExternalServiceError(overflow_msg)

    fake_graph.astream_events = boom  # type: ignore[method-assign]

    app = _make_app([])
    with TestClient(app) as client:
        resp = client.post(
            "/api/chat/stream",
            json={
                "session_id": "chat_session:test",
                "message": "summarize all sources",
                "context": {},
            },
        )

    events = _parse_ndjson(resp.text)
    err = next(e for e in events if e["type"] == "error")
    assert err["detail"] == overflow_msg
    assert "failed unexpectedly" not in resp.text


def test_stream_surfaces_network_error_message(monkeypatch, fake_graph, fake_session):
    """v0.8.67i — NetworkError (e.g. the local sidecar not yet reachable on
    a cold first request) likewise surfaces its actionable message instead
    of the opaque generic failure."""
    from deeper_notebook.exceptions import NetworkError

    net_msg = (
        "Could not reach the AI model server. If you're using a local "
        "model (llama.cpp / Ollama), make sure it's running."
    )

    async def boom(*args, **kw):
        yield {"event": "on_chat_model_stream", "data": {"chunk": _FakeChunk("x")}}
        raise NetworkError(net_msg)

    fake_graph.astream_events = boom  # type: ignore[method-assign]

    app = _make_app([])
    with TestClient(app) as client:
        resp = client.post(
            "/api/chat/stream",
            json={"session_id": "chat_session:test", "message": "hi", "context": {}},
        )

    events = _parse_ndjson(resp.text)
    err = next(e for e in events if e["type"] == "error")
    assert err["detail"] == net_msg


def test_stream_filters_non_string_chunk_content(monkeypatch, fake_graph, fake_session):
    """on_chat_model_stream chunks with non-string content (multi-modal)
    are silently skipped — we only emit string tokens to the client."""
    fake_graph.events = [
        {
            "event": "on_chat_model_stream",
            "data": {"chunk": _FakeChunk(None)},
        },  # None content
        {
            "event": "on_chat_model_stream",
            "data": {"chunk": _FakeChunk([{"type": "image", "url": "..."}])},
        },  # multi-modal list
        {"event": "on_chat_model_stream", "data": {"chunk": _FakeChunk("real text")}},
        {"event": "on_chain_end", "data": {"output": {"messages": []}}},
    ]

    app = _make_app(fake_graph.events)
    with TestClient(app) as client:
        resp = client.post(
            "/api/chat/stream",
            json={"session_id": "chat_session:test", "message": "hi", "context": {}},
        )
    events = _parse_ndjson(resp.text)
    tokens = [e for e in events if e["type"] == "token"]
    assert len(tokens) == 1
    assert tokens[0]["content"] == "real text"


def test_stream_response_headers_disable_proxy_buffering(
    monkeypatch, fake_graph, fake_session
):
    """X-Accel-Buffering: no and Cache-Control: no-cache are required
    for nginx-family proxies + Next.js dev proxy to actually flush
    each NDJSON line as it's written."""
    fake_graph.events = [
        {"event": "on_chain_end", "data": {"output": {"messages": []}}},
    ]

    app = _make_app(fake_graph.events)
    with TestClient(app) as client:
        resp = client.post(
            "/api/chat/stream",
            json={"session_id": "chat_session:test", "message": "hi", "context": {}},
        )
    assert resp.headers.get("x-accel-buffering") == "no"
    assert "no-cache" in resp.headers.get("cache-control", "")
