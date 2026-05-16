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

We deliberately do NOT do vector-similarity search here even though
the rows carry embeddings. Reasons:
  1. The chat-graph node is hot path; we want the read to be a
     single SurrealQL round-trip with no model-side embedding pass.
  2. A typical single-user deploy has tens, not thousands, of
     facts — dumping the 20 most recent gives the LLM "what I've
     learned about you lately" without needing semantic relevance.
  3. The mem0 retriever HTTP service that DOES do similarity search
     isn't always reachable from the API (it's a sibling process in
     the desktop launcher) and we don't want to make chat depend
     on it.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from open_notebook.database.repository import repo_query

# Total cap across BOTH facts and preferences so the injected block
# stays predictable. Each row is typically 30-200 chars, so 20 rows
# is ~2-4k chars in the worst case — comfortable inside the chat-graph
# 12k-char history budget.
_MAX_FACTS = 15
_MAX_PREFERENCES = 10


async def recall_recent_memory() -> dict[str, list[dict[str, Any]]]:
    """Return recent fact + preference rows for prompt injection.

    Shape:
        {"facts": [{"text": "...", "scope": "user"}, ...],
         "preferences": [...]}

    Returns empty lists on any failure (table missing, DB blip,
    upstream non-desktop build). The caller treats empty == "no
    memory section in the prompt".
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


def _coerce_text(value: Any) -> str:
    """SurrealDB `SELECT VALUE` returns scalars but the wrapper may
    occasionally hand us a dict with a single field. Normalize."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        # Defensive: if the SELECT VALUE flattening didn't happen for
        # some reason, recover the text field.
        return str(value.get("text", "")).strip()
    return str(value).strip()


async def _safe_select(query: str, vars: dict) -> list[Any]:
    """Run a SurrealQL query and never raise. Memory tables may not
    exist on a fresh DB (no chat turns yet, or upstream build with the
    memory feature disabled) — empty list is the right answer."""
    try:
        result = await repo_query(query, vars)
        if isinstance(result, list):
            return result
        return []
    except Exception as exc:
        # debug — every chat turn would log otherwise; the empty path
        # is the expected case on fresh installs.
        logger.debug("memory recall query failed (returning empty): %s", exc)
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
