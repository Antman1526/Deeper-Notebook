"""v0.7.159 — Pagination on ObjectModel.get_all().

Previously `GET /notes` (no notebook filter) called `Note.get_all()`
which ran `SELECT * FROM note ORDER BY updated DESC` with NO limit.
A heavy user with thousands of notes hit by an API explorer call or
a stale React Query cache returned multi-MB JSON and burned a request
slot for seconds.

This module exercises the new `limit` / `offset` keyword args on
`ObjectModel.get_all` against a mocked `repo_query` so we can assert
the rendered SurrealQL without a live SurrealDB. All four behaviors
are guarded:

  1. No args → query unchanged (backward compatibility)
  2. `limit` only → appends `LIMIT <n>`
  3. `limit + offset` → appends both clauses in `LIMIT … START …` order
  4. Invalid input → `InvalidInputError`, no query issued
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from deeper_notebook.domain.notebook import Note
from deeper_notebook.exceptions import InvalidInputError


def _make_row(suffix: str = "1") -> dict:
    return {
        "id": f"note:{suffix}",
        "title": f"note-{suffix}",
        "content": "x",
        "note_type": "human",
        "created": "2026-05-21T00:00:00Z",
        "updated": "2026-05-21T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_get_all_without_pagination_is_unbounded():
    """v0.7.159 — back-compat. Callers that don't ask for limit/offset
    still get the full table. This preserves all pre-v0.7.159 behavior."""
    rows = [_make_row(str(i)) for i in range(3)]
    captured: dict = {}

    async def fake_repo_query(q, params=None):
        captured["q"] = q
        return rows

    with patch("deeper_notebook.domain.base.repo_query", new=fake_repo_query):
        result = await Note.get_all()

    assert len(result) == 3
    # Query has NO LIMIT clause.
    assert "LIMIT" not in captured["q"]
    assert "START" not in captured["q"]


@pytest.mark.asyncio
async def test_get_all_with_limit_only_appends_limit_clause():
    """v0.7.159 — `limit=200` appends `LIMIT 200`."""
    captured: dict = {}

    async def fake_repo_query(q, params=None):
        captured["q"] = q
        return []

    with patch("deeper_notebook.domain.base.repo_query", new=fake_repo_query):
        await Note.get_all(limit=200)

    assert "LIMIT 200" in captured["q"]
    assert "START" not in captured["q"]


@pytest.mark.asyncio
async def test_get_all_with_limit_and_offset_appends_both_clauses():
    """v0.7.159 — both clauses in SurrealQL `LIMIT n START m` order."""
    captured: dict = {}

    async def fake_repo_query(q, params=None):
        captured["q"] = q
        return []

    with patch("deeper_notebook.domain.base.repo_query", new=fake_repo_query):
        await Note.get_all(order_by="updated desc", limit=50, offset=100)

    q = captured["q"]
    assert "ORDER BY updated desc" in q
    # LIMIT comes before START — SurrealQL requires this order.
    assert q.index("LIMIT") < q.index("START"), (
        f"LIMIT must come before START in SurrealQL, got: {q!r}"
    )
    assert "LIMIT 50" in q
    assert "START 100" in q


@pytest.mark.asyncio
async def test_get_all_rejects_negative_limit():
    """v0.7.159 — defensive input validation. SurrealQL doesn't sanitize
    integer literals from string interpolation, so we belt-and-suspender
    the limit/offset values before they reach the query."""
    with pytest.raises(InvalidInputError):
        await Note.get_all(limit=-5)


@pytest.mark.asyncio
async def test_get_all_rejects_non_int_offset():
    """v0.7.159 — same defensive check on offset."""
    with pytest.raises(InvalidInputError):
        await Note.get_all(limit=10, offset="42")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_all_rejects_zero_limit():
    """v0.7.159 — `limit=0` is a foot-gun (returns 0 rows silently);
    require a positive int to surface the caller's intent."""
    with pytest.raises(InvalidInputError):
        await Note.get_all(limit=0)
