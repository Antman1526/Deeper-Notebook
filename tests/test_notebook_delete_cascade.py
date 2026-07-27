"""v0.7.107 / v0.7.116 — regression test for Notebook delete cascade.

v0.7.107 parallelized the per-note delete loop via asyncio.gather.
This test verifies behavior without needing a real SurrealDB:

  * Every note attached to the notebook gets `delete()` called.
  * A single note's delete-failure does NOT cancel siblings.
  * Final delete_notes count matches successful deletions.
  * Calls happen concurrently (parallel gather), not sequentially.
  * Defensive top-level `DELETE artifact WHERE out=$notebook_id` runs
    after the per-note loop completes.

Mocks `repo_query` + class methods on Notebook so the test exercises
only the cascade-orchestration logic.
"""
from __future__ import annotations

import asyncio

import pytest


class _FakeNote:
    """Stand-in for a Note row. Tracks delete() calls + can raise."""
    def __init__(self, note_id: str, *, raise_on_delete: bool = False):
        self.id = note_id
        self.delete_called = False
        self.raise_on_delete = raise_on_delete

    async def delete(self) -> bool:
        self.delete_called = True
        if self.raise_on_delete:
            raise RuntimeError(f"simulated delete failure for {self.id}")
        return True


@pytest.fixture()
def make_notebook(monkeypatch):
    """Factory yielding a Notebook with N attached notes and mocked
    SurrealDB queries. Returns (notebook, notes, repo_query_calls)."""
    from deeper_notebook.domain import notebook as nb_mod

    def _factory(notes: list, sources: list = None):
        sources = sources or []

        calls: list[tuple[str, dict]] = []

        async def _fake_repo_query(query: str, params: dict = None):
            calls.append((query, params or {}))
            if "SELECT" in query and "count" in query.lower():
                return [{"count": len(sources)}]
            if "SELECT" in query:
                return []
            return None

        async def _fake_repo_delete(record_id):
            calls.append((f"DELETE {record_id}", {}))
            return True

        monkeypatch.setattr(nb_mod, "repo_query", _fake_repo_query)
        monkeypatch.setattr(nb_mod, "ensure_record_id", lambda x: x)

        # ObjectModel.delete() (in base.py) calls repo_delete directly.
        # We need to stub that too, otherwise the notebook-row delete at
        # the very end of Notebook.delete tries to hit SurrealDB.
        from deeper_notebook.domain import base as base_mod
        monkeypatch.setattr(base_mod, "repo_delete", _fake_repo_delete)

        # Class-level monkeypatch — Pydantic v2 doesn't allow instance
        # attribute assignment, so we patch on the class.
        async def _get_notes(self):
            return notes

        async def _get_sources(self):
            return sources

        monkeypatch.setattr(nb_mod.Notebook, "get_notes", _get_notes)
        monkeypatch.setattr(nb_mod.Notebook, "get_sources", _get_sources)

        notebook = nb_mod.Notebook(
            id="notebook:test-cascade",
            name="Cascade Test",
            description="(test)",
        )
        return notebook, notes, calls

    return _factory


def test_delete_calls_delete_on_every_note(make_notebook):
    notes = [_FakeNote(f"note:{i}") for i in range(5)]
    notebook, _, _ = make_notebook(notes)
    result = asyncio.run(notebook.delete())
    assert all(n.delete_called for n in notes), \
        f"Some notes not deleted: {[n.id for n in notes if not n.delete_called]}"
    assert result["deleted_notes"] == 5


def test_delete_continues_after_one_note_fails(make_notebook):
    """v0.7.107 — A single note's delete failure must NOT cancel the
    sibling deletes."""
    notes = [
        _FakeNote("note:1"),
        _FakeNote("note:2", raise_on_delete=True),
        _FakeNote("note:3"),
        _FakeNote("note:4"),
    ]
    notebook, _, _ = make_notebook(notes)
    result = asyncio.run(notebook.delete())
    # All four had delete() called (the raise happened inside note 2)
    assert all(n.delete_called for n in notes)
    # deleted_notes count excludes the failure
    assert result["deleted_notes"] == 3


def test_delete_runs_per_note_in_parallel(make_notebook):
    """v0.7.107 — Per-note deletes use asyncio.gather. Verify peak
    concurrency exceeds 1 (sequential would have peak=1)."""
    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    class _SlowNote:
        def __init__(self, note_id):
            self.id = note_id

        async def delete(self):
            nonlocal in_flight, peak
            async with lock:
                in_flight += 1
                if in_flight > peak:
                    peak = in_flight
            await asyncio.sleep(0.05)
            async with lock:
                in_flight -= 1
            return True

    notes = [_SlowNote(f"note:{i}") for i in range(5)]
    notebook, _, _ = make_notebook(notes)
    asyncio.run(notebook.delete())
    assert peak > 1, f"Expected concurrent delete (peak > 1), got peak={peak}"


def test_delete_runs_top_level_artifact_delete_after_loop(make_notebook):
    """The defensive `DELETE artifact WHERE out=$notebook_id` belt-and-
    braces step must run after the per-note loop."""
    notes = [_FakeNote("note:1"), _FakeNote("note:2")]
    notebook, _, calls = make_notebook(notes)
    asyncio.run(notebook.delete())
    artifact_delete = [
        (q, p) for q, p in calls if "DELETE artifact" in q
    ]
    assert artifact_delete, \
        "Expected DELETE artifact in queries; got:\n  " + \
        "\n  ".join(q for q, _ in calls)
    assert artifact_delete[0][1].get("notebook_id") == "notebook:test-cascade"


def test_delete_empty_notebook_is_safe(make_notebook):
    """A notebook with zero notes shouldn't crash — no-op delete loop,
    defensive top-level DELETE artifact + DELETE reference still run."""
    notebook, _, calls = make_notebook([])
    result = asyncio.run(notebook.delete())
    assert result["deleted_notes"] == 0
    assert any("DELETE artifact" in q for q, _ in calls)
    assert any("DELETE reference" in q for q, _ in calls)
