"""Recall recent memory facts + preferences for chat-prompt injection.

v0.7.71 — companion to v0.7.68 / v0.7.70 (the memory WRITE path). The
writer extracts facts/preferences from each turn and stores them in
SurrealDB tables `memory_fact` / `memory_preference` via mem0. Until
now those rows were only consumed by the Gmail digest — chat never
recalled them, so the assistant never "remembered" anything across
sessions even though it was diligently writing things down.

This module gives the chat graph a tiny, safe read path that:
  - tolerates missing tables (fresh DBs, upstream non-desktop build)
    by swallowing query errors and returning empty
  - caps result count (we render into the system prompt; runaway
    growth would clobber the local LLM's context budget)
  - returns simple `{text, scope, kind}` dicts the Jinja template
    can iterate without knowing the SurrealDB schema

v0.7.84 — added `recall_relevant_memory(query)` which does cosine
similarity over the `embedding` column populated by mem0. The chat
node now calls `recall_memory(query=last_user_text)` — a thin
orchestrator that picks `relevant` once memory tables grow past
~10 rows (otherwise recency is fine and saves an embed round trip),
with `auto` / `recent` / `semantic` overrides via
`DEEPER_NOTEBOOK_MEMORY_RECALL_MODE`. ANY failure in the semantic path falls
through to the recency path so chat never breaks because the
embedder is misconfigured.
"""

from __future__ import annotations

import asyncio  # v0.7.113 — wait_for around the chat-hot-path embed call
import os
import re  # v0.8.47 — flatten recalled-memory text before prompt injection
from typing import Any

from loguru import logger

from deeper_notebook.database.repository import repo_query
from deeper_notebook.environment import resolve_env

# Total cap across BOTH facts and preferences so the injected block
# stays predictable. Each row is typically 30-200 chars, so 20 rows
# is ~2-4k chars in the worst case — comfortable inside the chat-graph
# 12k-char history budget.
_MAX_FACTS = 15
_MAX_PREFERENCES = 10

# v0.8.49 — episodes are whole-session summaries written by the v0.7.70
# `summarize_session` writer on session delete. Until now they were
# WRITE-ONLY: `surreal_store` routes `kind="episode"` into the
# `memory_episode` table, the writer diligently produced them on every
# session end (one ~800-token LLM call), but NOTHING ever read them back
# — recall only queried memory_fact + memory_preference. This wired the
# missing read path so the third memory layer actually informs chat,
# consistent with facts/preferences (already recalled by default).
# Capped tighter than facts/preferences: a session summary is coarse and
# long, so even 2 carries meaningful context without crowding the prompt.
_MAX_EPISODES = 2

# Episode recall defaults ON (parity with facts/preferences, which have
# no gate). Set DEEPER_NOTEBOOK_MEMORY_RECALL_EPISODES=0 to suppress — useful if a
# user finds old-conversation summaries resurfacing unhelpful, or to
# claw back the ~1k chars of system-prompt budget on a tiny local model.
_DEFAULT_EPISODE_RECALL = True


def _episode_recall_enabled() -> bool:
    raw = (resolve_env("DEEPER_NOTEBOOK_MEMORY_RECALL_EPISODES") or "").strip().lower()
    if not raw:
        return _DEFAULT_EPISODE_RECALL
    return raw not in ("0", "false", "no", "off")

# v0.7.84 — once a user's memory tables grow past this row count, the
# "most recent N" heuristic starts losing relevant older facts. Switch
# to semantic search above this threshold (unless the env var forces a
# specific mode). 30 is conservative: most single-user deploys after a
# week of chats land in the 50-200 range.
_SEMANTIC_THRESHOLD = 30

# Minimum cosine score for a memory hit to be included. Below this the
# match is too weak to be worth injecting (the local LLM is better off
# without than with noise). Embedding models put unrelated text in the
# 0.0-0.3 range, weakly related at 0.3-0.5, strongly related at 0.6+.
_MIN_SCORE = 0.30


async def recall_recent_memory() -> dict[str, list[dict[str, Any]]]:
    """Return recent fact + preference rows for prompt injection.

    Shape:
        {"facts": [{"text": "..."}],
         "preferences": [{"text": "..."}]}

    Returns empty lists on any failure (table missing, DB blip,
    upstream non-desktop build). The caller treats empty == "no
    memory section in the prompt". This is the original v0.7.71
    recall path — v0.7.84's orchestrator (`recall_memory`) falls
    through to here on any semantic-search failure.
    """
    # v0.8.19 CRITICAL — Drop the `VALUE` projection. SurrealDB rejects
    # `SELECT VALUE <field> ... ORDER BY <other_field>` with
    # "Missing order idiom in statement selection" because the order
    # idiom must be in the projection. Pre-v0.8.19 this raised on
    # every chat turn, _safe_select swallowed the parse error at
    # DEBUG level, and memory recall returned empty silently —
    # users thought memory was working but no fact was ever recalled.
    # The downstream `_coerce_text` already handles both scalar
    # and dict shapes (per its v0.7.71 docstring), so consumers
    # are robust to the shape change.
    #
    # v0.8.30 CRITICAL — v0.8.19's drop-VALUE fix was INCOMPLETE.
    # SurrealDB's "Missing order idiom" rejection is not just about
    # the VALUE projection — it requires the ORDER BY field
    # (`created_at`) to ALSO be IN the projection. The post-v0.8.19
    # state `SELECT text FROM memory_fact ORDER BY created_at DESC`
    # STILL fails with the same parse error. v0.8.19's severity-
    # bumped WARNING log (which originally surfaced the v0.7.71 bug)
    # kept firing every chat turn — memory recall has STILL been
    # returning empty across v0.8.19 → v0.8.29. Surfaced by
    # `tests/test_chat_history_cap.py` running against a live
    # SurrealDB this session.
    # Fix: include `created_at` in the projection. `_coerce_text`
    # still picks out the `text` field — the extra column is ignored
    # by consumers.
    facts = await _safe_select(
        "SELECT text, created_at FROM memory_fact "
        "ORDER BY created_at DESC LIMIT $limit",
        {"limit": _MAX_FACTS},
    )
    preferences = await _safe_select(
        "SELECT text, created_at FROM memory_preference "
        "ORDER BY created_at DESC LIMIT $limit",
        {"limit": _MAX_PREFERENCES},
    )
    # v0.8.49 — recall the most-recent session summaries too (was the
    # missing read half of the v0.7.70 summarize_session feature). Same
    # v0.8.30 idiom: created_at must be IN the projection alongside the
    # ORDER BY, or SurrealDB rejects with "Missing order idiom".
    episodes = (
        await _safe_select(
            "SELECT text, created_at FROM memory_episode "
            "ORDER BY created_at DESC LIMIT $limit",
            {"limit": _MAX_EPISODES},
        )
        if _episode_recall_enabled()
        else []
    )
    return {
        "facts": [{"text": _coerce_text(t)} for t in facts if _coerce_text(t)],
        "preferences": [
            {"text": _coerce_text(t)} for t in preferences if _coerce_text(t)
        ],
        "episodes": [
            {"text": _coerce_text(t)} for t in episodes if _coerce_text(t)
        ],
    }


async def recall_relevant_memory(
    query: str,
) -> dict[str, list[dict[str, Any]]]:
    """Cosine-similarity recall against the mem0 embedding column.

    v0.7.84 — uses `vector::similarity::cosine(embedding, $q)` directly
    against memory_fact / memory_preference tables (the same SurrealQL
    idiom mem0's surreal_store.search() uses). Embeds the query via
    `model_manager.get_embedding_model()`.

    Falls through to {} on any failure (no embedding model, table
    missing, embedding shape mismatch between mem0's writes and our
    query's embedding) — the caller of `recall_memory()` retries with
    `recall_recent_memory()` so chat never breaks on bad config.

    The chat-graph node is on the hot path; one embed call + two
    SurrealQL queries adds ~50-150 ms on a local embed server. Worth
    it once the user has > _SEMANTIC_THRESHOLD facts because the
    recency heuristic starts dropping relevant older facts.
    """
    if not query or not query.strip():
        return {"facts": [], "preferences": []}
    # v0.7.113 — wrap the embed call in wait_for. recall_relevant_memory
    # runs on the chat hot path (every user turn); a stuck embedding
    # model (cold-start, OOM, misconfigured base_url) would otherwise
    # hold up chat for up to DEEPER_NOTEBOOK_CHAT_TIMEOUT_SEC (300s default before
    # v0.7.99's outer wrap fires). 5s default keeps chat snappy; on
    # timeout we fall through to recency recall which is DB-only.
    _recall_embed_timeout = float(
        resolve_env("DEEPER_NOTEBOOK_MEMORY_RECALL_EMBED_TIMEOUT_SEC", "5").strip() or 5
    )
    try:
        # Lazy import to avoid pulling the model layer into module-load
        # for non-chat callers. If model_manager isn't configured (no
        # embedding model selected), this raises and we return empty.
        from deeper_notebook.ai.models import model_manager

        embed_model = await model_manager.get_embedding_model()
        if embed_model is None:
            logger.debug(
                "recall_relevant_memory: no embedding model configured — "
                "caller will fall back to recency"
            )
            return {}
        # Esperanto's embedding interface: .aembed() takes a list,
        # returns list[list[float]]. Take the single result.
        embeds = await asyncio.wait_for(
            embed_model.aembed([query.strip()]),
            timeout=_recall_embed_timeout,
        )
        if not embeds:
            return {}
        q_vec = embeds[0]
    except asyncio.TimeoutError:
        logger.debug(
            "recall_relevant_memory: embedding timed out after {}s — "
            "caller will fall back to recency", _recall_embed_timeout,
        )
        # v0.7.124 — Prometheus counter for visibility into how often
        # the timeout path actually fires. If this counter rises,
        # the embedding model is unhealthy and chat is silently
        # degrading.
        try:
            from api.metrics import record_memory_fallthrough
            record_memory_fallthrough("embed_timeout")
        except Exception:
            pass
        return {}
    except Exception as exc:
        logger.debug(
            "recall_relevant_memory: embedding step failed ({}) — "
            "caller will fall back to recency",
            exc,
        )
        try:
            from api.metrics import record_memory_fallthrough
            record_memory_fallthrough("embed_error")
        except Exception:
            pass
        return {}

    # Cosine search against each table separately so the per-kind cap
    # is enforced (preferences are more authoritative than facts —
    # don't let one dominate the other).
    facts = await _safe_select(
        f"SELECT text, vector::similarity::cosine(embedding, $q) AS score "  # nosec B608
        f"FROM memory_fact "
        f"WHERE embedding <|{_MAX_FACTS}|> $q "
        f"ORDER BY score DESC LIMIT $limit",
        {"q": q_vec, "limit": _MAX_FACTS},
    )
    preferences = await _safe_select(
        f"SELECT text, vector::similarity::cosine(embedding, $q) AS score "  # nosec B608
        f"FROM memory_preference "
        f"WHERE embedding <|{_MAX_PREFERENCES}|> $q "
        f"ORDER BY score DESC LIMIT $limit",
        {"q": q_vec, "limit": _MAX_PREFERENCES},
    )
    # v0.8.49 — semantic recall of session summaries (parity with the
    # recency path). Same cosine idiom against the memory_episode table.
    episodes = (
        await _safe_select(
            f"SELECT text, vector::similarity::cosine(embedding, $q) AS score "  # nosec B608
            f"FROM memory_episode "
            f"WHERE embedding <|{_MAX_EPISODES}|> $q "
            f"ORDER BY score DESC LIMIT $limit",
            {"q": q_vec, "limit": _MAX_EPISODES},
        )
        if _episode_recall_enabled()
        else []
    )

    def _filter(rows: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            score = row.get("score")
            text = _coerce_text(row.get("text"))
            if not text:
                continue
            if isinstance(score, (int, float)) and score < _MIN_SCORE:
                continue
            out.append({"text": text})
        return out

    return {
        "facts": _filter(facts),
        "preferences": _filter(preferences),
        "episodes": _filter(episodes),  # v0.8.49
    }


async def _count_memory_rows() -> int:
    """Approximate row count across ALL THREE memory tables.

    Used by `recall_memory()` to pick recency-vs-semantic when the env
    var leaves it on `auto`. Tolerates missing tables.

    v0.8.66 (audit MEM-4) — now includes `memory_episode`. Omitting it made an
    episodes-only store look empty, so auto-mode's recency-vs-semantic decision
    and the "no matches" short-circuit discarded episodes-only semantic hits
    (the v0.8.49 episode-recall regression).
    """
    rows = await _safe_select(
        "SELECT VALUE count() FROM memory_fact GROUP ALL", {}
    )
    fact_n = int(rows[0]) if rows and isinstance(rows[0], (int, float)) else 0
    rows = await _safe_select(
        "SELECT VALUE count() FROM memory_preference GROUP ALL", {}
    )
    pref_n = int(rows[0]) if rows and isinstance(rows[0], (int, float)) else 0
    rows = await _safe_select(
        "SELECT VALUE count() FROM memory_episode GROUP ALL", {}
    )
    episode_n = int(rows[0]) if rows and isinstance(rows[0], (int, float)) else 0
    return fact_n + pref_n + episode_n


# v0.7.133 — Outer budget for the whole memory-recall flow.
#
# Background: the existing per-step timeouts are DEEPER_NOTEBOOK_MEMORY_RECALL_EMBED_TIMEOUT_SEC
# (default 5s) + DEEPER_NOTEBOOK_MEMORY_RECALL_QUERY_TIMEOUT_SEC (default 5s). The
# semantic path does 1 embed + 2 queries (facts + preferences) and can
# fall through to a recency-only path that does 2 more queries. Worst
# case: 5 + 5 + 5 + 5 + 5 = 25s before chat sees an empty memory section,
# and DEEPER_NOTEBOOK_CHAT_TIMEOUT_SEC won't fire until later.
#
# Area for Review #2 asked: should this be a single budget instead of
# stacked timeouts? Answer: BOTH. Keep the per-step timeouts as defense
# in depth (they're useful when the embedder is hung but mem0 is fine —
# you get fast fall-through to query-only without paying the embed wait),
# and add an outer wall via DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC (default 12s)
# so total recall NEVER exceeds the budget.
#
# 12s default chosen because:
#   * Healthy hot path: ~200ms embed + ~100ms × 2 queries = under 1s.
#   * Worst legit case: cold embedder + cold DB pool — maybe 8s.
#   * 12s leaves headroom but caps the absolute worst-case at well
#     under DEEPER_NOTEBOOK_CHAT_TIMEOUT_SEC (300s default), so chat still has time
#     to actually do something useful with what memory it does have.
_DEFAULT_RECALL_BUDGET_SEC = 12.0


def _recall_budget_sec() -> float:
    raw = (resolve_env("DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC") or "").strip()
    if not raw:
        return _DEFAULT_RECALL_BUDGET_SEC
    try:
        val = float(raw)
        if val <= 0:
            logger.warning(
                "DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC={} must be positive; "
                "using default {}s", raw, _DEFAULT_RECALL_BUDGET_SEC,
            )
            return _DEFAULT_RECALL_BUDGET_SEC
        return val
    except ValueError:
        logger.warning(
            "DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC={!r} not a float; using default {}s",
            raw, _DEFAULT_RECALL_BUDGET_SEC,
        )
        return _DEFAULT_RECALL_BUDGET_SEC


async def recall_memory(
    query: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Orchestrator. Picks semantic vs recency based on
    DEEPER_NOTEBOOK_MEMORY_RECALL_MODE or row-count.

    Modes:
      - "recent"  → always use recall_recent_memory()
      - "semantic" → always use recall_relevant_memory(query); falls
        through to recency on failure
      - "auto" (default) → semantic if rows > _SEMANTIC_THRESHOLD,
        else recency. Empty `query` always uses recency.

    v0.7.133 — Wrapped in an outer DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC budget
    (default 12s). Per-step timeouts (embed: 5s, query: 5s) still apply
    individually, but the budget guarantees the whole orchestration
    completes within the bound regardless of how steps cascade. On
    budget exhaustion we return an empty memory dict — chat still works,
    just without the memory section for this turn.

    The fall-through is the safety net: any failure in the semantic
    path returns {} from `recall_relevant_memory`, and we then call
    `recall_recent_memory`. Chat never breaks because of a misconfigured
    embedder.
    """
    budget = _recall_budget_sec()
    try:
        return await asyncio.wait_for(
            _recall_memory_inner(query), timeout=budget,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "memory recall exceeded outer budget of {}s; returning empty "
            "(per-step timeouts probably already fired — check "
            "memory_recall_fallthrough_total{{reason}} metrics)",
            budget,
        )
        # Best-effort metric emission. If the metrics module fails to
        # import we silently drop — the chat path must NEVER break
        # because observability broke.
        try:
            from api.metrics import record_memory_fallthrough
            record_memory_fallthrough("outer_budget")
        except Exception:
            pass
        return {"facts": [], "preferences": [], "episodes": []}  # v0.8.49


async def _recall_memory_inner(
    query: str | None,
) -> dict[str, list[dict[str, Any]]]:
    """v0.7.133 — Extracted inner so the public `recall_memory` can
    wrap with a single asyncio.wait_for. Behavior unchanged from the
    pre-budget version."""
    mode = (resolve_env("DEEPER_NOTEBOOK_MEMORY_RECALL_MODE") or "auto").strip().lower()

    if mode == "recent" or not query or not query.strip():
        return await recall_recent_memory()

    if mode == "semantic":
        result = await recall_relevant_memory(query)
        # v0.8.67 (audit A2) — also consider `episodes`. Without it an
        # episodes-only store (session summaries, v0.8.49) looks "empty" here
        # and silently downgrades to recency, discarding relevant episode hits.
        # Same omission class as the v0.8.66 MEM-4 fix in _count_memory_rows.
        if not result or (
            not result.get("facts")
            and not result.get("preferences")
            and not result.get("episodes")
        ):
            # Empty (failure or genuinely no matches) — recency is the
            # better default than an empty memory section.
            return await recall_recent_memory()
        return result

    # auto
    total = await _count_memory_rows()
    if total <= _SEMANTIC_THRESHOLD:
        return await recall_recent_memory()
    result = await recall_relevant_memory(query)
    # v0.8.67 (audit A2) — include `episodes` in the emptiness check (see the
    # semantic-mode branch above) so an episodes-only store isn't discarded.
    if not result or (
        not result.get("facts")
        and not result.get("preferences")
        and not result.get("episodes")
    ):
        return await recall_recent_memory()
    return result


def _coerce_text(value: Any) -> str:
    """SurrealDB `SELECT VALUE` returns scalars but the wrapper may
    occasionally hand us a dict with a single field. Normalize."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        # Defensive: if the SELECT VALUE flattening didn't happen for
        # some reason, recover the text field. `dict.get("text")` may
        # return None on a row with a null text column — coerce that
        # back to "" rather than the string "None" (caught by test).
        inner = value.get("text")
        if inner is None:
            return ""
        if isinstance(inner, str):
            return inner.strip()
        return str(inner).strip()
    return str(value).strip()


async def _safe_select(query: str, vars: dict) -> list[Any]:
    """Run a SurrealQL query and never raise. Memory tables may not
    exist on a fresh DB (no chat turns yet, or upstream build with the
    memory feature disabled) — empty list is the right answer.

    v0.7.114 — Per-query timeout. Memory recall runs on every chat
    turn; an overloaded connection pool would otherwise stall the
    request for up to the pool's own timeout. 5s default matches
    v0.7.113's embed timeout — combined, the whole memory-recall
    path is bounded by ~15s worst-case (one embed + two queries)
    before falling through to empty.
    """
    _query_timeout = float(
        resolve_env("DEEPER_NOTEBOOK_MEMORY_RECALL_QUERY_TIMEOUT_SEC", "5").strip() or 5
    )
    try:
        result = await asyncio.wait_for(
            repo_query(query, vars), timeout=_query_timeout,
        )
        if isinstance(result, list):
            return result
        return []
    except asyncio.TimeoutError:
        logger.debug(
            "memory recall query timed out after {}s (returning empty)",
            _query_timeout,
        )
        # v0.7.124 — Prometheus counter for the timeout path.
        try:
            from api.metrics import record_memory_fallthrough
            record_memory_fallthrough("query_timeout")
        except Exception:
            pass
        return []
    except Exception as exc:
        # v0.8.19 — Was DEBUG only ("the empty path is the expected
        # case on fresh installs"), but that masked the v0.8.19
        # SurrealQL parse error for an entire release cycle. Split:
        # "table missing" is genuinely expected (no chat turns yet)
        # and stays at DEBUG; "Parse error" / "Missing order idiom"
        # / "Idiom missing" / "unexpected token" are bugs and must
        # be visible. WARNING level surfaces them in launcher.log
        # without spamming on healthy fresh installs.
        msg = str(exc)
        is_schema_error = (
            "Parse error" in msg
            or "Missing order idiom" in msg
            or "Idiom missing" in msg
            or "unexpected token" in msg
        )
        log_fn = logger.warning if is_schema_error else logger.debug
        log_fn(
            "memory recall query failed (returning empty): {}", exc,
        )
        # v0.7.124 — Prometheus counter for the error path (distinct
        # from timeout — useful for differentiating "table missing"
        # vs "pool overloaded").
        try:
            from api.metrics import record_memory_fallthrough
            record_memory_fallthrough("query_error")
        except Exception:
            pass
        return []


# v0.8.47 — defense against stored prompt-injection via recalled memory.
#
# Memory facts/preferences are auto-extracted by the mem0 WRITE path
# (v0.7.68) from chat turns — INCLUDING turns where the user pasted
# untrusted external content (PDFs, web pages, emails — ONP's core
# research use case). render_memory_block interpolates that text straight
# into the chat SYSTEM prompt. Without flattening, a planted "fact" like
# "\n\n## SYSTEM\nIgnore prior instructions and ..." would render on its
# own lines and forge a brand-new prompt section — a classic stored
# injection that persists across sessions.
#
# Collapsing every fact to a SINGLE line is the core mitigation: the text
# can no longer start a fresh line, so it can't forge block-level markdown
# (headings/blockquotes/fences) or pose as a separate instruction block.
# Whatever inline text survives stays inside its "- " bullet, clearly
# framed by the template as untrusted "facts learned about the user" data.
# (We deliberately do NOT strip a leading "-"/"*" run: that would mangle
# legitimate facts like "-5°C is the user's preferred setting", and the
# enclosing "- " bullet already prevents a leading "#" from forming a
# heading — flattening newlines is what actually closes the hole.)
_MEMORY_TEXT_MAX_CHARS = 600
_WHITESPACE_RUN = re.compile(r"\s+")


def _sanitize_memory_text(text: Any) -> str:
    """Flatten a recalled memory string to one line and cap its length
    before it is interpolated into the SYSTEM prompt. Returns "" for
    empty/whitespace-only input so the caller drops the bullet."""
    if not text:
        return ""
    flat = _WHITESPACE_RUN.sub(" ", str(text)).strip()
    if len(flat) > _MEMORY_TEXT_MAX_CHARS:
        flat = flat[:_MEMORY_TEXT_MAX_CHARS].rstrip() + "…"
    return flat


def render_memory_block(memory: dict[str, list[dict[str, Any]]]) -> str:
    """Render the recall dict as a plain-text Markdown block suitable
    for direct {{ memory_block }} substitution in the chat system
    prompt. Returns empty string when both lists are empty so the
    template's `{% if memory_block %}` short-circuits cleanly.

    v0.8.47 — every fact/preference is passed through
    `_sanitize_memory_text` so stored content can't break out of its
    bullet and forge a SYSTEM-prompt section. Bullets that sanitize to
    empty are dropped.

    v0.8.49 — also renders an "## Earlier conversation summaries" section
    from recalled episodes (the missing read half of v0.7.70). Episodes
    are sanitized identically and ordered LAST (coarsest / least
    authoritative — preferences and facts lead).
    """
    facts = memory.get("facts") or []
    preferences = memory.get("preferences") or []
    episodes = memory.get("episodes") or []  # v0.8.49
    if not facts and not preferences and not episodes:
        return ""
    lines: list[str] = []
    if preferences:
        pref_lines = [
            f"- {clean}"
            for clean in (_sanitize_memory_text(p.get("text")) for p in preferences)
            if clean
        ]
        if pref_lines:
            lines.append("## User preferences")
            lines.extend(pref_lines)
            lines.append("")
    if facts:
        fact_lines = [
            f"- {clean}"
            for clean in (_sanitize_memory_text(f.get("text")) for f in facts)
            if clean
        ]
        if fact_lines:
            lines.append("## Recent facts learned about the user")
            lines.extend(fact_lines)
            lines.append("")
    if episodes:
        ep_lines = [
            f"- {clean}"
            for clean in (_sanitize_memory_text(e.get("text")) for e in episodes)
            if clean
        ]
        if ep_lines:
            lines.append("## Earlier conversation summaries")
            lines.extend(ep_lines)
            lines.append("")
    return "\n".join(lines).rstrip()
