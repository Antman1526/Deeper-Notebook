"""v0.8.60 — Phase 5.3c-full: agent-FSM integration in the chat tool loop.

By default and when DEEPER_NOTEBOOK_AGENT_FSM is on, the loop (a) tells the model it may declare a
terminal <state>, and (b) classifies + surfaces the terminal state via
agent_state_out — the valuable case being CLARIFY (the model paused to ask
the user). Explicit off → no <state> injection, agent_state_out untouched.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from deeper_notebook.graphs import chat as chat_mod


class _Msg:
    def __init__(self, tool_calls=None, content=""):
        self.tool_calls = tool_calls or []
        self.content = content


class _Model:
    def __init__(self, responses):
        self._r = list(responses)
        self.payloads: list = []

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, payload):
        self.payloads.append(payload)
        return self._r.pop(0) if self._r else _Msg()


def _make_tool(name, coroutine):
    class _T:
        pass

    t = _T()
    t.name = name
    t.coroutine = coroutine
    return t


async def _ok(**kwargs):
    return "result"


def _no_tools(monkeypatch):
    monkeypatch.setattr(chat_mod, "_resolve_chat_tools", AsyncMock(return_value=[]))


def _instruction_in(payload) -> bool:
    return any(
        getattr(m, "content", None) == chat_mod._AGENT_FSM_TOOL_LOOP_INSTRUCTION
        for m in payload
    )


@pytest.mark.asyncio
async def test_clarify_classified_when_fsm_on(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", "on")
    _no_tools(monkeypatch)
    model = _Model([_Msg(content="Which file did you mean?\n<state>clarify</state>")])
    out: dict = {}

    await chat_mod.bind_mcp_and_run_tool_loop(model, [], agent_state_out=out)

    assert out["agent_state"] == "clarify"
    # The <state> prompt instruction was injected into the model payload.
    assert _instruction_in(model.payloads[0])


@pytest.mark.asyncio
async def test_complete_classified_on_declared_complete(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", "on")
    _no_tools(monkeypatch)
    model = _Model([_Msg(content="All done.\n<state>complete</state>")])
    out: dict = {}
    await chat_mod.bind_mcp_and_run_tool_loop(model, [], agent_state_out=out)
    assert out["agent_state"] == "complete"


@pytest.mark.asyncio
async def test_complete_when_no_state_tag(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", "on")
    _no_tools(monkeypatch)
    model = _Model([_Msg(content="Here is the answer.")])
    out: dict = {}
    await chat_mod.bind_mcp_and_run_tool_loop(model, [], agent_state_out=out)
    assert out["agent_state"] == "complete"


@pytest.mark.asyncio
async def test_malformed_terminal_state_falls_back_to_complete(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_AGENT_FSM", raising=False)
    _no_tools(monkeypatch)
    model = _Model([_Msg(content="Here is the answer.\n<state>not-a-state</state>")])
    out: dict = {}

    await chat_mod.bind_mcp_and_run_tool_loop(model, [], agent_state_out=out)

    assert out["agent_state"] == "complete"
    assert _instruction_in(model.payloads[0])


@pytest.mark.asyncio
async def test_truncated_classified_when_loop_hits_cap(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", "on")
    monkeypatch.setattr(
        chat_mod,
        "_resolve_chat_tools",
        AsyncMock(return_value=[_make_tool("mcp_search", _ok)]),
    )
    # Always requests a tool → loop force-stops at max_iterations.
    model = _Model(
        [
            _Msg(tool_calls=[{"name": "mcp_search", "args": {}, "id": f"c{i}"}])
            for i in range(5)
        ]
    )
    out: dict = {}
    await chat_mod.bind_mcp_and_run_tool_loop(
        model, [], max_iterations=2, agent_state_out=out
    )
    assert out["agent_state"] == "truncated"


@pytest.mark.asyncio
async def test_fsm_defaults_on_and_injects_terminal_state_contract(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_AGENT_FSM", raising=False)
    _no_tools(monkeypatch)
    model = _Model([_Msg(content="answer <state>clarify</state>")])
    out: dict = {}
    await chat_mod.bind_mcp_and_run_tool_loop(model, [], agent_state_out=out)

    assert out["agent_state"] == "clarify"
    assert _instruction_in(model.payloads[0])


@pytest.mark.asyncio
async def test_fsm_explicit_off_no_injection_no_state(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", "0")
    _no_tools(monkeypatch)
    model = _Model([_Msg(content="answer <state>clarify</state>")])
    out: dict = {}
    await chat_mod.bind_mcp_and_run_tool_loop(model, [], agent_state_out=out)
    # Explicit off → no classification, no prompt injection (payload passed through as-is).
    assert out == {}
    assert not _instruction_in(model.payloads[0])
    assert model.payloads[0] == []


def test_agent_fsm_enabled_parsing(monkeypatch):
    for on in ("on", "1", "true", "yes", "ON"):
        monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", on)
        assert chat_mod._agent_fsm_enabled() is True
    for off in ("", "off", "0", "false", "no"):
        monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", off)
        assert chat_mod._agent_fsm_enabled() is False
    monkeypatch.delenv("DEEPER_NOTEBOOK_AGENT_FSM", raising=False)
    assert chat_mod._agent_fsm_enabled() is True
