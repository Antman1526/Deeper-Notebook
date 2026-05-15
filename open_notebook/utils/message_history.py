"""Shared message-history trimming for chat graphs.

v0.7.13 — extracted from v0.7.11's `chat.py._trim_message_history` so
the same logic protects both `chat.py` and `source_chat.py` (and any
future chat-style graph) without duplication.

Why a shared util: each graph has its own context budget (source_chat
also spends tokens on injected source/insight content; the regular
chat graph spends them on notebook summaries), so we parameterize the
env-var name and default cap rather than hardcoding them. Other
behaviors — always preserve the most-recent message, prepend a
SystemMessage marker only when messages were actually dropped, log a
warning on truncation — are identical and live here.
"""
from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import SystemMessage
from loguru import logger


# A marker injected at the front of the trimmed list so the model
# sees that earlier turns existed and were elided rather than
# hallucinating a nonexistent earlier exchange. Same string used for
# both the chat and source-chat callers.
HISTORY_TRUNCATION_MARKER = (
    "[Earlier conversation turns were elided to fit the model's context "
    "budget. Resume the conversation from the messages that follow.]"
)


def _env_int(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        val = int(raw)
        if val < minimum:
            logger.warning(
                f"{name}={raw} is below minimum {minimum}; using default {default}"
            )
            return default
        return val
    except ValueError:
        logger.warning(f"{name}={raw!r} is not an int; using default {default}")
        return default


def msg_char_len(msg: Any) -> int:
    """Approximate the prompt-character footprint of one message.

    Handles BaseMessage objects (with .content), plain dicts, raw
    strings, and multi-modal content lists — chat graphs receive
    whatever the router and checkpoint store hand them.
    """
    if hasattr(msg, "content"):
        c = msg.content
    elif isinstance(msg, dict):
        c = msg.get("content", "")
    else:
        c = msg
    if isinstance(c, str):
        return len(c)
    return len(str(c))


def trim_message_history(
    messages: list,
    *,
    env_var_name: str = "ONP_CHAT_HISTORY_CHAR_CAP",
    default_char_cap: int = 12_000,
    minimum_cap: int = 500,
) -> list:
    """Drop oldest messages until the total fits under the char cap.

    Args:
        messages: Persisted message history (list of BaseMessage or dicts).
        env_var_name: Env var used to override the per-call cap; lets
            chat.py and source_chat.py have independent budgets.
        default_char_cap: Fallback cap if env var unset or invalid.
        minimum_cap: Smallest legal env-override value. Below this is
            treated as a typo and falls back to default — protects
            against e.g. "50" that would ship a single-token history.

    Behavior:
        - Empty input → returned unchanged.
        - Total under cap → returned unchanged (no marker added).
        - Total over cap → oldest messages dropped, most-recent
          message ALWAYS preserved (dropping the current user turn
          would break the conversation), and a SystemMessage marker
          prepended IFF messages were actually dropped.
        - A single oversize current-turn message that triggers the
          always-keep-last path is NOT a history truncation — no
          marker. Per-message truncation is handled elsewhere.

    Order is preserved across trimming (drop from front, never reorder).
    """
    if not messages:
        return messages
    cap = _env_int(env_var_name, default_char_cap, minimum=minimum_cap)
    total = sum(msg_char_len(m) for m in messages)
    if total <= cap:
        return messages

    kept: list = []
    running = 0
    for m in reversed(messages):
        mlen = msg_char_len(m)
        if not kept:
            # Always keep the most recent message, even if it alone
            # exceeds the cap.
            kept.append(m)
            running += mlen
            continue
        if running + mlen > cap:
            break
        kept.append(m)
        running += mlen
    kept.reverse()
    dropped = len(messages) - len(kept)
    if dropped == 0:
        return kept
    logger.warning(
        f"Chat history truncated: kept {len(kept)}/{len(messages)} messages "
        f"(~{running}/{total} chars; cap={cap}, env={env_var_name}). "
        f"Set {env_var_name} to raise."
    )
    return [SystemMessage(content=HISTORY_TRUNCATION_MARKER)] + kept
