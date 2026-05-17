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
`ONP_MEMORY_RECALL_MODE`. ANY failure in the semantic path falls
through to the recency path so chat never breaks because the
embedder is misconfigured.
"""

from __future__ import annotations

import asyncio  # v0.7.113 — wait_for around the chat-hot-path embed call
import os
from typing import Any

from loguru import logger

from open_notebook.database.repository import repo_query

# Total cap across BOTH facts and preferences so the injected block
# stays predictable. Each row is typically 30-200 chars, so 20 rows
# is ~2-4k chars in the worst case — comfortable inside the chat-graph
# 12k-char history budget.
_MAX_FACTS = 15
_MAX_PREFERENCES = 10

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
    facts = await _safe_select(
        "SELECT VALUE text FROM memory_fact "
        "ORDER BY created_at DESC LIMIT $limit",
        {"limit": _MAX_FACTS},
    )
    preferences = await _safe_select(
        "SELECT VALUE text FROM memory_preference "
        "ORDER BY created_at DESC LIMIT $limit",
        {"limit": _MAX_PREFERENCES},
    )
    return {
        "facts": [{"text": _coerce_text(t)} for t in facts if _coerce_text(t)],
        "preferences": [
            {"text": _coerce_text(t)} for t in preferences if _coerce_text(t)
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
    # hold up chat for up to ONP_CHAT_TIMEOUT_SEC (300s default before
    # v0.7.99's outer wrap fires). 5s default keeps chat snappy; on
    # timeout we fall through to recency recall which is DB-only.
    _recall_embed_timeout = float(
        os.environ.get("ONP_MEMORY_RECALL_EMBED_TIMEOUT_SEC", "5").strip() or 5
    )
    try:
        # Lazy import to avoid pulling the model layer into module-load
        # for non-chat callers. If model_manager isn't configured (no
        # embedding model selected), this raises and we return empty.
        from open_notebook.ai.models import model_manager

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
        return {}
    except Exception as exc:
        logger.debug(
            "recall_relevant_memory: embedding step failed ({}) — "
            "caller will fall back to recency",
            exc,
        )
        return {}

    # Cosine search against each table separately so the per-kind cap
    # is enforced (preferences are more authoritative than facts —
    # don't let one dominate the other).
    facts = await _safe_select(
        "SELECT text, vector::similarity::cosine(embedding, $q) AS score "
        "FROM memory_fact "
        "ORDER BY score DESC LIMIT $limit",
        {"q": q_vec, "limit": _MAX_FACTS},
    )
    preferences = await _safe_select(
        "SELECT text, vector::similarity::cosine(embedding, $q) AS score "
        "FROM memory_preference "
        "ORDER BY score DESC LIMIT $limit",
        {"q": q_vec, "limit": _MAX_PREFERENCES},
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

    return {"facts": _filter(facts), "preferences": _filter(preferences)}


async def _count_memory_rows() -> int:
    """Approximate row count across both memory tables.

    Used by `recall_memory()` to pick recency-vs-semantic when the env
    var leaves it on `auto`. Tolerates missing tables.
    """
    rows = await _safe_select(
        "SELECT VALUE count() FROM memory_fact GROUP ALL", {}
    )
    fact_n = int(rows[0]) if rows and isinstance(rows[0], (int, float)) else 0
    rows = await _safe_select(
        "SELECT VALUE count() FROM memory_preference GROUP ALL", {}
    )
    pref_n = int(rows[0]) if rows and isinstance(rows[0], (int, float)) else 0
    return fact_n + pref_n


async def recall_memory(
    query: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Orchestrator. Picks semantic vs recency based on
    ONP_MEMORY_RECALL_MODE or row-count.

    Modes:
      - "recent"  → always use recall_recent_memory()
      - "semantic" → always use recall_relevant_memory(query); falls
        through to recency on failure
      - "auto" (default) → semantic if rows > _SEMANTIC_THRESHOLD,
        else recency. Empty `query` always uses recency.

    The fall-through is the safety net: any failure in the semantic
    path returns {} from `recall_relevant_memory`, and we then call
    `recall_recent_memory`. Chat never breaks because of a misconfigured
    embedder.
    """
    mode = (os.environ.get("ONP_MEMORY_RECALL_MODE") or "auto").strip().lower()

    if mode == "recent" or not query or not query.strip():
        return await recall_recent_memory()

    if mode == "semantic":
        result = await recall_relevant_memory(query)
        if not result or (not result.get("facts") and not result.get("preferences")):
            # Empty (failure or genuinely no matches) — recency is the
            # better default than an empty memory section.
            return await recall_recent_memory()
        return result

    # auto
    total = await _count_memory_rows()
    if total <= _SEMANTIC_THRESHOLD:
        return await recall_recent_memory()
    result = await recall_relevant_memory(query)
    if not result or (not result.get("facts") and not result.get("preferences")):
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
        os.environ.get("ONP_MEMORY_RECALL_QUERY_TIMEOUT_SEC", "5").strip() or 5
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
        return []
    except Exception as exc:
        # debug — every chat turn would log otherwise; the empty path
        # is the expected case on fresh installs.
        logger.debug("memory recall query failed (returning empty): {}", exc)
        return []


def render_memory_block(memory: dict[str, list[dict[str, Any]]]) -> str:
    """Render the recall dict as a plain-text Markdown block suitable
    for direct {{ memory_block }} substitution in the chat system
    prompt. Returns empty string when both lists are empty so the
    template's `{% if memory_block %}` short-circuits cleanly.
    """
    facts = memory.get("facts") or []
    preferences = memory.get("preferences") or []
    if not facts and not preferences:
        return ""
    lines: list[str] = []
    if preferences:
        lines.append("## User preferences")
        for p in preferences:
            lines.append(f"- {p['text']}")
        lines.append("")
    if facts:
        lines.append("## Recent facts learned about the user")
        for f in facts:
            lines.append(f"- {f['text']}")
        lines.append("")
    return "\n".join(lines).rstrip()
