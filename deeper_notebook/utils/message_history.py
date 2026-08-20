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

from deeper_notebook.environment import resolve_env

# A marker injected at the front of the trimmed list so the model
# sees that earlier turns existed and were elided rather than
# hallucinating a nonexistent earlier exchange. Same string used for
# both the chat and source-chat callers.
HISTORY_TRUNCATION_MARKER = (
    "[Earlier conversation turns were elided to fit the model's context "
    "budget. Resume the conversation from the messages that follow.]"
)


def _env_int(name: str, default: int, minimum: int) -> int:
    raw = resolve_env(name)
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


def _truncate_message_content(msg: Any, cap_chars: int) -> Any:
    """Return a copy of `msg` whose content is truncated to `cap_chars`.

    v0.7.66 — used by trim_message_history to defend local LLMs
    against a single giant user paste. The always-keep-most-recent
    rule previously let one >100k-char message through whole, which
    blew past llama-cpp-python's `--n_ctx` (16k default for the
    bundled chat server) and crashed mid-stream. We now apply a
    per-message char cap and append a clear "[…truncated…]" marker
    so the model sees that content was cut.

    Multimodal content (lists of blocks) is collapsed to its text
    form before truncation. We construct a new message of the same
    runtime type via `model_copy` when available (BaseMessage path),
    otherwise return a plain dict shape that downstream code accepts.
    """
    if hasattr(msg, "content"):
        c = msg.content
    elif isinstance(msg, dict):
        c = msg.get("content", "")
    else:
        c = msg
    text = c if isinstance(c, str) else str(c)
    if len(text) <= cap_chars:
        return msg
    keep = max(cap_chars - 64, 1)  # leave room for the marker
    truncated = text[:keep] + (
        "\n\n[…content truncated to fit the model's per-message "
        "budget; the original was %d characters…]" % len(text)
    )
    # Try to preserve the message type — BaseMessage subclasses have
    # `model_copy`. Falling back to dict is fine for both source/chat
    # graphs which already handle dicts in msg_char_len.
    if hasattr(msg, "model_copy"):
        try:
            return msg.model_copy(update={"content": truncated})
        except Exception:
            pass
    if isinstance(msg, dict):
        out = dict(msg)
        out["content"] = truncated
        return out
    return truncated


def trim_message_history(
    messages: list,
    *,
    env_var_name: str = "DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP",
    default_char_cap: int = 12_000,
    minimum_cap: int = 500,
    per_message_cap_env: str = "DEEPER_NOTEBOOK_CHAT_MESSAGE_CHAR_CAP",
    default_per_message_cap: int = 24_000,
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
        per_message_cap_env: Env var for the per-MESSAGE char cap (set
            independently of the history cap). Default 24k chars ≈ 6k
            tokens — well within local LLM headroom even on a 16k
            context after subtracting the system prompt and the
            response budget.
        default_per_message_cap: Fallback if env unset/invalid.

    Behavior:
        - Empty input → returned unchanged.
        - Each message individually capped to per_message_cap chars;
          the original character count is preserved in the truncation
          marker so the model is aware content was cut.
        - Total under history cap → returned unchanged (no history marker).
        - Total over history cap → oldest messages dropped, most-recent
          message ALWAYS preserved (dropping the current user turn
          would break the conversation), and a SystemMessage marker
          prepended IFF messages were actually dropped.

    Order is preserved across trimming (drop from front, never reorder).
    """
    if not messages:
        return messages

    # v0.7.66 — apply per-message cap FIRST. Previously a single
    # >100k-char paste survived because we "always keep the most
    # recent message"; the always-keep rule is still correct, but
    # the kept message needs to fit on its own. DEEPER_NOTEBOOK_CHAT_MESSAGE_CHAR_CAP
    # lets capable hardware raise it.
    per_msg_cap = _env_int(
        per_message_cap_env, default_per_message_cap, minimum=minimum_cap
    )
    truncated_count = 0
    capped_messages: list = []
    for m in messages:
        capped = _truncate_message_content(m, per_msg_cap)
        if capped is not m:
            truncated_count += 1
        capped_messages.append(capped)
    if truncated_count:
        logger.warning(
            f"Trimmed {truncated_count} message(s) to per-message cap "
            f"{per_msg_cap} chars (env={per_message_cap_env}). "
            f"Raise {per_message_cap_env} on capable hardware."
        )
    messages = capped_messages

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
            # exceeds the cap (it's already been per-message-capped).
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
