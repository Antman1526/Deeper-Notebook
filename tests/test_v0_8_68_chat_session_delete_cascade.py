"""v0.8.68 — ChatSession.delete sweeps refers_to edges (delete cascade).

Standalone session deletes previously left dangling session→notebook /
session→source graph edges; only a full notebook delete swept them.
"""

from __future__ import annotations

import asyncio

import pytest

from deeper_notebook.domain import notebook as nb


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture
def _capture(monkeypatch):
    queries: list[tuple[str, dict]] = []

    async def _fake_repo_query(query, vars=None):
        queries.append((query, vars or {}))
        return []

    async def _fake_super_delete(self):
        queries.append(("__row_delete__", {"id": self.id}))
        return True

    monkeypatch.setattr(nb, "repo_query", _fake_repo_query)
    monkeypatch.setattr(nb.ObjectModel, "delete", _fake_super_delete)
    return queries


def test_delete_sweeps_refers_to_then_row(_capture):
    session = nb.ChatSession(id="chat_session:abc", title="t")
    assert _run(session.delete()) is True

    sweep = [q for q, _ in _capture if "DELETE refers_to" in q]
    assert sweep, "refers_to sweep query must run"
    # Edge sweep happens BEFORE the row delete.
    sweep_idx = next(i for i, (q, _) in enumerate(_capture) if "DELETE refers_to" in q)
    row_idx = next(i for i, (q, _) in enumerate(_capture) if q == "__row_delete__")
    assert sweep_idx < row_idx


def test_delete_without_id_is_noop(_capture):
    session = nb.ChatSession(title="t")
    assert _run(session.delete()) is False
    assert _capture == []


def test_sweep_failure_does_not_block_row_delete(monkeypatch):
    calls: list[str] = []

    async def _boom(query, vars=None):
        raise RuntimeError("edge table unavailable")

    async def _fake_super_delete(self):
        calls.append("row_delete")
        return True

    monkeypatch.setattr(nb, "repo_query", _boom)
    monkeypatch.setattr(nb.ObjectModel, "delete", _fake_super_delete)

    session = nb.ChatSession(id="chat_session:abc", title="t")
    assert _run(session.delete()) is True
    assert calls == ["row_delete"]
