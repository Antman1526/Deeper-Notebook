"""v0.7.13 — regression tests for source_chat message-history trimming.

source_chat.py concatenated `state["messages"]` verbatim into the LLM
payload (same v0.7.11 bug as chat.py, just in a different graph).
After v0.7.13 it now calls the shared `trim_message_history` util
with `env_var_name="DEEPER_NOTEBOOK_SOURCE_CHAT_HISTORY_CHAR_CAP"` and a smaller
default cap of 8_000 chars (since source_chat already spends part of
the context budget on injected source + insight content per v0.7.12).
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from deeper_notebook.utils import message_history as mh


def _hist(n_turns: int, content_size: int = 300) -> list:
    out: list = []
    for i in range(n_turns):
        out.append(HumanMessage(content=("U%d" % i) + ("." * content_size)))
        out.append(AIMessage(content=("A%d" % i) + ("." * content_size)))
    return out


# ---------------------------------------------------------------------------
# Shared util — keep coverage of the env-var routing
# ---------------------------------------------------------------------------


def test_source_chat_uses_its_own_env_var(monkeypatch):
    """Setting DEEPER_NOTEBOOK_SOURCE_CHAT_HISTORY_CHAR_CAP must affect the
    source-chat trim path even when DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP differs.
    Independent budgets for the two chat graphs is the whole point."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP", "999999")  # huge
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_CHAT_HISTORY_CHAR_CAP", "1000")  # tiny

    msgs = _hist(20, content_size=200)  # ~8_000 chars

    # Chat-style call (huge cap) → no trimming
    chat_out = mh.trim_message_history(
        msgs,
        env_var_name="DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP",
        default_char_cap=12_000,
    )
    assert chat_out == msgs

    # Source-chat-style call (tiny cap) → trimmed
    sc_out = mh.trim_message_history(
        msgs,
        env_var_name="DEEPER_NOTEBOOK_SOURCE_CHAT_HISTORY_CHAR_CAP",
        default_char_cap=8_000,
    )
    assert isinstance(sc_out[0], SystemMessage)
    assert mh.HISTORY_TRUNCATION_MARKER in sc_out[0].content
    assert len(sc_out) - 1 < len(msgs)


def test_source_chat_default_cap_is_8000(monkeypatch):
    """Default cap for source-chat is smaller than for chat (8k vs 12k)
    because the system prompt already eats more budget."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_HISTORY_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP", raising=False)

    msgs = _hist(30, content_size=500)  # ~30k chars

    out = mh.trim_message_history(
        msgs,
        env_var_name="DEEPER_NOTEBOOK_SOURCE_CHAT_HISTORY_CHAR_CAP",
        default_char_cap=8_000,
    )
    assert isinstance(out[0], SystemMessage)
    kept_chars = sum(mh.msg_char_len(m) for m in out[1:])
    assert kept_chars <= 8_000
    # And the last kept is the most-recent original
    assert out[-1] is msgs[-1]


# ---------------------------------------------------------------------------
# Integration with source_chat.py — verify it's actually wired in
# ---------------------------------------------------------------------------

import pytest


@pytest.mark.asyncio
async def test_source_chat_invokes_trim(monkeypatch):
    """Verify _call_model_with_source_context_inner calls
    trim_message_history before building the LLM payload — so the bug
    fix is wired in, not just defined as a helper somewhere.

    v0.7.37 — the inner function is now `async def`. Call-site
    needs `await`; the fake model now exposes `ainvoke`."""
    from deeper_notebook.graphs import source_chat

    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_HISTORY_CHAR_CAP", raising=False)
    # This test owns history trimming, not the separately covered default-on
    # Agent FSM terminal instruction. Keep its two-message payload authority.
    monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", "0")

    trim_calls: list = []

    def fake_trim(messages, *, env_var_name, default_char_cap, minimum_cap=500):
        trim_calls.append(
            {
                "messages": list(messages),
                "env_var_name": env_var_name,
                "default_char_cap": default_char_cap,
            }
        )
        # Return a stub small list so we can pinpoint it in the payload
        return [HumanMessage(content="trimmed")]

    monkeypatch.setattr(source_chat, "trim_message_history", fake_trim)

    sent_payloads: list = []

    class _FakeResp:
        content = "ai reply"
        type = "ai"

        def model_copy(self, update):
            new = _FakeResp()
            new.content = update.get("content", self.content)
            new.type = "ai"
            return new

    class _FakeModel:
        async def ainvoke(self, payload):
            sent_payloads.append(payload)
            return _FakeResp()

    async def fake_provision(*args, **kw):
        return _FakeModel()

    class _FakePrompter:
        def __init__(self, *args, **kw):
            pass

        def render(self, data):
            return "system source-chat prompt"

    # ContextBuilder spins up an async fetch with DB I/O — stub it.
    class _FakeContextBuilder:
        def __init__(self, **kw):
            pass

        async def build(self):
            return {"sources": [], "insights": [], "metadata": {}, "total_tokens": 0}

    monkeypatch.setattr(source_chat, "ContextBuilder", _FakeContextBuilder)
    monkeypatch.setattr(source_chat, "Prompter", _FakePrompter)
    monkeypatch.setattr(source_chat, "provision_langchain_model", fake_provision)
    # v0.8.66 (audit A-M1) — the no-override path now routes through
    # provision_langchain_chat_model (smart-router + privacy gate); stub it too.
    monkeypatch.setattr(source_chat, "provision_langchain_chat_model", fake_provision)

    msgs = _hist(20, content_size=500)
    await source_chat._call_model_with_source_context_inner(
        {
            "source_id": "source:1",
            "messages": msgs,
        },
        {"configurable": {}},
    )

    # Trim was called with the canonical source_chat env var name and 8k default
    assert len(trim_calls) == 1
    assert (
        trim_calls[0]["env_var_name"] == "DEEPER_NOTEBOOK_SOURCE_CHAT_HISTORY_CHAR_CAP"
    )
    assert trim_calls[0]["default_char_cap"] == 8_000
    assert trim_calls[0]["messages"] == msgs

    # The payload contains the trimmed history, not the raw 40-message list
    assert len(sent_payloads) == 1
    payload = sent_payloads[0]
    assert isinstance(payload[0], SystemMessage)
    assert payload[0].content == "system source-chat prompt"
    assert payload[1].content == "trimmed"
    assert len(payload) == 2  # NOT 41 (system + 40 raw)
