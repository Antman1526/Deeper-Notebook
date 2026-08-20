"""v0.8.54 — Phase 5.1b: batched memory extraction.

By default the extractor runs one LLM call per turn. With
DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS=N>1 the worker buffers turns per session and runs ONE
extraction over the combined transcript every N turns (and drains the buffer
at session end). These tests mock the LLM + mem0 client — no live services.
Default (batch=1) must be byte-for-byte the prior per-turn behaviour.
"""

from __future__ import annotations

import pytest

from desktop.memory import writer as writer_mod
from desktop.memory.prompts import (
    EXTRACT_TURN_SYSTEM_PROMPT,
    SUMMARIZE_SESSION_SYSTEM_PROMPT,
)


class _FakeLLM:
    def __init__(self, output: str = ""):
        self.calls: list[tuple[str, str]] = []
        self.output = output

    def complete(self, system, user):
        self.calls.append((system, user))
        return self.output


class _FakeMemClient:
    """No vector_store attr → prune_memories is a no-op (returns {})."""

    def __init__(self):
        self.added: list[dict] = []

    # v0.8.66 (audit C1) — accept `infer` (writer now passes infer=False).
    def add(self, messages, user_id=None, metadata=None, infer=None):
        self.added.append({"messages": messages, "metadata": metadata, "infer": infer})


_FACT_OUTPUT = '<tool_call>{"name": "remember_fact", "arguments": {"text": "uses Python"}}</tool_call>'


@pytest.fixture(autouse=True)
def _clear_buffers():
    writer_mod._SESSION_BUFFERS.clear()
    yield
    writer_mod._SESSION_BUFFERS.clear()


# ---------------------------------------------------------------------------
# _batch_turns env parsing
# ---------------------------------------------------------------------------


def test_batch_turns_default(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS", raising=False)
    assert writer_mod._batch_turns() == 1


@pytest.mark.parametrize(
    "val,expected",
    [
        ("3", 3),
        ("10", 10),
        ("1", 1),
        ("0", 1),
        ("-2", 1),
        ("garbage", 1),
        ("", 1),
    ],
)
def test_batch_turns_parsing(monkeypatch, val, expected):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS", val)
    assert writer_mod._batch_turns() == expected


# ---------------------------------------------------------------------------
# default (batch=1) path — unchanged per-turn extraction
# ---------------------------------------------------------------------------


def test_default_extracts_every_turn(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS", raising=False)
    llm, mem = _FakeLLM(), _FakeMemClient()
    for i in range(3):
        writer_mod.extract_turn(
            llm=llm,
            mem_client=mem,
            chat_session_id="s1",
            user_text=f"u{i}",
            assistant_text=f"a{i}",
        )
    # One LLM call per turn, all using the extract system prompt.
    assert len(llm.calls) == 3
    assert all(sys == EXTRACT_TURN_SYSTEM_PROMPT for sys, _ in llm.calls)
    # Nothing buffered.
    assert writer_mod._SESSION_BUFFERS == {}


# ---------------------------------------------------------------------------
# batched (batch=N) path
# ---------------------------------------------------------------------------


def test_buffers_until_threshold(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS", "3")
    llm, mem = _FakeLLM(), _FakeMemClient()

    writer_mod.extract_turn(
        llm=llm,
        mem_client=mem,
        chat_session_id="s1",
        user_text="u0",
        assistant_text="a0",
    )
    writer_mod.extract_turn(
        llm=llm,
        mem_client=mem,
        chat_session_id="s1",
        user_text="u1",
        assistant_text="a1",
    )
    # Below threshold → buffered, no LLM call yet.
    assert llm.calls == []
    assert len(writer_mod._SESSION_BUFFERS["s1"]) == 2

    writer_mod.extract_turn(
        llm=llm,
        mem_client=mem,
        chat_session_id="s1",
        user_text="u2",
        assistant_text="a2",
    )
    # Threshold hit → ONE combined extraction over all 3 turns.
    assert len(llm.calls) == 1
    sys, user = llm.calls[0]
    assert sys == EXTRACT_TURN_SYSTEM_PROMPT
    for tok in ("u0", "a0", "u1", "a1", "u2", "a2"):
        assert tok in user
    # v0.8.66 (audit MEM-1) — the session key is now DELETED after a threshold
    # flush (previously left as an empty list that lingered forever).
    assert "s1" not in writer_mod._SESSION_BUFFERS


def test_flush_at_session_end_drains_buffer(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS", "5")
    llm, mem = _FakeLLM(), _FakeMemClient()

    writer_mod.extract_turn(
        llm=llm,
        mem_client=mem,
        chat_session_id="s1",
        user_text="hello",
        assistant_text="hi",
    )
    writer_mod.extract_turn(
        llm=llm,
        mem_client=mem,
        chat_session_id="s1",
        user_text="more",
        assistant_text="ok",
    )
    assert llm.calls == []  # below threshold

    # Session end drains the buffer (extraction) THEN summarizes.
    writer_mod.summarize_session(
        llm=llm,
        mem_client=mem,
        chat_session_id="s1",
        transcript="t",
    )
    systems = [s for s, _ in llm.calls]
    assert EXTRACT_TURN_SYSTEM_PROMPT in systems  # the drained extraction
    assert SUMMARIZE_SESSION_SYSTEM_PROMPT in systems  # the summary
    # The drained extraction's content carried both buffered turns.
    extract_user = next(u for s, u in llm.calls if s == EXTRACT_TURN_SYSTEM_PROMPT)
    assert "hello" in extract_user and "more" in extract_user
    assert "s1" not in writer_mod._SESSION_BUFFERS  # popped


def test_buffers_isolated_per_session(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS", "3")
    llm, mem = _FakeLLM(), _FakeMemClient()
    writer_mod.extract_turn(
        llm=llm, mem_client=mem, chat_session_id="A", user_text="a0", assistant_text="x"
    )
    writer_mod.extract_turn(
        llm=llm, mem_client=mem, chat_session_id="B", user_text="b0", assistant_text="y"
    )
    assert len(writer_mod._SESSION_BUFFERS["A"]) == 1
    assert len(writer_mod._SESSION_BUFFERS["B"]) == 1
    assert llm.calls == []  # neither reached threshold


def test_batched_flush_writes_facts(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS", "2")
    llm, mem = _FakeLLM(output=_FACT_OUTPUT), _FakeMemClient()
    writer_mod.extract_turn(
        llm=llm,
        mem_client=mem,
        chat_session_id="s1",
        user_text="u0",
        assistant_text="a0",
    )
    writer_mod.extract_turn(
        llm=llm,
        mem_client=mem,
        chat_session_id="s1",
        user_text="u1",
        assistant_text="a1",
    )
    # Flush fired → the fact from the (mocked) extraction was written.
    assert len(mem.added) == 1
    assert mem.added[0]["metadata"]["kind"] == "fact"


def test_flush_noop_when_buffer_empty(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS", "3")
    llm, mem = _FakeLLM(), _FakeMemClient()
    # No buffered turns → flush is a no-op (no extraction call).
    writer_mod.flush_session_buffer(llm=llm, mem_client=mem, chat_session_id="none")
    assert llm.calls == []


# ---------------------------------------------------------------------------
# v0.8.66 (audit MEM-1) — buffer-map leak prevention
# ---------------------------------------------------------------------------


def test_threshold_flush_removes_session_key(monkeypatch):
    """After a threshold flush, the session key must be DELETED, not left as an
    empty list that lingers forever once the session ends."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS", "2")
    llm, mem = _FakeLLM(), _FakeMemClient()
    writer_mod.extract_turn(
        llm=llm,
        mem_client=mem,
        chat_session_id="s1",
        user_text="u0",
        assistant_text="a0",
    )
    writer_mod.extract_turn(
        llm=llm,
        mem_client=mem,
        chat_session_id="s1",
        user_text="u1",
        assistant_text="a1",
    )  # threshold → flush
    assert "s1" not in writer_mod._SESSION_BUFFERS, (
        "post-flush session key lingered (empty-list leak)"
    )


def test_buffer_map_bounded_for_abandoned_sessions(monkeypatch):
    """Abandoned sessions (buffered below threshold, never flushed) must not
    grow the map without bound — oldest entries are evicted past the cap."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS", "100")  # never flushes
    monkeypatch.setattr(writer_mod, "_MAX_BUFFERED_SESSIONS", 5)
    llm, mem = _FakeLLM(), _FakeMemClient()
    for i in range(20):
        writer_mod.extract_turn(
            llm=llm,
            mem_client=mem,
            chat_session_id=f"s{i}",
            user_text="u",
            assistant_text="a",
        )
    assert len(writer_mod._SESSION_BUFFERS) <= 5, (
        f"buffer map exceeded cap: {len(writer_mod._SESSION_BUFFERS)}"
    )
    assert llm.calls == []  # nothing reached the threshold
