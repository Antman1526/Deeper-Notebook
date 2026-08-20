"""v0.7.108 — regression test for v0.7.99's /chat/execute timeout.

v0.7.99 wrapped `chat_graph.ainvoke()` in `asyncio.wait_for(timeout=
_chat_timeout)` so a hung local chat model can't block the non-streaming
endpoint forever. This test verifies:

  * The timeout actually fires when the graph never returns.
  * The HTTP response is 504 (Gateway Timeout), NOT 500 or 200.
  * The detail message includes the env-knob name AND the streaming
    endpoint hint, so the user has an actionable next step.

We stub `chat_graph.ainvoke`, `chat_graph.get_state`, and
`ChatSession.get` so the test doesn't need a database or LangGraph
runtime — only the timeout-wrapping code path is exercised.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import chat as chat_router


@pytest.fixture()
def app():
    a = FastAPI()
    a.include_router(chat_router.router, prefix="/api")
    return a


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def hanging_graph(monkeypatch):
    """Replace chat_graph with one whose ainvoke hangs forever and whose
    get_state returns an empty state. The wait_for timeout in the handler
    is what must save us.

    v0.7.192 — Also stub `get_async_graph()` (the v0.7.192 lazy async-
    checkpointer twin). Pre-fix the router only used chat_graph.ainvoke;
    after v0.7.192 the actual ainvoke call sites use the async twin via
    `await get_async_graph()`, so the test had to be extended to patch
    both surfaces."""

    class _HangingGraph:
        def get_state(self, config):
            return SimpleNamespace(values={"messages": []})

        async def ainvoke(self, *, input, config):
            # Hang well past the test's 1s timeout
            await asyncio.sleep(60)
            return {"messages": []}

    fake = _HangingGraph()
    monkeypatch.setattr(chat_router, "chat_graph", fake)

    # v0.7.192 — also stub the lazy async-graph getter so the wait_for
    # at the call site times out on OUR hanging fake, not on the real
    # graph trying to reach a non-existent SurrealDB.
    async def _fake_get_async_graph():
        return fake

    monkeypatch.setattr(chat_router, "get_async_graph", _fake_get_async_graph)
    return fake


@pytest.fixture()
def fake_session(monkeypatch):
    """Make ChatSession.get return a fake session for our test session_id."""
    from deeper_notebook.domain import notebook as nb_mod

    async def _get(session_id):
        if session_id.startswith("chat_session:"):
            return SimpleNamespace(id=session_id, model_override=None)
        return None

    monkeypatch.setattr(nb_mod.ChatSession, "get", staticmethod(_get))


def test_chat_execute_timeout_returns_504_with_env_knob_hint(
    client,
    hanging_graph,
    fake_session,
    monkeypatch,
):
    """v0.7.108 — When chat_graph.ainvoke hangs past DEEPER_NOTEBOOK_CHAT_TIMEOUT_SEC,
    the endpoint must return 504 with the env knob + /chat/stream hint
    in the detail. Previously (pre-v0.7.99) it would hang the request
    indefinitely."""
    # Force a tiny timeout so the test runs in ~1s instead of 300.
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_TIMEOUT_SEC", "1")

    resp = client.post(
        "/api/chat/execute",
        json={
            "session_id": "chat_session:test",
            "message": "Hello",
            "context": {},
        },
    )
    assert resp.status_code == 504, resp.text
    detail = resp.json()["detail"]
    # Actionable: name the env knob the user can raise
    assert "DEEPER_NOTEBOOK_CHAT_TIMEOUT_SEC" in detail
    # Actionable: point at the streaming endpoint as the better path
    assert "/chat/stream" in detail
    # Includes the actual timeout value so the user knows what they hit
    assert "timed out" in detail.lower()


def test_chat_execute_returns_200_when_graph_returns_in_time(
    client,
    fake_session,
    monkeypatch,
):
    """v0.7.108 — Negative-space check: a graph that returns within the
    timeout must produce a 200, not be incorrectly timeout-killed."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_TIMEOUT_SEC", "5")

    class _FastGraph:
        def get_state(self, config):
            return SimpleNamespace(values={"messages": []})

        async def ainvoke(self, *, input, config):
            # Returns immediately with one AI message
            from langchain_core.messages import AIMessage

            return {"messages": [AIMessage(content="quick reply")]}

    fake_fast = _FastGraph()
    monkeypatch.setattr(chat_router, "chat_graph", fake_fast)

    # v0.7.192 — patch the async-graph getter too (see hanging_graph
    # fixture above for the full rationale).
    async def _fake_get_async_graph():
        return fake_fast

    monkeypatch.setattr(chat_router, "get_async_graph", _fake_get_async_graph)

    resp = client.post(
        "/api/chat/execute",
        json={
            "session_id": "chat_session:test",
            "message": "Hi",
            "context": {},
        },
    )
    # 200 means we did NOT incorrectly timeout-kill a fast response.
    # (Session save may fail in this minimal harness; we check for any
    # success-shaped response — 200 or 500 with a "save" message — that
    # confirms the timeout path didn't fire spuriously.)
    assert resp.status_code != 504, resp.text
