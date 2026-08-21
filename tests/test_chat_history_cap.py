"""v0.7.11 — regression tests for chat-history trimming.

`deeper_notebook.graphs.chat.call_model_with_messages` used to concatenate
the entire persisted `state["messages"]` list into the LLM payload at
every turn. LangGraph's `add_messages` reducer is append-only, so a
long-running session's history grew without bound and — combined with
the hardcoded `max_tokens=8192` output reservation — overflowed a
16k-context local server (the v0.7.8 default) after ~30 turns.

These tests pin the new `_trim_message_history` contract.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from deeper_notebook.graphs import chat

# ---------------------------------------------------------------------------
# _msg_char_len — defensive against many message shapes
# ---------------------------------------------------------------------------


def test_msg_char_len_handles_message_objects():
    assert chat._msg_char_len(HumanMessage(content="hello")) == 5
    assert chat._msg_char_len(AIMessage(content="hi there")) == 8


def test_msg_char_len_handles_dict():
    assert chat._msg_char_len({"content": "abcdef", "type": "user"}) == 6


def test_msg_char_len_handles_string():
    assert chat._msg_char_len("plain") == 5


def test_msg_char_len_handles_non_str_content():
    """Multi-modal content lists are stringified defensively."""
    msg = HumanMessage(content=[{"type": "text", "text": "x"}])
    # Don't pin exact length — just verify it didn't crash and returned int
    assert isinstance(chat._msg_char_len(msg), int)
    assert chat._msg_char_len(msg) > 0


# ---------------------------------------------------------------------------
# _trim_message_history — pure function
# ---------------------------------------------------------------------------


def _make_history(n_turns: int, content_size: int = 200) -> list:
    """Build a realistic alternating user/AI history."""
    out: list = []
    for i in range(n_turns):
        out.append(HumanMessage(content=("U%d" % i) + ("." * content_size)))
        out.append(AIMessage(content=("A%d" % i) + ("." * content_size)))
    return out


def test_trim_returns_empty_when_input_empty(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP", raising=False)
    assert chat._trim_message_history([]) == []


def test_trim_returns_untouched_when_under_cap(monkeypatch):
    """Under the cap → no marker, no slicing, same list returned."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP", raising=False)
    msgs = _make_history(3, content_size=100)  # ~6 × 102 = 612 chars
    out = chat._trim_message_history(msgs)
    assert out == msgs
    assert not any(
        isinstance(m, SystemMessage) and chat._HISTORY_TRUNCATION_MARKER in m.content
        for m in out
    )


def test_trim_drops_oldest_when_over_cap(monkeypatch):
    """Over the cap → oldest dropped, most-recent kept, marker prepended."""
    monkeypatch.delenv(
        "DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP", raising=False
    )  # 12_000 default
    msgs = _make_history(50, content_size=500)  # ~50_000 chars total
    out = chat._trim_message_history(msgs)

    # First element is the truncation marker
    assert isinstance(out[0], SystemMessage)
    assert chat._HISTORY_TRUNCATION_MARKER in out[0].content

    # Most-recent original message preserved as the last element
    assert out[-1] is msgs[-1]

    # Total kept content is under cap (excluding marker)
    kept_chars = sum(chat._msg_char_len(m) for m in out[1:])
    assert kept_chars <= 12_000

    # Fewer messages than we started with
    assert len(out) - 1 < len(msgs)


def test_trim_keeps_last_message_even_if_oversize(monkeypatch):
    """A single oversize current-turn message is KEPT (we never drop
    the most recent), but as of v0.7.66 its content is now truncated
    to the per-message cap so a 50k-char paste can't blow past a
    local LLM's 16k context. Dropping the message would still break
    the conversation; truncating it preserves the turn while
    respecting the model's budget.
    """
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_MESSAGE_CHAR_CAP", raising=False)
    huge = HumanMessage(content="X" * 30_000)  # 2.5x the history cap
    out = chat._trim_message_history([huge])
    # Still exactly one message, no history marker prepended (nothing dropped).
    assert len(out) == 1
    assert isinstance(out[0], HumanMessage)
    # Content was truncated to the default 24k per-message cap.
    assert len(out[0].content) < 30_000
    assert len(out[0].content) <= 24_000 + 200  # marker padding
    # Marker is appended so the model knows content was cut.
    assert "content truncated" in out[0].content


def test_trim_respects_env_var_higher(monkeypatch):
    """Capable hardware: raise the cap, more history fits."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP", "60000")
    msgs = _make_history(30, content_size=500)  # ~30_000 chars
    out = chat._trim_message_history(msgs)
    # Fits under 60k → untouched
    assert out == msgs


def test_trim_respects_env_var_lower(monkeypatch):
    """Constrained hardware: lower the cap, more aggressive trimming."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP", "2000")
    msgs = _make_history(10, content_size=500)
    out = chat._trim_message_history(msgs)
    # Marker present + fewer messages
    assert isinstance(out[0], SystemMessage)
    assert chat._HISTORY_TRUNCATION_MARKER in out[0].content
    assert len(out) - 1 < len(msgs)


def test_trim_falls_back_on_invalid_env(monkeypatch):
    """Garbage env value → default 12_000 cap applied."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP", "not-an-int")
    msgs = _make_history(50, content_size=500)
    out = chat._trim_message_history(msgs)
    # Trimming happened (default cap kicked in, not the bogus value)
    assert isinstance(out[0], SystemMessage)
    kept_chars = sum(chat._msg_char_len(m) for m in out[1:])
    assert kept_chars <= 12_000


def test_trim_falls_back_when_cap_too_low(monkeypatch):
    """A cap below 500 is almost certainly a typo — fall back to default
    so we don't ship a useless single-token history."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP", "50")
    msgs = _make_history(50, content_size=500)
    out = chat._trim_message_history(msgs)
    # Default applied → many messages survive (not just 1-2)
    assert len(out) > 5


def test_trim_preserves_message_order(monkeypatch):
    """The order of kept messages must match the original order — we
    drop from the front, never reorder."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP", raising=False)
    msgs = _make_history(40, content_size=500)
    out = chat._trim_message_history(msgs)
    kept = out[1:]  # skip the marker
    # Each kept message should appear in original order
    indices = [msgs.index(m) for m in kept]
    assert indices == sorted(indices)
    # And the last kept is the most-recent original
    assert kept[-1] is msgs[-1]


# ---------------------------------------------------------------------------
# call_model_with_messages integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_model_invokes_trimming(monkeypatch):
    """Verify the chat-graph node calls _trim_message_history before
    building its LLM payload — so the bug fix is wired in, not just
    defined as a helper.

    v0.7.37 — call_model_with_messages is now `async def`. The model's
    LLM round trip is `await model.ainvoke()` instead of
    `model.invoke()`. The trimmer is invoked the same way; only the
    test's call-site needs `await`."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP", raising=False)
    # This test owns history trimming, not the separately covered default-on
    # Agent FSM terminal instruction. Keep its two-message payload authority.
    monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_FSM", "0")

    called_with: list = []

    def fake_trim(messages):
        called_with.append(list(messages))
        # Return a known small list so we can assert against the payload
        return [HumanMessage(content="trimmed")]

    sent_payloads: list = []

    class _FakeResp:
        content = "ai response"

        def model_copy(self, update):
            new = _FakeResp()
            new.content = update.get("content", self.content)
            new.type = "ai"
            return new

    _FakeResp.type = "ai"

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
            return "system"

    monkeypatch.setattr(chat, "_trim_message_history", fake_trim)
    monkeypatch.setattr(chat, "Prompter", _FakePrompter)
    monkeypatch.setattr(chat, "provision_langchain_model", fake_provision)
    # v0.8.46c — Since v0.8.0 Phase 3 Task 12, the chat node's
    # no-model-override path calls `provision_langchain_chat_model`
    # (the smart-route wrapper), NOT `provision_langchain_model`
    # directly. With model_override=None below, the test hits that
    # wrapper — so patching only `provision_langchain_model` left the
    # real wrapper running, which calls `model_manager.get_defaults()`
    # → a live SurrealDB connect → failure. Patch the wrapper too so
    # the trimming-assertion path is exercised without any DB/network.
    # (This test broke at v0.8.0 but was never in a curated sweep, so
    # the full-suite run is what surfaced it.)
    monkeypatch.setattr(chat, "provision_langchain_chat_model", fake_provision)

    msgs = _make_history(20, content_size=500)
    await chat.call_model_with_messages(
        {
            "messages": msgs,
            "notebook": None,
            "context": None,
            "context_config": None,
            "model_override": None,
        },
        {"configurable": {}},
    )

    # The trimmer received the original messages
    assert called_with == [msgs]
    # The payload starts with SystemMessage (chat/system prompt) then the
    # trimmed history (just one message in our stub)
    assert len(sent_payloads) == 1
    payload = sent_payloads[0]
    assert isinstance(payload[0], SystemMessage)
    assert payload[0].content == "system"
    assert payload[1].content == "trimmed"
    # And critically: the raw 40-message history did NOT land in the payload
    assert len(payload) == 2
