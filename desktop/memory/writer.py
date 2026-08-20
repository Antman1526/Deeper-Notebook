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
import os
import re
import threading
from typing import Any

from deeper_notebook.environment import resolve_env
from desktop.memory.prompts import (
    EXTRACT_TURN_SYSTEM_PROMPT,
    SUMMARIZE_SESSION_SYSTEM_PROMPT,
    render_extract_user,
    render_extract_user_batch,
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
    return "[…earlier omitted…]\n" + text[-(limit - 30) :]


# --------------------------------------------------------------- retention (v0.8.50)
#
# Phase 5.1a. The memory tables (memory_fact/preference/episode) grew without
# bound — recall caps RESULTS, never ROWS (Finding #3). We enforce a per-table
# ceiling by recency. Pruning is best-effort: it must NEVER block or fail a
# memory write. Triggered at two points so the ceiling holds for every usage
# pattern:
#   * summarize_session (session end) — always; the natural, infrequent boundary.
#   * extract_turn (per turn) — only behind a cheap high-water count gate, so the
#     common path pays nothing but a user who never deletes sessions still stays
#     bounded.
_DEFAULT_KEEP_PER_TABLE = 500
_PRUNE_HIGH_WATER = 1.5  # prune from extract_turn only when a table > keep*this


# --------------------------------------------------------------- batching (v0.8.54)
#
# Phase 5.1b. By default the extractor runs one LLM call per chat turn. With
# DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS=N>1 the worker buffers turns per session and runs ONE
# extraction over the combined transcript every N turns (and drains the buffer
# at session end), collapsing O(turns) extraction calls to O(turns/N) and
# giving the model whole-conversation context. DEFAULT 1 → exactly the prior
# per-turn behaviour (the buffer code path is never entered).
#
# The buffer is process-local to the long-lived surreal_commands worker and
# guarded by a lock (the worker may dispatch commands on multiple threads). A
# worker restart drops any un-flushed tail — acceptable for best-effort memory
# and only relevant when batching is explicitly enabled.
_SESSION_BUFFERS: dict[str, list[tuple[str, str]]] = {}
_BUFFER_LOCK = threading.Lock()
# v0.8.66 (audit MEM-1) — hard cap on the number of buffered sessions so
# abandoned sessions (buffered below the batch threshold and never flushed)
# can't leak the map unboundedly. Each buffer is small (≤ batch turns); 512
# sessions is far above any realistic single-user concurrency. When exceeded we
# evict oldest-inserted sessions — acceptable for best-effort memory.
_MAX_BUFFERED_SESSIONS = 512


def _batch_turns() -> int:
    """Read DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS; default 1 (no batching). Invalid / <1
    values fall back to 1 so a typo can't silently disable extraction."""
    raw = (resolve_env("DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS") or "").strip()
    if not raw:
        return 1
    try:
        n = int(raw)
    except ValueError:
        return 1
    return n if n >= 1 else 1


def _keep_per_table() -> int:
    """Read DEEPER_NOTEBOOK_MEMORY_KEEP_PER_TABLE; fall back to the default on
    missing/invalid/non-positive values."""
    raw = (resolve_env("DEEPER_NOTEBOOK_MEMORY_KEEP_PER_TABLE") or "").strip()
    if not raw:
        return _DEFAULT_KEEP_PER_TABLE
    try:
        n = int(raw)
    except ValueError:
        return _DEFAULT_KEEP_PER_TABLE
    return n if n >= 1 else _DEFAULT_KEEP_PER_TABLE


def prune_memories(
    mem_client, keep_per_table: int | None = None, *, high_water: float | None = None
) -> dict[str, int]:
    """Best-effort retention prune of the memory tables. Returns
    {table: n_deleted} (empty dict if pruning was skipped/unavailable).
    NEVER raises — a retention failure must not take down a memory write.

    `high_water`: when given, only prune if some table's row count exceeds
    `keep_per_table * high_water` (a cheap count() gate). Omit to always
    prune (session-end path).
    """
    keep = keep_per_table if keep_per_table is not None else _keep_per_table()
    store = getattr(mem_client, "vector_store", None)
    if store is None or not hasattr(store, "prune"):
        return {}
    try:
        if high_water is not None and hasattr(store, "count"):
            from desktop.memory.constants import ALL_MEMORY_TABLES

            threshold = int(keep * high_water)
            if not any(store.count(t) > threshold for t in ALL_MEMORY_TABLES):
                return {}  # under the high-water mark — nothing to do
        deleted = store.prune(keep)
        total = sum(deleted.values()) if deleted else 0
        if total:
            import logging

            logging.getLogger(__name__).info(
                "memory retention: pruned %d row(s) to keep=%d per table (%s)",
                total,
                keep,
                deleted,
            )
        return deleted or {}
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "memory retention prune failed (best-effort, ignored): %s",
            exc,
        )
        return {}


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


# v0.7.212 — module-level sentinel raised when a memory backend is
# detected unreachable inside `apply_tool_call`. The per-turn driver
# in `extract_turn` catches this sentinel and stops issuing more
# `mem_client.add()` calls for the same turn. Without the short-
# circuit, a memory-shim-down state caused the worker to spend
# `~60s * N facts` on dead retries before logging and moving on.
class _MemoryBackendUnreachable(Exception):
    """Raised when `apply_tool_call` detects the memory backend
    has gone unreachable for THIS turn. Caller short-circuits."""


# Connection-related exception names we recognise without
# importing httpx/requests at module load (those imports happen
# inside mem0 when actually needed). Compared as `type(exc).__name__`
# to stay loose against version drift.
_BACKEND_DOWN_EXC_NAMES = frozenset(
    {
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "ConnectionError",
        "ConnectionRefusedError",
        "OSError",
    }
)


# --------------------------------------------------------------- confidence (v0.8.55)
#
# Phase 5.1c. The extract prompt already asks the model for a `confidence`
# (0.0-1.0) on each fact/preference, but it was ignored: apply_tool_call never
# read it and surreal_store always persisted 1.0. Now we (a) drop candidates
# below DEEPER_NOTEBOOK_MEMORY_CONFIDENCE_FLOOR and (b) persist the real score (via
# metadata) so retention/recall can rank by it later. DEFAULT floor 0.0 → keep
# everything (unchanged); a missing/garbled score is treated as 1.0 so we never
# silently drop a fact just because the model omitted the number.
def _confidence_floor() -> float:
    raw = (resolve_env("DEEPER_NOTEBOOK_MEMORY_CONFIDENCE_FLOOR") or "").strip()
    if not raw:
        return 0.0
    try:
        v = float(raw)
    except ValueError:
        return 0.0
    return v if 0.0 <= v <= 1.0 else 0.0


def _coerce_confidence(value: Any) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 1.0  # absent/garbled → trust it (don't drop on a missing score)
    return min(1.0, max(0.0, c))


def apply_tool_call(mem_client, call: dict) -> None:
    """Translate one tool call into a mem0.add(...) invocation."""
    name = call.get("name")
    if name not in _NAME_TO_KIND:
        return  # unknown tool
    args = call.get("arguments", {})
    text = args.get("text") or args.get("summary") or ""
    if not text:
        return
    # v0.8.55 — confidence floor: drop candidates the model itself flagged as
    # low-confidence (when an operator raises the floor above the 0.0 default).
    confidence = _coerce_confidence(args.get("confidence"))
    if confidence < _confidence_floor():
        import logging

        logging.getLogger(__name__).debug(
            "apply_tool_call: dropped %s below confidence floor (%.2f < %.2f)",
            _NAME_TO_KIND[name],
            confidence,
            _confidence_floor(),
        )
        return
    kind = _NAME_TO_KIND[name]
    metadata = {
        "kind": kind,
        "scope": args.get("scope", "user"),
        # v0.8.55 — persist the score (read back by surreal_store.insert).
        "confidence": confidence,
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
            # v0.8.66 (audit C1) — infer=False. The Hermes writer ALREADY
            # extracted this fact; with mem0's default infer=True it re-ran its
            # own extraction + update-decision LLM over our curated text (a
            # second pair of local-LLM round-trips per fact AND nondeterministic
            # mutation), and persisted the message under the payload key `data`
            # — which surreal_store.insert wasn't reading, so every row stored
            # text="" and the whole memory subsystem was inert. infer=False
            # stores the text verbatim as `data`; surreal_store now reads it.
            messages=[{"role": "user", "content": text}],
            user_id="local",
            metadata=metadata,
            infer=False,
        )
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "mem_client.add failed for %s (text=%r): %s",
            kind,
            text[:80],
            exc,
        )
        # v0.7.212 — Backend-down short-circuit. mem0's underlying
        # httpx call has a default 60-second read timeout; without
        # this signal, a memory-shim-down state cost the worker
        # `60s * N_facts` per turn (5 facts ≈ 5 minutes pinned).
        # Recognised connection-class exceptions raise our sentinel
        # so the driver loop bails fast. Logical errors (bad
        # payload, mem0 internal assertion) still fall through to
        # the soft-fail path so the rest of the turn's facts can
        # land.
        exc_name = type(exc).__name__
        if exc_name in _BACKEND_DOWN_EXC_NAMES:
            raise _MemoryBackendUnreachable(
                f"memory backend unreachable ({exc_name})"
            ) from exc


def _extract_and_apply(
    *, llm, mem_client, chat_session_id: str, user_content: str
) -> None:
    """v0.8.54 — shared extract→parse→apply→prune core for both the
    single-turn (default) and batched paths. `user_content` is the rendered
    turn(s). Behaviour is byte-for-byte the pre-v0.8.54 extract_turn body —
    only the rendered input varies between the two callers."""
    output = (
        llm.complete(
            system=EXTRACT_TURN_SYSTEM_PROMPT,
            user=user_content,
        )
        or ""
    )
    calls = parse_tool_calls(output)
    if not calls and output.strip():
        # The LLM responded but didn't emit any <tool_call> blocks. Useful
        # debug signal — a chat model with weak instruction-following will
        # show up here.
        import logging

        logging.getLogger(__name__).debug(
            "extract parsed 0 tool calls from %d-char response: %r",
            len(output),
            output[:200],
        )
    for call in calls:
        # source_chat_id isn't a tool argument for extract, but we attach
        # it to metadata so a downstream retriever can attribute the fact.
        call.setdefault("arguments", {}).setdefault("source_chat_id", chat_session_id)
        try:
            apply_tool_call(mem_client, call)
        except _MemoryBackendUnreachable as exc:
            # v0.7.212 — backend is down; remaining facts would each cost up
            # to the underlying http timeout (mem0 default ~60s). Bail fast
            # and let the next turn try again — the shim may be back up then.
            import logging

            logging.getLogger(__name__).warning(
                "extract: %s — aborting remaining %d call(s)",
                exc,
                max(0, len(calls) - calls.index(call) - 1),
            )
            return
    # v0.8.50 — enforce the retention ceiling, but only behind the cheap
    # high-water gate so the per-turn path doesn't pay a select-all every
    # turn. Best-effort: prune_memories never raises.
    prune_memories(mem_client, high_water=_PRUNE_HIGH_WATER)


def extract_turn(
    *, llm, mem_client, chat_session_id: str, user_text: str, assistant_text: str
) -> None:
    """Run the per-turn extractor; write any tool calls into memory.

    v0.8.54 — when DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS=N>1, buffer this turn and only run
    the extraction once N turns have accumulated (drained at session end via
    flush_session_buffer). Default 1 → immediate single-turn extraction,
    identical to the prior behaviour.
    """
    # v0.5.10 — truncate inputs to keep us under any model's context window.
    # 4000 chars ≈ 1000 tokens which fits comfortably even in a 4k-ctx model.
    user_text = _truncate(user_text, _MAX_TURN_CHARS)
    assistant_text = _truncate(assistant_text, _MAX_TURN_CHARS)

    batch = _batch_turns()
    if batch <= 1:
        # Default path — unchanged: extract this turn immediately.
        _extract_and_apply(
            llm=llm,
            mem_client=mem_client,
            chat_session_id=chat_session_id,
            user_content=render_extract_user(user_text, assistant_text),
        )
        return

    # Batched path — buffer this turn; flush a combined extraction at the
    # threshold. Buffer ops are locked (worker may be multi-threaded).
    with _BUFFER_LOCK:
        buf = _SESSION_BUFFERS.setdefault(chat_session_id, [])
        buf.append((user_text, assistant_text))
        # v0.8.66 (audit MEM-1) — evict oldest-inserted sessions beyond the cap
        # so abandoned, never-flushed buffers can't grow the map without bound.
        while len(_SESSION_BUFFERS) > _MAX_BUFFERED_SESSIONS:
            oldest = next(iter(_SESSION_BUFFERS))
            if oldest == chat_session_id:
                break  # never evict the session we're actively buffering
            del _SESSION_BUFFERS[oldest]
        if len(buf) < batch:
            return
        turns = buf[:]
        # v0.8.66 (audit MEM-1) — DELETE the key after a threshold flush rather
        # than leaving an empty list behind (which lingered forever once a
        # session ended). The next turn re-creates it via setdefault.
        _SESSION_BUFFERS.pop(chat_session_id, None)
    _extract_and_apply(
        llm=llm,
        mem_client=mem_client,
        chat_session_id=chat_session_id,
        user_content=render_extract_user_batch(turns),
    )


def flush_session_buffer(*, llm, mem_client, chat_session_id: str) -> None:
    """v0.8.54 — drain any buffered turns for a session through one batched
    extraction. No-op when batching is off / the buffer is empty. Called at
    session end (summarize_session) so end-of-session facts aren't stranded
    below the batch threshold."""
    with _BUFFER_LOCK:
        turns = _SESSION_BUFFERS.pop(chat_session_id, None)
    if not turns:
        return
    _extract_and_apply(
        llm=llm,
        mem_client=mem_client,
        chat_session_id=chat_session_id,
        user_content=render_extract_user_batch(turns),
    )


def summarize_session(
    *, llm, mem_client, chat_session_id: str, transcript: str
) -> None:
    # v0.8.54 — drain any buffered turns (batched extraction, Phase 5.1b)
    # BEFORE summarizing, so facts from the session's tail aren't stranded in
    # the buffer below the batch threshold when the conversation ends. No-op
    # when batching is off.
    flush_session_buffer(
        llm=llm, mem_client=mem_client, chat_session_id=chat_session_id
    )
    # v0.5.10 — keep transcript under ~16k chars (~4k tokens). Long sessions
    # would otherwise blow past the model context.
    transcript = _truncate(transcript, _MAX_TRANSCRIPT_CHARS)

    output = (
        llm.complete(
            system=SUMMARIZE_SESSION_SYSTEM_PROMPT,
            user=render_summarize_user(chat_session_id, transcript),
        )
        or ""
    )
    for call in parse_tool_calls(output):
        apply_tool_call(mem_client, call)
    # v0.8.50 — session end is the natural, infrequent retention boundary:
    # always prune here (no high-water gate). Catches users who DO delete
    # sessions; the extract_turn high-water path covers those who don't.
    prune_memories(mem_client)
