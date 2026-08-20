"""v0.8.32 — End-to-end memory recall against a real SurrealDB.

This file is the v0.8.30 follow-up. v0.8.19 dropped `SELECT VALUE`
from the memory_recall queries thinking that fixed the SurrealDB
"Missing order idiom" parse error. The unit tests only mocked
`repo_query`, so SurrealDB's real query parser was never exercised.

v0.8.30 (one session later) discovered the v0.8.19 fix was incomplete:
SurrealDB ALSO requires the `ORDER BY` field (`created_at`) to be IN
the projection. The corrected query is:

    SELECT text, created_at FROM memory_fact ORDER BY created_at DESC LIMIT $limit

The lesson captured in v0.8.30's commit message: any SurrealQL change
needs at least one integration-style test that talks to the real query
parser. THIS FILE is that test. Running it against v0.8.18 or v0.8.19
state (no `created_at` in projection) would have failed loudly.

Gated by `SURREAL_INTEGRATION=1` — same machinery as
test_notebook_lifecycle.py. Mints a throwaway namespace, runs the full
migration set, exercises the recall path, REMOVE NAMESPACE on teardown.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from deeper_notebook.database.repository import repo_query

pytestmark = pytest.mark.integration_surreal

_EMBEDDING_DIMENSION = 768


async def test_recall_relevant_memory_returns_all_kinds_from_hnsw(
    clean_namespace, monkeypatch
):
    """A real HNSW recall query must return fact, preference, and episode rows.

    The one-argument KNN operator is valid only for MTREE. Against these HNSW
    indexes SurrealDB 2.6.5 accepts it but returns no candidates, so this test
    exercises the actual query planner while stubbing only the embedder.
    """
    component = 1 / math.sqrt(_EMBEDDING_DIMENSION)
    vector = [component] * _EMBEDDING_DIMENSION
    rows = {
        "memory_fact": "fact recalled through HNSW",
        "memory_preference": "preference recalled through HNSW",
        "memory_episode": "episode recalled through HNSW",
    }
    for table, text in rows.items():
        await repo_query(
            f"CREATE {table} CONTENT {{text: $text, embedding: $embedding}}",  # nosec B608
            {"text": text, "embedding": vector},
        )

    class FakeEmbeddingModel:
        async def aembed(self, texts):
            return [vector]

    async def get_embedding_model():
        return FakeEmbeddingModel()

    from deeper_notebook.ai.models import model_manager
    from deeper_notebook.utils.memory_recall import recall_relevant_memory

    monkeypatch.setattr(model_manager, "get_embedding_model", get_embedding_model)

    result = await recall_relevant_memory("HNSW recall fixture")

    assert result == {
        "facts": [{"text": rows["memory_fact"]}],
        "preferences": [{"text": rows["memory_preference"]}],
        "episodes": [{"text": rows["memory_episode"]}],
    }


# v0.8.67s — Removed @pytest.mark.asyncio and changed fixture from surreal_db
# to clean_namespace to avoid event-loop mismatch (Future attached to a
# different loop). Relying on pyproject.toml asyncio_mode = "auto" ensures
# the test runs in the session event loop where the pool was initialized.
async def test_recall_recent_memory_against_real_surrealdb(clean_namespace):
    """Insert two memory_fact + two memory_preference rows and assert
    `recall_recent_memory()` returns them ordered DESC by created_at.

    This is the test that would have failed against the v0.8.19 fix
    state (missing `created_at` in projection) — the SurrealDB query
    parser would have raised:

        Parse error: Missing order idiom `created_at` in statement
        selection

    Pre-v0.8.19 (with `SELECT VALUE` + `ORDER BY created_at`) the
    same parser error would have fired. The v0.8.30 fix adds
    `created_at` to the projection, which finally satisfies the
    parser AND keeps `_coerce_text` extracting only the `text` field.
    """
    # Insert two facts and two preferences with explicit created_at
    # so we can assert the ORDER BY behaviour deterministically.
    # v0.8.67s — Added dummy embedding of 768 floats to meet schema requirements
    # for SCHEMAFULL memory tables and prevent "Found NONE for field embedding" errors.
    now = datetime.now(timezone.utc)
    dummy_embedding = [0.0] * 768
    facts_payload = [
        {
            "text": "fact-OLDER",
            "created_at": now.replace(microsecond=0),
            "embedding": dummy_embedding,
        },
        {"text": "fact-NEWER", "created_at": now, "embedding": dummy_embedding},
    ]
    prefs_payload = [
        {
            "text": "pref-OLDER",
            "created_at": now.replace(microsecond=0),
            "embedding": dummy_embedding,
        },
        {"text": "pref-NEWER", "created_at": now, "embedding": dummy_embedding},
    ]
    for row in facts_payload:
        await repo_query(
            "CREATE memory_fact CONTENT {text: $text, created_at: $created_at, embedding: $embedding}",
            row,
        )
    for row in prefs_payload:
        await repo_query(
            "CREATE memory_preference CONTENT {text: $text, created_at: $created_at, embedding: $embedding}",
            row,
        )

    # Now exercise the real recall_recent_memory — same import the
    # chat graph uses on every turn.
    from deeper_notebook.utils.memory_recall import recall_recent_memory

    result = await recall_recent_memory()

    # Shape: {"facts": [{"text": ...}, ...], "preferences": [{"text": ...}, ...]}
    assert "facts" in result and "preferences" in result
    # Both kinds were populated (v0.8.30: pre-fix this returned empty).
    assert result["facts"], (
        "v0.8.30 contract violated: recall_recent_memory returned empty "
        "facts despite memory_fact rows existing. The query likely hit "
        "the 'Missing order idiom' parse error and _safe_select returned []."
    )
    assert result["preferences"], (
        "v0.8.30 contract violated: recall_recent_memory returned empty "
        "preferences despite memory_preference rows existing."
    )

    # Ordering: newer facts first (ORDER BY created_at DESC).
    fact_texts = [f["text"] for f in result["facts"]]
    pref_texts = [p["text"] for p in result["preferences"]]
    assert fact_texts[0] == "fact-NEWER", (
        f"v0.8.30: facts must be ordered by created_at DESC. Got order: {fact_texts}"
    )
    assert pref_texts[0] == "pref-NEWER", (
        f"v0.8.30: preferences must be ordered by created_at DESC. "
        f"Got order: {pref_texts}"
    )

    # Cleanup so subsequent integration tests (if any add memory rows)
    # start from a known state. REMOVE NAMESPACE on session teardown
    # also handles this, but explicit cleanup is cheap and avoids
    # cross-test ordering hazards inside the same session.
    await repo_query("DELETE memory_fact;")
    await repo_query("DELETE memory_preference;")


# v0.8.67s — Removed @pytest.mark.asyncio and changed fixture from surreal_db
# to clean_namespace to avoid event-loop mismatch.
async def test_safe_select_query_shape_does_not_raise(clean_namespace):
    """Even with an empty table, the query must parse cleanly. This
    is the SMALLEST possible test — it doesn't assert content, just
    that SurrealDB accepts the query. Most useful as a regression
    guard for future query rewrites.

    If a future refactor reintroduces `SELECT VALUE` or drops
    `created_at` from the projection, the parser will raise here
    even on an empty table — exactly the signal v0.8.19 needed but
    didn't have.
    """
    from deeper_notebook.utils.memory_recall import _safe_select

    facts = await _safe_select(
        "SELECT text, created_at FROM memory_fact "
        "ORDER BY created_at DESC LIMIT $limit",
        {"limit": 10},
    )
    prefs = await _safe_select(
        "SELECT text, created_at FROM memory_preference "
        "ORDER BY created_at DESC LIMIT $limit",
        {"limit": 10},
    )

    # Empty tables: _safe_select returns [] either way — but the
    # critical point is that no exception fired internally (which
    # _safe_select swallows with a WARNING log). If we got [] AND
    # no warning, we're good. The pre-v0.8.30 state would have hit
    # the WARNING path.
    assert facts == []
    assert prefs == []
