"""v0.8.99 — SurrealQL identifier interpolation is validated by construction.

An AST sweep for f-string queries interpolating a *function parameter* (rather
than a module constant or literal) found four sites across the repository:

  * `evaluation/repository.latest_run`      — already guarded by an explicit
    `{"artifact_id", "message_id"}` whitelist. This is the house pattern.
  * `desktop/memory/surreal_store.count`    — guarded in v0.8.98.
  * `database/dedup_edges`                  — unguarded (this suite).
  * `knowledge_engine/navigation_repository._random_where` — unguarded (this suite).

All four were safe in practice: every caller passes a module constant. But the
`# nosec B608` on each line asserts "constants/whitelisted identifiers", and an
assertion that depends on caller discipline is a comment, not a control. These
tests make the last two true by construction, matching `latest_run`.
"""

from __future__ import annotations

import pytest

from deeper_notebook.database import dedup_edges
from deeper_notebook.knowledge_engine.navigation_repository import (
    KnowledgeNavigationRepository,
)

HOSTILE = [
    "reference; REMOVE TABLE reference",
    "reference WHERE 1=1",
    "not_a_table",
    "",
    "reference\nDELETE artifact",
    "*",
]


# --- dedup_edges --------------------------------------------------------------


@pytest.mark.parametrize("table", dedup_edges._EDGE_TABLES)
@pytest.mark.asyncio
async def test_dedupe_table_accepts_every_known_edge_table(table, monkeypatch):
    seen: list[str] = []

    async def fake_query(query, *args, **kwargs):
        seen.append(query)
        return []

    monkeypatch.setattr(dedup_edges, "repo_query", fake_query)
    assert await dedup_edges._dedupe_table(table) == 0
    assert seen and table in seen[0]


@pytest.mark.parametrize("hostile", HOSTILE)
@pytest.mark.asyncio
async def test_dedupe_table_refuses_unknown_edge_tables(hostile, monkeypatch):
    executed: list[str] = []

    async def fake_query(query, *args, **kwargs):
        executed.append(query)
        return []

    monkeypatch.setattr(dedup_edges, "repo_query", fake_query)
    with pytest.raises(ValueError):
        await dedup_edges._dedupe_table(hostile)
    assert executed == [], "a refused table must not reach a query"


# --- navigation repository ----------------------------------------------------


def test_random_where_accepts_the_two_known_projections():
    from deeper_notebook.knowledge_engine.navigation_repository import (
        _OPEN_DESCRIPTOR_FIELDS,
    )

    for fields in ("count() AS count", _OPEN_DESCRIPTOR_FIELDS):
        query = KnowledgeNavigationRepository._random_where(fields)
        assert "knowledge_engine_document" in query


@pytest.mark.parametrize(
    "hostile",
    [
        "* FROM knowledge_engine_document; REMOVE TABLE knowledge_engine_document --",
        "id, (SELECT * FROM credential) AS leaked",
        "",
        "*",
    ],
)
def test_random_where_refuses_arbitrary_projections(hostile):
    with pytest.raises(ValueError):
        KnowledgeNavigationRepository._random_where(hostile)
