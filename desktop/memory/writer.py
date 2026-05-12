"""Hermes 3 memory writer agent.

Two entry points:
- extract_turn(): runs after each assistant response, extracts explicit
  facts/preferences via short Hermes call.
- summarize_session(): runs at chat session end, produces one episode record.

Both invoke `<llm>.complete(system_prompt, user_prompt)` and parse the
returned text for `<tool_call>...</tool_call>` blocks, then dispatch each to
the mem0 client via apply_tool_call.
"""
from __future__ import annotations

import json
import re
from typing import Any

from desktop.memory.prompts import (
    EXTRACT_TURN_SYSTEM_PROMPT,
    SUMMARIZE_SESSION_SYSTEM_PROMPT,
    render_extract_user,
    render_summarize_user,
)


_TOOL_CALL_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)


def parse_tool_calls(text: str) -> list[dict[str, Any]]:
    """Extract tool-call JSON blocks from Hermes 3 output text.

    Malformed JSON is skipped silently — the writer is best-effort.
    """
    calls = []
    for match in _TOOL_CALL_RE.finditer(text):
        try:
            calls.append(json.loads(match.group(1).strip()))
        except json.JSONDecodeError:
            continue
    return calls


_NAME_TO_KIND = {
    "remember_fact": "fact",
    "remember_preference": "preference",
    "remember_episode": "episode",
}


def apply_tool_call(mem_client, call: dict) -> None:
    """Translate one tool call into a mem0.add(...) invocation."""
    name = call.get("name")
    if name not in _NAME_TO_KIND:
        return  # unknown tool
    args = call.get("arguments", {})
    text = args.get("text") or args.get("summary") or ""
    if not text:
        return
    kind = _NAME_TO_KIND[name]
    metadata = {
        "kind": kind,
        "scope": args.get("scope", "user"),
    }
    if name == "remember_episode":
        metadata["topics"] = args.get("topics", [])
        metadata["outcome"] = args.get("outcome", "no_outcome")
        metadata["source_chat_id"] = args.get("source_chat_id", "")
    mem_client.add(
        messages=text,
        metadata=metadata,
    )


def extract_turn(*, llm, mem_client, chat_session_id: str,
                 user_text: str, assistant_text: str) -> None:
    """Run the per-turn extractor; write any tool calls into memory."""
    output = llm.complete(
        system=EXTRACT_TURN_SYSTEM_PROMPT,
        user=render_extract_user(user_text, assistant_text),
    )
    for call in parse_tool_calls(output):
        # source_chat_id isn't a tool argument for extract_turn, but we attach
        # it to metadata so a downstream retriever can attribute the fact.
        call.setdefault("arguments", {}).setdefault("source_chat_id", chat_session_id)
        apply_tool_call(mem_client, call)


def summarize_session(*, llm, mem_client, chat_session_id: str,
                      transcript: str) -> None:
    output = llm.complete(
        system=SUMMARIZE_SESSION_SYSTEM_PROMPT,
        user=render_summarize_user(chat_session_id, transcript),
    )
    for call in parse_tool_calls(output):
        apply_tool_call(mem_client, call)
