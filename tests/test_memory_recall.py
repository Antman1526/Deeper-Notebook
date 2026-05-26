"""v0.7.71 — pure-render unit tests for memory_recall.

The query path is exercised against the live SurrealDB in integration
tests; here we only verify the parts that are deterministic without
a DB: the SELECT-VALUE coercion helper and the prompt-block renderer.

v0.7.84 — extended with orchestrator tests (recall_memory mode
selection + fall-through). The orchestrator's behavior — which
sub-function it calls — is verified via monkeypatching, leaving the
underlying SurrealQL paths for integration tests.
"""
from __future__ import annotations

import pytest

from open_notebook.utils import memory_recall
from open_notebook.utils.memory_recall import (
    _coerce_text,
    render_memory_block,
)


def test_coerce_text_handles_string():
    assert _coerce_text("hello world") == "hello world"
    assert _coerce_text("  trim me  ") == "trim me"


def test_coerce_text_handles_none():
    assert _coerce_text(None) == ""


def test_coerce_text_handles_dict_with_text_field():
    """If SELECT VALUE flattening didn't happen and we got back a row dict,
    fall back to the `text` field rather than stringifying the dict."""
    assert _coerce_text({"text": "fact about user"}) == "fact about user"


def test_coerce_text_handles_dict_without_text_field():
    """An empty dict has no text field; should produce empty string, not 'None'."""
    assert _coerce_text({"text": None}) == ""
    assert _coerce_text({"id": "memory_fact:abc"}) == ""


def test_coerce_text_handles_other_types():
    """Numbers, lists — fall back to stringification."""
    assert _coerce_text(42) == "42"


def test_render_returns_empty_string_for_empty_memory():
    """Empty input → empty string so the Jinja `{% if memory_block %}`
    short-circuits and no section appears in the system prompt."""
    assert render_memory_block({"facts": [], "preferences": []}) == ""
    assert render_memory_block({}) == ""


def test_render_includes_only_preferences_when_only_preferences():
    out = render_memory_block({
        "facts": [],
        "preferences": [{"text": "prefers concise answers"}],
    })
    assert "## User preferences" in out
    assert "prefers concise answers" in out
    # No facts section when facts list is empty
    assert "## Recent facts" not in out


def test_render_includes_only_facts_when_only_facts():
    out = render_memory_block({
        "facts": [{"text": "uses TypeScript"}],
        "preferences": [],
    })
    assert "## Recent facts learned about the user" in out
    assert "uses TypeScript" in out
    # No preferences section
    assert "## User preferences" not in out


def test_render_includes_both_sections_when_both_present():
    out = render_memory_block({
        "facts": [
            {"text": "uses TypeScript"},
            {"text": "lives in Berlin"},
        ],
        "preferences": [
            {"text": "prefers concise answers"},
        ],
    })
    assert "## User preferences" in out
    assert "## Recent facts learned about the user" in out
    # Preferences come BEFORE facts (more authoritative)
    assert out.index("## User preferences") < out.index("## Recent facts")
    # All items appear
    assert "uses TypeScript" in out
    assert "lives in Berlin" in out
    assert "prefers concise answers" in out


def test_render_strips_trailing_whitespace():
    """Trailing newlines/whitespace don't leak into the prompt."""
    out = render_memory_block({
        "facts": [{"text": "fact"}],
        "preferences": [],
    })
    assert out == out.rstrip()


def test_render_handles_missing_keys_gracefully():
    """The recall dict shape should always have both keys, but be defensive."""
    assert render_memory_block({"facts": [{"text": "f"}]}) != ""
    assert render_memory_block({"preferences": [{"text": "p"}]}) != ""


@pytest.mark.parametrize("count", [1, 5, 15])
def test_render_produces_one_bullet_per_item(count: int):
    facts = [{"text": f"fact {i}"} for i in range(count)]
    out = render_memory_block({"facts": facts, "preferences": []})
    # Each fact becomes a bullet line `- fact i`
    assert out.count("\n- ") == count


# ---------------------------------------------------------------------------
# v0.7.84 — recall_memory orchestrator tests
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_recalls(monkeypatch):
    """Monkeypatch both recall paths to return marker dicts so we can
    observe which path the orchestrator picked."""
    recent_marker = {"facts": [{"text": "RECENT"}], "preferences": []}
    relevant_marker = {"facts": [{"text": "RELEVANT"}], "preferences": []}

    async def fake_recent():
        return recent_marker

    async def fake_relevant(query):
        return relevant_marker

    monkeypatch.setattr(memory_recall, "recall_recent_memory", fake_recent)
    monkeypatch.setattr(memory_recall, "recall_relevant_memory", fake_relevant)
    return recent_marker, relevant_marker


@pytest.fixture
def stub_count(monkeypatch):
    """Patch the row-counter so tests can control the auto-mode branch
    without touching SurrealDB."""
    state = {"count": 0}

    async def fake_count():
        return state["count"]

    monkeypatch.setattr(memory_recall, "_count_memory_rows", fake_count)
    return state


@pytest.mark.asyncio
async def test_orchestrator_empty_query_uses_recency(monkeypatch, stub_recalls):
    """Even in semantic / auto mode, an empty query has no embedding signal
    so we should fall through to recency rather than embedding the empty
    string (which would either fail or produce nonsense scores)."""
    monkeypatch.delenv("ONP_MEMORY_RECALL_MODE", raising=False)
    recent_marker, _ = stub_recalls
    result = await memory_recall.recall_memory(query="")
    assert result == recent_marker
    result = await memory_recall.recall_memory(query=None)
    assert result == recent_marker


@pytest.mark.asyncio
async def test_orchestrator_recent_mode_forces_recency(monkeypatch, stub_recalls):
    """`ONP_MEMORY_RECALL_MODE=recent` always returns recency, even with a
    query and a populated DB."""
    monkeypatch.setenv("ONP_MEMORY_RECALL_MODE", "recent")
    recent_marker, _ = stub_recalls
    result = await memory_recall.recall_memory(query="anything")
    assert result == recent_marker


@pytest.mark.asyncio
async def test_orchestrator_semantic_mode_forces_semantic(monkeypatch, stub_recalls):
    """`ONP_MEMORY_RECALL_MODE=semantic` always uses the semantic path."""
    monkeypatch.setenv("ONP_MEMORY_RECALL_MODE", "semantic")
    _, relevant_marker = stub_recalls
    result = await memory_recall.recall_memory(query="what do I prefer?")
    assert result == relevant_marker


@pytest.mark.asyncio
async def test_orchestrator_semantic_falls_back_to_recency(monkeypatch, stub_recalls):
    """If the semantic path returns empty (the documented signal for
    "embed failed / no matches"), the orchestrator falls back to
    recency rather than returning an empty memory block."""
    monkeypatch.setenv("ONP_MEMORY_RECALL_MODE", "semantic")
    recent_marker, _ = stub_recalls

    async def empty_relevant(query):
        return {}

    monkeypatch.setattr(memory_recall, "recall_relevant_memory", empty_relevant)
    result = await memory_recall.recall_memory(query="anything")
    assert result == recent_marker


@pytest.mark.asyncio
async def test_orchestrator_auto_picks_recency_below_threshold(
    monkeypatch, stub_recalls, stub_count
):
    """Below _SEMANTIC_THRESHOLD rows, auto mode uses recency — no embed
    round trip needed for small memory stores."""
    monkeypatch.delenv("ONP_MEMORY_RECALL_MODE", raising=False)
    recent_marker, _ = stub_recalls
    stub_count["count"] = memory_recall._SEMANTIC_THRESHOLD  # exactly at threshold
    result = await memory_recall.recall_memory(query="anything")
    assert result == recent_marker


@pytest.mark.asyncio
async def test_orchestrator_auto_picks_semantic_above_threshold(
    monkeypatch, stub_recalls, stub_count
):
    """Above _SEMANTIC_THRESHOLD rows, auto mode switches to semantic."""
    monkeypatch.delenv("ONP_MEMORY_RECALL_MODE", raising=False)
    _, relevant_marker = stub_recalls
    stub_count["count"] = memory_recall._SEMANTIC_THRESHOLD + 1
    result = await memory_recall.recall_memory(query="anything")
    assert result == relevant_marker


@pytest.mark.asyncio
async def test_orchestrator_unknown_mode_falls_through_to_auto(
    monkeypatch, stub_recalls, stub_count
):
    """An unrecognized env-var value should not crash — orchestrator
    drops to auto behavior (which then picks recency below threshold)."""
    monkeypatch.setenv("ONP_MEMORY_RECALL_MODE", "definitely-not-a-mode")
    recent_marker, _ = stub_recalls
    stub_count["count"] = 0
    result = await memory_recall.recall_memory(query="anything")
    assert result == recent_marker


# ============================================================================
# v0.7.113 — Embed timeout on the chat hot path
# ============================================================================


import asyncio as _asyncio_for_timeout_test


def test_recall_relevant_memory_falls_through_on_embed_timeout(
    monkeypatch,
):
    """v0.7.113 — recall_relevant_memory runs on every chat turn. If the
    embedding model is stuck (cold-start, OOM, misconfigured base_url),
    chat must NOT block waiting for it — recall_relevant_memory returns
    {} so the orchestrator falls through to recency recall (DB-only)."""
    monkeypatch.setenv("ONP_MEMORY_RECALL_EMBED_TIMEOUT_SEC", "0.1")

    class _HangingEmbedModel:
        async def aembed(self, texts):
            await _asyncio_for_timeout_test.sleep(5)
            return [[0.0] * 768]

    async def _get_emb():
        return _HangingEmbedModel()

    from open_notebook.ai import models as ai_models
    monkeypatch.setattr(
        ai_models.model_manager, "get_embedding_model", _get_emb,
    )

    from open_notebook.utils.memory_recall import recall_relevant_memory
    result = _asyncio_for_timeout_test.run(
        recall_relevant_memory("what is my favorite color")
    )
    # Empty dict signals "fall back to recency" to the caller
    assert result == {}


def test_recall_relevant_memory_completes_when_embed_returns_in_time(
    monkeypatch,
):
    """v0.7.113 — negative-space check: a fast embed call must NOT be
    spuriously timeout-killed."""
    monkeypatch.setenv("ONP_MEMORY_RECALL_EMBED_TIMEOUT_SEC", "5")

    class _FastEmbedModel:
        async def aembed(self, texts):
            return [[0.1] * 768]

    async def _get_emb():
        return _FastEmbedModel()

    async def _safe_select_empty(*args, **kwargs):
        # DB returns no facts/preferences — keeps the test focused on
        # the embed timeout path, not on SurrealQL semantics.
        return []

    from open_notebook.ai import models as ai_models
    monkeypatch.setattr(
        ai_models.model_manager, "get_embedding_model", _get_emb,
    )
    from open_notebook.utils import memory_recall
    monkeypatch.setattr(memory_recall, "_safe_select", _safe_select_empty)

    from open_notebook.utils.memory_recall import recall_relevant_memory
    result = _asyncio_for_timeout_test.run(
        recall_relevant_memory("what is my favorite color")
    )
    # NOT timeout-killed → returns the expected shape (empty facts +
    # preferences, since we stubbed the DB to return nothing).
    assert "facts" in result
    assert "preferences" in result


# ============================================================================
# v0.7.114 — _safe_select query timeout (hot path bound)
# ============================================================================


def test_safe_select_returns_empty_on_query_timeout(monkeypatch):
    """v0.7.114 — _safe_select runs on every chat turn (recall_recent
    fires two queries, recall_relevant fires two more). An overloaded
    connection pool must NOT stall chat; _safe_select returns [] on
    timeout so the caller treats it the same as a missing table."""
    monkeypatch.setenv("ONP_MEMORY_RECALL_QUERY_TIMEOUT_SEC", "0.1")

    async def _hanging_query(q, params):
        await _asyncio_for_timeout_test.sleep(5)
        return []

    from open_notebook.utils import memory_recall
    monkeypatch.setattr(memory_recall, "repo_query", _hanging_query)

    result = _asyncio_for_timeout_test.run(
        memory_recall._safe_select("SELECT 1", {})
    )
    assert result == []


def test_safe_select_returns_results_when_query_fast(monkeypatch):
    """v0.7.114 — negative-space check: a fast query is NOT
    spuriously timeout-killed."""
    monkeypatch.setenv("ONP_MEMORY_RECALL_QUERY_TIMEOUT_SEC", "5")

    async def _fast_query(q, params):
        return [{"text": "ok"}]

    from open_notebook.utils import memory_recall
    monkeypatch.setattr(memory_recall, "repo_query", _fast_query)

    result = _asyncio_for_timeout_test.run(
        memory_recall._safe_select("SELECT 1", {})
    )
    assert result == [{"text": "ok"}]


# ============================================================================
# v0.8.19 CRITICAL — recall_recent_memory SQL shape regression
# ============================================================================


def test_recall_recent_memory_uses_select_text_not_select_value(monkeypatch):
    """v0.8.19 CRITICAL — pre-fix the query was `SELECT VALUE text ...
    ORDER BY created_at DESC` which SurrealDB rejects with
    'Missing order idiom in statement selection' because VALUE
    requires the ORDER BY field to be in the projection.

    `_safe_select` swallowed the parse error at DEBUG level so
    memory recall silently returned empty every chat turn — users
    thought memory was working but no fact was ever recalled.

    This test pins the query shape against future regressions: any
    edit that brings back `SELECT VALUE ... ORDER BY <other_field>`
    fails immediately."""
    captured_queries: list[str] = []

    async def _capture(q, params):
        captured_queries.append(q)
        # Return realistic shape — SELECT text returns dicts, not strings
        return [{"text": "fake fact"}]

    from open_notebook.utils import memory_recall
    monkeypatch.setattr(memory_recall, "repo_query", _capture)

    result = _asyncio_for_timeout_test.run(
        memory_recall.recall_recent_memory()
    )

    # Two queries should have fired (facts + preferences)
    assert len(captured_queries) == 2
    for q in captured_queries:
        assert "SELECT text" in q, (
            f"v0.8.19: must use SELECT text (not SELECT VALUE text) "
            f"to keep SurrealDB happy on the ORDER BY created_at clause; "
            f"got query: {q!r}"
        )
        assert "VALUE" not in q, (
            f"v0.8.19: SELECT VALUE + ORDER BY <other_field> = SurrealDB "
            f"parse error. Got: {q!r}"
        )
        assert "ORDER BY created_at DESC" in q
        # v0.8.30 CRITICAL — v0.8.19's drop-VALUE was incomplete.
        # SurrealDB ALSO requires the ORDER BY field in the projection.
        # `SELECT text ... ORDER BY created_at DESC` STILL fails with
        # the same "Missing order idiom" parse error. The complete
        # fix adds `created_at` to the projection.
        assert "created_at" in q.split("FROM")[0], (
            f"v0.8.30: must SELECT created_at alongside text — "
            f"otherwise SurrealDB rejects ORDER BY created_at with "
            f"'Missing order idiom'. Got: {q!r}. v0.8.19 dropped VALUE "
            f"but missed this — memory recall has been silently empty "
            f"across v0.8.19 → v0.8.29 until v0.8.30 closed the loop."
        )

    # And the consumer must still extract the text correctly from
    # the dict shape (verifies _coerce_text on dicts works through
    # the pipeline, not just in isolation).
    assert result == {
        "facts": [{"text": "fake fact"}],
        "preferences": [{"text": "fake fact"}],
    }


def test_safe_select_logs_warning_on_schema_error(monkeypatch):
    """v0.8.19 — schema/parse errors must surface as WARNING. Pre-fix
    they were DEBUG, which masked the v0.8.19 bug for an entire
    release cycle. 'Table missing' (genuine fresh-install case) stays
    at DEBUG; SurrealDB parse errors get bumped to WARNING.

    Uses loguru's add()-sink-to-list pattern rather than pytest's
    caplog, because loguru writes directly to stderr and doesn't go
    through stdlib logging."""
    from loguru import logger

    captured: list[str] = []
    sink_id = logger.add(
        lambda msg: captured.append(msg.record["message"] + "|" + msg.record["level"].name),
        level="DEBUG",
    )
    try:
        async def _raise_schema_err(q, params):
            raise Exception(
                "'There was a problem with the database: Parse error: "
                "Missing order idiom `created_at` in statement selection'"
            )

        from open_notebook.utils import memory_recall
        monkeypatch.setattr(memory_recall, "repo_query", _raise_schema_err)

        result = _asyncio_for_timeout_test.run(
            memory_recall._safe_select("SELECT VALUE x FROM y ORDER BY z", {})
        )

        assert result == [], "still returns empty (non-fatal contract)"
        warning_msgs = [
            m for m in captured
            if "|WARNING" in m and "memory recall query failed" in m
        ]
        assert warning_msgs, (
            "v0.8.19: SurrealDB Parse errors must log at WARNING so they "
            "show up in launcher.log; pre-fix they were silently swallowed "
            "at DEBUG and the entire memory recall path was dead for "
            "multiple release cycles before anyone noticed. Captured: "
            f"{captured!r}"
        )
    finally:
        logger.remove(sink_id)


def test_safe_select_keeps_table_missing_at_debug(monkeypatch):
    """v0.8.19 — negative-space check for the previous test. 'Table
    missing' / 'unknown table' on a fresh install is genuinely the
    expected case (no chat turns yet, no memory_fact rows ever
    written), so it should stay at DEBUG to avoid log spam. Only
    actual SurrealDB syntax/parse errors get bumped to WARNING."""
    from loguru import logger

    captured: list[str] = []
    sink_id = logger.add(
        lambda msg: captured.append(msg.record["message"] + "|" + msg.record["level"].name),
        level="DEBUG",
    )
    try:
        async def _raise_table_missing(q, params):
            raise Exception("Table memory_fact does not exist")

        from open_notebook.utils import memory_recall
        monkeypatch.setattr(memory_recall, "repo_query", _raise_table_missing)

        result = _asyncio_for_timeout_test.run(
            memory_recall._safe_select("SELECT text FROM memory_fact", {})
        )

        assert result == []
        # Should be DEBUG (not WARNING) — fresh-install case
        warning_msgs = [m for m in captured if "|WARNING" in m]
        assert not warning_msgs, (
            f"v0.8.19: 'table missing' must stay at DEBUG to avoid log "
            f"spam on fresh installs (only parse errors get WARNING). "
            f"Got warnings: {warning_msgs!r}"
        )
    finally:
        logger.remove(sink_id)
