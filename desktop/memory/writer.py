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

# v0.5.10 — hard caps on inputs to keep us under any chat-model context.
# Per-turn extract uses just last turn; both fields capped individually.
# Session summary caps the whole transcript.
_MAX_TURN_CHARS = 4000
_MAX_TRANSCRIPT_CHARS = 16_000


def _truncate(text: str, limit: int) -> str:
    """Truncate from the END (keep the most-recent material). One-line marker
    so the LLM knows truncation happened."""
    if not text or len(text) <= limit:
        return text or ""
    return "[…earlier omitted…]\n" + text[-(limit - 30):]


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
    # v0.5.10 — defensive try/except. If mem0 raises (embed server down,
    # invalid payload, etc.), we lose this fact but the rest of the
    # turn's facts still get a chance to land. Without this guard, the
    # first failed add aborts the whole turn's extraction.
    try:
        # mem0 2.x requires every add to be scoped to a user/agent/run.
        # We're a single-user desktop app — pin to "local".
        mem_client.add(
            messages=text,
            user_id="local",
            metadata=metadata,
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "mem_client.add failed for %s (text=%r): %s",
            kind, text[:80], exc,
        )


def extract_turn(*, llm, mem_client, chat_session_id: str,
                 user_text: str, assistant_text: str) -> None:
    """Run the per-turn extractor; write any tool calls into memory."""
    # v0.5.10 — truncate inputs to keep us under any model's context window.
    # 4000 chars ≈ 1000 tokens which fits comfortably even in a 4k-ctx model.
    user_text = _truncate(user_text, _MAX_TURN_CHARS)
    assistant_text = _truncate(assistant_text, _MAX_TURN_CHARS)

    output = llm.complete(
        system=EXTRACT_TURN_SYSTEM_PROMPT,
        user=render_extract_user(user_text, assistant_text),
    ) or ""
    calls = parse_tool_calls(output)
    if not calls and output.strip():
        # The LLM responded but didn't emit any <tool_call> blocks. Useful
        # debug signal — a chat model with weak instruction-following will
        # show up here.
        import logging
        logging.getLogger(__name__).debug(
            "extract_turn parsed 0 tool calls from %d-char response: %r",
            len(output), output[:200],
        )
    for call in calls:
        # source_chat_id isn't a tool argument for extract_turn, but we attach
        # it to metadata so a downstream retriever can attribute the fact.
        call.setdefault("arguments", {}).setdefault("source_chat_id", chat_session_id)
        apply_tool_call(mem_client, call)


def summarize_session(*, llm, mem_client, chat_session_id: str,
                      transcript: str) -> None:
    # v0.5.10 — keep transcript under ~16k chars (~4k tokens). Long sessions
    # would otherwise blow past the model context.
    transcript = _truncate(transcript, _MAX_TRANSCRIPT_CHARS)

    output = llm.complete(
        system=SUMMARIZE_SESSION_SYSTEM_PROMPT,
        user=render_summarize_user(chat_session_id, transcript),
    ) or ""
    for call in parse_tool_calls(output):
        apply_tool_call(mem_client, call)
