"""v0.8.35e — `bind_mcp_and_run_tool_loop` must bound per-tool-call time.

Background: an MCP tool that hangs (slow web fetch, server stuck, hung
network connection) currently blocks the entire chat turn. /chat/execute
has the v0.7.99 outer wrap (`DEEPER_NOTEBOOK_CHAT_TIMEOUT_SEC`, default 300s) so
the request eventually fails, but /chat/stream has no such bound —
streaming relies on client-disconnect detection to halt. A hung tool
freezes the user's stream until they reload the tab.

CLAUDE.md's standing audit explicitly names "missing timeouts" as a
recurring footgun. Wrapping each tool call in `asyncio.wait_for`
bounds the worst-case wait at `DEEPER_NOTEBOOK_MCP_TOOL_TIMEOUT_SEC` (default
30s, env-overridable) per tool — matching the per-call timeout pattern
already used in `api/chat_service.py:_DEFAULT_TIMEOUT` and
`api/routers/chat.py:_chat_timeout`.

These tests:
  1. A tool that completes within the timeout works normally (no
     regression on the happy path).
  2. A tool that hangs past the timeout returns a timeout-error
     message to the model (no exception bubbles up; the loop
     continues so the model can adapt).
  3. The env var overrides the default.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from deeper_notebook.graphs import chat as chat_mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeAIMessage:
    """Stand-in for a LangChain AIMessage that carries tool_calls.

    bind_mcp_and_run_tool_loop reads `.tool_calls` and treats the
    presence of any entries as "model wants another round". We yield
    one round of tool calls on the FIRST invoke and zero on the
    SECOND so the loop terminates after one tool round.
    """

    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.content = ""


class _ScriptedModel:
    """Mocks the LangChain model's `ainvoke` + `bind_tools`.

    Returns the next scripted response on each ainvoke call. `bind_tools`
    is a no-op pass-through so the loop's binding step succeeds. The
    captured `payloads` log each ainvoke's input list for assertions.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.payloads: list = []

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, payload):
        self.payloads.append(payload)
        if not self._responses:
            return _FakeAIMessage(tool_calls=[])
        return self._responses.pop(0)


def _make_tool(name: str, coroutine):
    """Build a fake LangChain Tool. The helper inspects `.name` for the
    tool_lookup dict and calls `.coroutine(**args)` directly (v0.8.10)."""

    class _T:
        pass

    t = _T()
    t.name = name
    t.coroutine = coroutine
    return t


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fast_tool_completes_normally(monkeypatch):
    """Happy path: a tool that returns immediately works as before.

    Regression guard for the v0.8.35e timeout wrap — we MUST NOT
    accidentally turn a fast tool into a timeout-string by mis-setting
    the env var or wrapping incorrectly.
    """
    fast_tool_invoked = [False]

    async def _fast(**kwargs):
        fast_tool_invoked[0] = True
        return "fast result"

    tools = [_make_tool("mcp_search", _fast)]
    monkeypatch.setattr(
        chat_mod, "_resolve_chat_tools",
        AsyncMock(return_value=tools),
    )

    model = _ScriptedModel([
        # Round 1: model emits one tool call
        _FakeAIMessage(tool_calls=[{
            "name": "mcp_search", "args": {"q": "hi"}, "id": "call-1",
        }]),
        # Round 2: model returns final answer (no more tool calls)
        _FakeAIMessage(tool_calls=[]),
    ])

    ai, _captures = await chat_mod.bind_mcp_and_run_tool_loop(model, [])

    assert fast_tool_invoked[0] is True
    # The second-round payload must include the ToolMessage feedback
    # whose content is the tool's return string (NOT a timeout error).
    second_payload = model.payloads[1]
    tool_msgs = [m for m in second_payload if type(m).__name__ == "ToolMessage"]
    assert len(tool_msgs) == 1
    # v0.8.66 (audit S-3/A-5) — tool output is wrapped in an untrusted-data
    # fence; the raw result is contained inside it (not the whole message).
    assert "fast result" in tool_msgs[0].content
    assert "UNTRUSTED TOOL OUTPUT" in tool_msgs[0].content


@pytest.mark.asyncio
async def test_hanging_tool_times_out_and_feeds_error_to_model(monkeypatch):
    """A tool that hangs past the timeout must NOT block the loop.

    The wrap (`asyncio.wait_for`) raises `TimeoutError`; the existing
    `except Exception as tool_exc` branch then converts that into a
    `ToolMessage` describing the timeout so the model can adapt
    (apologize, try a different tool, give up) instead of the stream
    freezing forever.
    """
    async def _hang(**kwargs):
        # Sleep way longer than the test's tiny timeout. asyncio.wait_for
        # cancels this coroutine when it fires.
        await asyncio.sleep(60)
        return "should never get here"

    # Force a tiny timeout via the env var so the test runs fast.
    monkeypatch.setenv("DEEPER_NOTEBOOK_MCP_TOOL_TIMEOUT_SEC", "0.05")

    tools = [_make_tool("mcp_search", _hang)]
    monkeypatch.setattr(
        chat_mod, "_resolve_chat_tools",
        AsyncMock(return_value=tools),
    )

    model = _ScriptedModel([
        _FakeAIMessage(tool_calls=[{
            "name": "mcp_search", "args": {"q": "hi"}, "id": "call-1",
        }]),
        _FakeAIMessage(tool_calls=[]),
    ])

    # Wrap the whole loop in its OWN outer bound so a regression in
    # the timeout wrap can't hang the test.
    ai, _captures = await asyncio.wait_for(
        chat_mod.bind_mcp_and_run_tool_loop(model, []),
        timeout=5.0,
    )

    # Loop completed (didn't hang).
    assert ai is not None

    # The second-round payload must include a ToolMessage whose content
    # mentions the timeout — that's the model's feedback channel.
    second_payload = model.payloads[1]
    tool_msgs = [m for m in second_payload if type(m).__name__ == "ToolMessage"]
    assert len(tool_msgs) == 1
    body = tool_msgs[0].content.lower()
    assert "mcp_search" in body
    # Either the literal word "timeout" or "timed out" — be lenient on
    # exact phrasing so a future copy edit doesn't break the test.
    assert "time" in body, (
        f"Expected ToolMessage to mention a timeout, got: "
        f"{tool_msgs[0].content!r}"
    )


@pytest.mark.asyncio
async def test_default_timeout_when_env_var_unset(monkeypatch):
    """When DEEPER_NOTEBOOK_MCP_TOOL_TIMEOUT_SEC is unset the wrap must still
    apply — using the default. We verify the default is non-trivial
    (> 1s) so legitimate slow tools (web fetch, large MCP search) are
    not falsely timed-out by an aggressive default."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_MCP_TOOL_TIMEOUT_SEC", raising=False)

    # A tool that sleeps 0.5s — well under any sensible default.
    async def _slow_but_ok(**kwargs):
        await asyncio.sleep(0.5)
        return "ok"

    tools = [_make_tool("mcp_search", _slow_but_ok)]
    monkeypatch.setattr(
        chat_mod, "_resolve_chat_tools",
        AsyncMock(return_value=tools),
    )

    model = _ScriptedModel([
        _FakeAIMessage(tool_calls=[{
            "name": "mcp_search", "args": {}, "id": "call-1",
        }]),
        _FakeAIMessage(tool_calls=[]),
    ])

    ai, _ = await asyncio.wait_for(
        chat_mod.bind_mcp_and_run_tool_loop(model, []),
        timeout=10.0,
    )
    assert ai is not None
    # The model saw the real tool result, not a timeout error.
    second_payload = model.payloads[1]
    tool_msgs = [m for m in second_payload if type(m).__name__ == "ToolMessage"]
    # v0.8.66 (audit S-3/A-5) — result fenced as untrusted data.
    assert "ok" in tool_msgs[0].content
    assert "UNTRUSTED TOOL OUTPUT" in tool_msgs[0].content
    assert "timed out" not in tool_msgs[0].content.lower()
