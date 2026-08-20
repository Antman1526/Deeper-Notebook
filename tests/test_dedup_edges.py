"""v0.7.85 — tests for the legacy-edge deduplicator.

The real query path runs against SurrealDB. Here we only verify the
orchestration logic — which deletes fire, in what order, which rows
survive — via monkeypatching `repo_query`. The deterministic
canonical-edge selection (lexicographically-smallest stringified id)
is the most important contract to lock down: it ensures that a
partial run can be safely retried on the next startup without losing
different edges than the first pass would have.
"""

from __future__ import annotations

import pytest

from deeper_notebook.database import dedup_edges


@pytest.fixture
def fake_repo(monkeypatch):
    """Mock repo_query with a scripted set of responses.

    Setup pattern:
        fake_repo.responses["reference_select"] = [
            {"in": "src:a", "out": "nb:x", "ids": ["reference:1", "reference:2", "reference:3"]},
        ]
        fake_repo.deletes = []  # captures DELETE $edge_id calls

    Each call inspects the query text to route to the right scripted
    response. DELETE calls are captured for assertion rather than
    actually executed.
    """
    state: dict = {
        "select_responses": {"reference": [], "artifact": []},
        "deletes": [],
        "select_fails": set(),  # tables to fail SELECT for
        "delete_fail_ids": set(),  # specific ids to fail DELETE for
    }

    async def fake_repo_query(query: str, vars: dict | None = None):
        q = query.strip()
        # Route by query shape.
        if q.startswith("SELECT in, out, array::group"):
            # The dedup SELECT for one table. Determine which by
            # `FROM {table}` substring.
            for table in dedup_edges._EDGE_TABLES:
                if f"FROM {table}" in q:
                    if table in state["select_fails"]:
                        raise RuntimeError(f"simulated SELECT failure on {table}")
                    return state["select_responses"][table]
            raise AssertionError(f"unexpected SELECT routing for {q!r}")
        if q.startswith("DELETE $edge_id"):
            assert vars is not None and "edge_id" in vars
            edge_id = vars["edge_id"]
            if edge_id in state["delete_fail_ids"]:
                raise RuntimeError(f"simulated DELETE failure for {edge_id}")
            state["deletes"].append(edge_id)
            return None
        raise AssertionError(f"unexpected query: {q!r}")

    monkeypatch.setattr(dedup_edges, "repo_query", fake_repo_query)
    return state


@pytest.mark.asyncio
async def test_clean_database_is_a_no_op(fake_repo):
    """A database with no duplicate edges runs zero DELETEs and reports
    zero deletions across every table."""
    fake_repo["select_responses"]["reference"] = []
    fake_repo["select_responses"]["artifact"] = []
    result = await dedup_edges.dedupe_legacy_edges()
    assert result == {"reference": 0, "artifact": 0}
    assert fake_repo["deletes"] == []


@pytest.mark.asyncio
async def test_single_duplicate_group_deletes_extras(fake_repo):
    """Three edges on the same (in, out) → keep one, delete two.
    Survivor is the lexicographically-smallest id for determinism."""
    fake_repo["select_responses"]["reference"] = [
        {
            "in": "source:abc",
            "out": "notebook:xyz",
            # Intentionally out of order — survivor should be 'reference:1'
            "ids": ["reference:3", "reference:1", "reference:2"],
        }
    ]
    result = await dedup_edges.dedupe_legacy_edges()
    assert result["reference"] == 2
    # Survivor (smallest) is NOT in the delete list.
    assert "reference:1" not in fake_repo["deletes"]
    # Extras ARE deleted, both of them.
    assert sorted(fake_repo["deletes"]) == ["reference:2", "reference:3"]


@pytest.mark.asyncio
async def test_already_deduped_group_is_skipped(fake_repo):
    """A group with exactly one id is the post-dedup state — should be
    treated as a no-op even though it was returned by the SELECT.

    (Whether SurrealDB filters by `HAVING count() > 1` upstream is
    version-dependent, so we defensively re-filter in Python.)"""
    fake_repo["select_responses"]["reference"] = [
        {"in": "source:abc", "out": "notebook:xyz", "ids": ["reference:1"]}
    ]
    result = await dedup_edges.dedupe_legacy_edges()
    assert result["reference"] == 0
    assert fake_repo["deletes"] == []


@pytest.mark.asyncio
async def test_partial_delete_failure_does_not_abort_remaining_extras(fake_repo):
    """Per-edge DELETE errors are best-effort: a single failure must
    not block the cleanup of OTHER duplicates in the same group or
    other groups."""
    fake_repo["select_responses"]["reference"] = [
        {
            "in": "source:abc",
            "out": "notebook:xyz",
            "ids": ["reference:1", "reference:2", "reference:3"],
        }
    ]
    fake_repo["delete_fail_ids"] = {"reference:2"}
    result = await dedup_edges.dedupe_legacy_edges()
    # 1 succeeded (reference:3), 1 failed silently (reference:2).
    assert result["reference"] == 1
    assert "reference:3" in fake_repo["deletes"]
    assert "reference:2" not in fake_repo["deletes"]


@pytest.mark.asyncio
async def test_per_table_select_failure_does_not_block_other_tables(fake_repo):
    """If the reference-table SELECT fails entirely, the artifact-table
    sweep should still run — they're independent."""
    fake_repo["select_fails"] = {"reference"}
    fake_repo["select_responses"]["artifact"] = [
        {
            "in": "note:n1",
            "out": "notebook:nb",
            "ids": ["artifact:a", "artifact:b"],
        }
    ]
    result = await dedup_edges.dedupe_legacy_edges()
    # reference table failed → 0
    assert result["reference"] == 0
    # artifact table still ran → 1 deletion
    assert result["artifact"] == 1
    assert fake_repo["deletes"] == ["artifact:b"]


@pytest.mark.asyncio
async def test_multiple_groups_processed_independently(fake_repo):
    """Two separate (in, out) groups in the same table — each gets
    deduped to one survivor."""
    fake_repo["select_responses"]["reference"] = [
        {
            "in": "source:a",
            "out": "notebook:1",
            "ids": ["reference:01", "reference:02"],
        },
        {
            "in": "source:b",
            "out": "notebook:1",
            "ids": ["reference:10", "reference:11", "reference:12"],
        },
    ]
    result = await dedup_edges.dedupe_legacy_edges()
    assert result["reference"] == 3  # 1 + 2 extras deleted
    # Survivors retained: reference:01 (group 1) and reference:10 (group 2).
    assert sorted(fake_repo["deletes"]) == [
        "reference:02",
        "reference:11",
        "reference:12",
    ]


@pytest.mark.asyncio
async def test_idempotent_on_re_run(fake_repo):
    """After the first sweep, the second sweep sees no duplicates and
    runs zero DELETEs. Simulated by setting the SELECT response to
    empty on the second call.

    This is the contract that makes the per-startup invocation safe:
    every restart re-runs the sweep, but only the first one on each
    database state actually deletes anything."""
    fake_repo["select_responses"]["reference"] = [
        {"in": "src:a", "out": "nb:1", "ids": ["reference:1", "reference:2"]}
    ]
    first = await dedup_edges.dedupe_legacy_edges()
    assert first["reference"] == 1
    # Simulate post-dedup state: SELECT now returns no duplicates.
    fake_repo["select_responses"]["reference"] = []
    fake_repo["deletes"].clear()
    second = await dedup_edges.dedupe_legacy_edges()
    assert second == {"reference": 0, "artifact": 0}
    assert fake_repo["deletes"] == []
