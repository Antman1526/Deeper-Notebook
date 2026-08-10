"""v0.7.166 — Backend regression for the `archived` WHERE-clause fix
plus AST-level pins for the frontend cache-invalidation additions.

Background:

(1) `GET /notebooks?archived=false` previously fetched ALL rows
    (with the per-row source_count + note_count subqueries) and
    filtered in Python (`api/routers/notebooks.py:64-65`). This
    test verifies the filter is now in the WHERE clause and that
    the `archived` parameter binds via `$archived` (not f-string
    interpolation).

(2) Five frontend mutation hooks (useCreateSource, useDeleteSource,
    useFileUpload, useAddSourcesToNotebook, useRemoveSourceFromNotebook,
    useCreateNote, useDeleteNote) now invalidate `QUERY_KEYS.notebooks`
    on success so the sidebar's source_count/note_count refreshes
    immediately. The previous behavior was: after every source/note
    mutation the sidebar counts stayed stale until the next
    window-focus refetch (`refetchOnWindowFocus: true` on the
    notebooks query). AST-level pin since the contract is structural.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


@pytest.fixture()
def client():
    from api.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# (1) archived filter moved into SurrealQL WHERE clause
# ---------------------------------------------------------------------------


def test_notebooks_archived_filter_uses_where_clause(client):
    """v0.7.166: hitting /api/notebooks?archived=false must result in a
    SurrealQL query that includes `WHERE archived = $archived` and a
    `$archived` parameter binding. Verifies the filter is server-side
    (saves the full table fetch + Python filter that used to run)."""
    captured: dict = {"query": None, "params": None}

    async def fake_repo_query(query, params=None):
        captured["query"] = query
        captured["params"] = params
        return []

    with patch(
        "api.routers.notebooks.repo_query", new=fake_repo_query
    ):
        r = client.get(
            "/api/notebooks?archived=false",
            headers={"x-skip-error-toast": "1"},
        )

    assert r.status_code == 200, r.text
    query = captured["query"] or ""
    assert "WHERE archived = $archived" in query, (
        f"v0.7.166 expects the archived filter in the WHERE clause. Got:\n{query}"
    )
    # Parameter binding must use $archived (not f-string interpolation).
    assert captured["params"] == {"archived": False}, (
        f"v0.7.166: archived must bind via $archived param, not f-string. "
        f"Got params: {captured['params']!r}"
    )


def test_notebooks_archived_filter_skipped_when_unset(client):
    """v0.7.166: when no `archived` param is passed, the WHERE clause
    must NOT be appended. Otherwise we'd accidentally restrict the
    default response to only archived=null rows."""
    captured: dict = {"query": None, "params": None}

    async def fake_repo_query(query, params=None):
        captured["query"] = query
        captured["params"] = params
        return []

    with patch(
        "api.routers.notebooks.repo_query", new=fake_repo_query
    ):
        r = client.get(
            "/api/notebooks",
            headers={"x-skip-error-toast": "1"},
        )

    assert r.status_code == 200
    query = captured["query"] or ""
    # No WHERE clause when archived param is omitted.
    assert "WHERE" not in query, (
        f"v0.7.166: unfiltered request should NOT inject WHERE. Got:\n{query}"
    )
    # And params should be None (no bindings needed).
    assert captured["params"] is None


def test_notebooks_archived_true_also_works(client):
    """Symmetric coverage: ?archived=true should bind True correctly."""
    captured: dict = {"params": None}

    async def fake_repo_query(query, params=None):
        captured["params"] = params
        return []

    with patch(
        "api.routers.notebooks.repo_query", new=fake_repo_query
    ):
        r = client.get(
            "/api/notebooks?archived=true",
            headers={"x-skip-error-toast": "1"},
        )

    assert r.status_code == 200
    assert captured["params"] == {"archived": True}


# ---------------------------------------------------------------------------
# (2) Frontend cache invalidation — AST-level pin
# ---------------------------------------------------------------------------


def test_use_sources_mutations_invalidate_notebooks_query():
    """v0.7.166: each source mutation hook must call
    `queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })`
    so the sidebar source_count refreshes immediately. A future
    refactor that drops this invalidation reintroduces the
    stale-sidebar UX bug."""
    src = _read_source("frontend/src/lib/hooks/use-sources.ts")

    # Count occurrences — must appear in onSuccess of each of these:
    # useCreateSource, useDeleteSource, useFileUpload,
    # useAddSourcesToNotebook, useRemoveSourceFromNotebook.
    invalidation = "queryKey: QUERY_KEYS.notebooks"
    count = src.count(invalidation)
    assert count >= 5, (
        f"v0.7.166 expects at least 5 invalidations of "
        f"QUERY_KEYS.notebooks (one per source mutation hook). Got {count}. "
        f"A future refactor that drops this leaves the sidebar's "
        f"source_count stale until the next window-focus refetch."
    )


def test_use_notes_mutations_invalidate_notebooks_query():
    """v0.7.166: useCreateNote + useDeleteNote must invalidate
    QUERY_KEYS.notebooks so note_count refreshes on the sidebar.
    """
    src = _read_source("frontend/src/lib/hooks/use-notes.ts")
    count = src.count("queryKey: QUERY_KEYS.notebooks")
    assert count >= 2, (
        f"v0.7.166 expects at least 2 invalidations of "
        f"QUERY_KEYS.notebooks (useCreateNote + useDeleteNote). Got {count}."
    )
