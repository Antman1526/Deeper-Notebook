"""v0.8.56 — Phase 5.3c (observability slice): chat tool-loop terminal state.

When the MCP tool loop force-stops at max_iterations while the model still
wants tools, the answer is likely incomplete — previously silent. v0.8.56
records a 'truncated' vs 'complete' outcome (no behavior change, no gate).

Mirrors the v0.8.35e mocking harness (_ScriptedModel / _FakeAIMessage /
_make_tool / _resolve_chat_tools AsyncMock).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from deeper_notebook.graphs import chat as chat_mod


class _FakeAIMessage:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.content = ""


class _ScriptedModel:
    def __init__(self, responses):
        self._responses = list(responses)

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, payload):
        if not self._responses:
            return _FakeAIMessage(tool_calls=[])
        return self._responses.pop(0)


def _make_tool(name, coroutine):
    class _T:
        pass

    t = _T()
    t.name = name
    t.coroutine = coroutine
    return t


def _capture_outcomes(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(
        "api.metrics.record_agent_tool_loop_outcome",
        lambda outcome: seen.append(outcome),
    )
    return seen


def _tool_call(i):
    return {"name": "mcp_search", "args": {"q": str(i)}, "id": f"c{i}"}


@pytest.mark.asyncio
async def test_truncated_when_loop_hits_cap_with_pending_tools(monkeypatch):
    seen = _capture_outcomes(monkeypatch)

    async def _ok(**kwargs):
        return "result"

    monkeypatch.setattr(
        chat_mod,
        "_resolve_chat_tools",
        AsyncMock(return_value=[_make_tool("mcp_search", _ok)]),
    )
    # Every response keeps requesting tools → the loop never stops naturally;
    # with max_iterations=2 it force-stops with tool calls still pending.
    model = _ScriptedModel([_FakeAIMessage([_tool_call(i)]) for i in range(5)])

    await chat_mod.bind_mcp_and_run_tool_loop(model, [], max_iterations=2)

    assert seen == ["truncated"]


@pytest.mark.asyncio
async def test_complete_when_model_stops_requesting_tools(monkeypatch):
    seen = _capture_outcomes(monkeypatch)

    async def _ok(**kwargs):
        return "result"

    monkeypatch.setattr(
        chat_mod,
        "_resolve_chat_tools",
        AsyncMock(return_value=[_make_tool("mcp_search", _ok)]),
    )
    # Round 1 calls a tool; round 2 returns no tool calls → natural completion.
    model = _ScriptedModel(
        [
            _FakeAIMessage([_tool_call(1)]),
            _FakeAIMessage([]),
        ]
    )

    await chat_mod.bind_mcp_and_run_tool_loop(model, [], max_iterations=4)

    assert seen == ["complete"]


@pytest.mark.asyncio
async def test_no_outcome_recorded_when_no_tools_bound(monkeypatch):
    """No MCP tools → no tool loop → no outcome (it isn't a 'tool loop')."""
    seen = _capture_outcomes(monkeypatch)
    monkeypatch.setattr(chat_mod, "_resolve_chat_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "deeper_notebook.tools.opencode.opencode_enabled", lambda: False
    )
    # v0.8.82 — web_search and scholarly_search are keyless and therefore bound
    # by default, so "no tools bound" now has to disable them too, the same way
    # this test already disables opencode. The assertion below is unchanged.
    monkeypatch.setattr(
        "deeper_notebook.tools.web_search.web_search_enabled", lambda: False
    )
    monkeypatch.setattr(
        "deeper_notebook.tools.scholarly_search.scholarly_search_enabled",
        lambda: False,
    )
    model = _ScriptedModel([_FakeAIMessage([])])

    await chat_mod.bind_mcp_and_run_tool_loop(model, [], max_iterations=4)

    assert seen == []


@pytest.mark.asyncio
async def test_complete_when_tools_bound_but_model_uses_none(monkeypatch):
    """Tools available but the model never calls one → complete (not truncated)."""
    seen = _capture_outcomes(monkeypatch)

    async def _ok(**kwargs):
        return "result"

    monkeypatch.setattr(
        chat_mod,
        "_resolve_chat_tools",
        AsyncMock(return_value=[_make_tool("mcp_search", _ok)]),
    )
    model = _ScriptedModel([_FakeAIMessage([])])  # no tool calls at all

    await chat_mod.bind_mcp_and_run_tool_loop(model, [], max_iterations=4)

    assert seen == ["complete"]
