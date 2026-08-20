from __future__ import annotations

from unittest.mock import MagicMock

from desktop.memory.writer import (
    apply_tool_call,
    extract_turn,
    parse_tool_calls,
    summarize_session,
)


def test_parse_tool_calls_finds_single_call():
    raw = (
        '<tool_call>{"name": "remember_fact", '
        '"arguments": {"text": "x", "scope": "user", "confidence": 0.8}}'
        "</tool_call>"
    )
    calls = parse_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0]["name"] == "remember_fact"


def test_parse_tool_calls_finds_multiple_calls():
    raw = (
        '<tool_call>{"name": "remember_fact", "arguments": {"text": "a", "scope": "user", "confidence": 1}}</tool_call>'
        "\n some chat \n"
        '<tool_call>{"name": "remember_preference", "arguments": {"text": "b", "scope": "user", "confidence": 1}}</tool_call>'
    )
    calls = parse_tool_calls(raw)
    assert len(calls) == 2
    assert calls[1]["name"] == "remember_preference"


def test_parse_tool_calls_returns_empty_on_no_calls():
    assert parse_tool_calls("No tool calls here.") == []


def test_parse_tool_calls_skips_malformed_blocks():
    raw = "<tool_call>not valid json</tool_call>"
    assert parse_tool_calls(raw) == []


def test_apply_tool_call_remember_fact_invokes_memory_add():
    mem_client = MagicMock()
    apply_tool_call(
        mem_client,
        {
            "name": "remember_fact",
            "arguments": {
                "text": "user likes coffee",
                "scope": "user",
                "confidence": 0.9,
            },
        },
    )
    mem_client.add.assert_called_once()
    kwargs = mem_client.add.call_args.kwargs
    assert kwargs.get("messages") or kwargs.get("data") or mem_client.add.call_args.args


def test_extract_turn_calls_llm_then_applies_each_tool_call(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.complete.return_value = (
        '<tool_call>{"name": "remember_fact", '
        '"arguments": {"text": "x", "scope": "user", "confidence": 0.9}}'
        "</tool_call>"
    )
    mem_client = MagicMock()
    extract_turn(
        llm=fake_llm,
        mem_client=mem_client,
        chat_session_id="chat:1",
        user_text="hello",
        assistant_text="hi",
    )
    fake_llm.complete.assert_called_once()
    mem_client.add.assert_called_once()


def test_summarize_session_emits_episode():
    fake_llm = MagicMock()
    fake_llm.complete.return_value = (
        '<tool_call>{"name": "remember_episode", "arguments": '
        '{"summary": "discussed coffee", "topics": ["coffee"], '
        '"outcome": "exploration", "source_chat_id": "chat:1"}}'
        "</tool_call>"
    )
    mem_client = MagicMock()
    summarize_session(
        llm=fake_llm,
        mem_client=mem_client,
        chat_session_id="chat:1",
        transcript="user: ...\nassistant: ...",
    )
    mem_client.add.assert_called_once()
