"""v0.8.53 — Phase 5.3b: agent-FSM completion gate on the ask graph.

When DEEPER_NOTEBOOK_AGENT_FSM is on and no search produced grounded content,
`write_final_answer` declares CLARIFY (and skips the synthesis LLM call)
instead of letting the model hallucinate from an empty context. Default off
→ unchanged behaviour.
"""

from __future__ import annotations

import pytest

from deeper_notebook.graphs import ask
from deeper_notebook.graphs.agent_fsm import AgentState


def _mock_synthesis(monkeypatch):
    """Patch the synthesis path; return a call counter so tests can assert
    whether the LLM was invoked."""
    called = {"provision": 0, "invoke": 0}

    class _FakePrompter:
        def __init__(self, *a, **k):
            pass

        def render(self, data):
            return "SYSTEM PROMPT"

    async def _fake_provision(*a, **k):
        called["provision"] += 1
        return object()

    class _FakeMsg:
        content = "synthesized answer"

    async def _fake_invoke(model, payload, *, node):
        called["invoke"] += 1
        return _FakeMsg()

    monkeypatch.setattr(ask, "Prompter", _FakePrompter)
    monkeypatch.setattr(ask, "provision_langchain_model", _fake_provision)
    monkeypatch.setattr(ask, "_ask_invoke", _fake_invoke)
    return called


@pytest.mark.asyncio
async def test_clarify_when_fsm_on_and_no_answers(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", "on")
    called = _mock_synthesis(monkeypatch)

    out = await ask.write_final_answer(
        {"question": "q", "answers": []}, {"configurable": {}}
    )

    assert out["agent_state"] == AgentState.CLARIFY.value
    assert "couldn't find" in out["final_answer"].lower()
    # Crucially: the LLM was NOT asked to synthesize from empty context.
    assert called["provision"] == 0
    assert called["invoke"] == 0


@pytest.mark.asyncio
async def test_clarify_when_answers_are_only_whitespace(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", "on")
    called = _mock_synthesis(monkeypatch)

    out = await ask.write_final_answer(
        {"question": "q", "answers": ["", "   ", "\n\t"]}, {"configurable": {}}
    )

    assert out["agent_state"] == AgentState.CLARIFY.value
    assert called["invoke"] == 0


@pytest.mark.asyncio
async def test_synthesis_when_fsm_on_and_grounded(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", "on")
    called = _mock_synthesis(monkeypatch)

    out = await ask.write_final_answer(
        {"question": "q", "answers": ["a real grounded answer"]},
        {"configurable": {}},
    )

    assert out["agent_state"] == AgentState.COMPLETE.value
    assert out["final_answer"] == "synthesized answer"
    assert called["invoke"] == 1


@pytest.mark.asyncio
async def test_fsm_off_synthesizes_even_with_no_answers(monkeypatch):
    """Default off: behaviour is unchanged — synthesize regardless, and emit
    no agent_state tag."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_AGENT_FSM", raising=False)
    called = _mock_synthesis(monkeypatch)

    out = await ask.write_final_answer(
        {"question": "q", "answers": []}, {"configurable": {}}
    )

    assert "agent_state" not in out
    assert out["final_answer"] == "synthesized answer"
    assert called["invoke"] == 1


def test_agent_fsm_enabled_parsing(monkeypatch):
    for on in ("on", "1", "true", "yes", "ON", "True"):
        monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", on)
        assert ask._agent_fsm_enabled() is True
    for off in ("", "off", "0", "false", "no", "nonsense"):
        monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", off)
        assert ask._agent_fsm_enabled() is False
    monkeypatch.delenv("DEEPER_NOTEBOOK_AGENT_FSM", raising=False)
    assert ask._agent_fsm_enabled() is False
