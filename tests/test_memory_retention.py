"""v0.8.50 — Phase 5.1a: memory retention ceiling (closes Finding #3).

The memory tables (memory_fact / memory_preference / memory_episode) grew
without bound — recall caps RESULTS, never ROWS. v0.8.50 adds a per-table
recency ceiling:
  * SurrealMemoryStore.prune(keep) / .count(table)
  * desktop/memory/writer.py:prune_memories() best-effort wrapper, invoked
    at session end (always) and per-turn (behind a high-water gate).

These tests mock the SurrealDB client (SurrealMemoryStore.from_test_client)
and the mem0 client — no live DB / mem0 / model needed.
"""
from __future__ import annotations

import pytest

from desktop.memory import writer as writer_mod
from desktop.memory.constants import ALL_MEMORY_TABLES
from desktop.memory.surreal_store import SurrealMemoryStore

# ---------------------------------------------------------------------------
# Fake SurrealDB client for the store
# ---------------------------------------------------------------------------


class _FakeClient:
    """Records queries; serves canned rows per table. Rows are returned in
    the order given (the REAL DB sorts via ORDER BY created_at DESC, so tests
    supply rows already newest-first)."""

    def __init__(self, table_rows: dict[str, list[dict]]):
        self.table_rows = table_rows
        self.queries: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, list]] = []

    def query(self, sql, vars=None):
        self.queries.append((sql, vars))
        s = sql.strip()
        # v0.8.66 (audit MEM-2) — the prune SELECT now also projects
        # `confidence` (ORDER BY created_at DESC, confidence DESC), so match the
        # `SELECT id, created_at...` prefix loosely rather than the exact old form.
        if s.startswith("SELECT id, created_at"):
            table = s.split("FROM")[1].split()[0]
            return list(self.table_rows.get(table, []))
        if s.startswith("DELETE"):
            table = s.split()[1]
            ids = (vars or {}).get("ids") or []
            self.deletes.append((table, list(ids)))
            return []
        if "count()" in s:
            table = s.split("FROM")[1].split()[0]
            return [{"n": len(self.table_rows.get(table, []))}]
        return []


def _rows(table: str, n: int) -> list[dict]:
    # Newest-first (as ORDER BY created_at DESC would return).
    return [{"id": f"{table}:r{i}", "created_at": f"t{n - i}"} for i in range(n)]


# ---------------------------------------------------------------------------
# SurrealMemoryStore.prune
# ---------------------------------------------------------------------------


def test_prune_keeps_newest_and_deletes_rest():
    rows = {"memory_fact": _rows("memory_fact", 5),
            "memory_preference": [], "memory_episode": []}
    client = _FakeClient(rows)
    store = SurrealMemoryStore.from_test_client(client)

    deleted = store.prune(keep_per_table=2)

    # 5 facts, keep 2 → delete the 3 oldest (rows[2:]).
    assert deleted["memory_fact"] == 3
    assert deleted["memory_preference"] == 0
    assert deleted["memory_episode"] == 0
    # The deleted ids are exactly the 3 oldest (r2, r3, r4).
    fact_deletes = [d for d in client.deletes if d[0] == "memory_fact"]
    assert fact_deletes == [("memory_fact",
                             ["memory_fact:r2", "memory_fact:r3", "memory_fact:r4"])]


def test_prune_noop_under_ceiling():
    rows = {t: _rows(t, 2) for t in ALL_MEMORY_TABLES}
    client = _FakeClient(rows)
    store = SurrealMemoryStore.from_test_client(client)

    deleted = store.prune(keep_per_table=10)

    assert deleted == {t: 0 for t in ALL_MEMORY_TABLES}
    assert client.deletes == []  # nothing deleted → no DELETE issued


def test_prune_query_shape_avoids_order_idiom_trap():
    """Pin the v0.8.19/v0.8.30 lesson: the SELECT must include created_at in
    its projection and must NOT use SELECT VALUE; eviction uses DELETE … IN."""
    client = _FakeClient({"memory_fact": _rows("memory_fact", 3),
                          "memory_preference": [], "memory_episode": []})
    store = SurrealMemoryStore.from_test_client(client)
    store.prune(keep_per_table=1)

    selects = [q for q, _ in client.queries if q.strip().startswith("SELECT id")]
    assert selects, "prune must SELECT id, created_at"
    for q in selects:
        assert "VALUE" not in q
        assert "created_at" in q.split("FROM")[0]
        assert "ORDER BY created_at DESC" in q
    deletes = [q for q, _ in client.queries if q.strip().startswith("DELETE")]
    assert all("WHERE id IN $ids" in q for q in deletes)


def test_prune_batches_large_eviction_lists():
    client = _FakeClient({"memory_fact": _rows("memory_fact", 2500),
                          "memory_preference": [], "memory_episode": []})
    store = SurrealMemoryStore.from_test_client(client)
    deleted = store.prune(keep_per_table=0)

    assert deleted["memory_fact"] == 2500
    fact_deletes = [d for d in client.deletes if d[0] == "memory_fact"]
    # 2500 ids → 3 batches of <=1000.
    assert len(fact_deletes) == 3
    assert sum(len(ids) for _, ids in fact_deletes) == 2500


def test_count_returns_row_count():
    client = _FakeClient({"memory_fact": _rows("memory_fact", 7)})
    store = SurrealMemoryStore.from_test_client(client)
    assert store.count("memory_fact") == 7
    assert store.count("memory_preference") == 0


# ---------------------------------------------------------------------------
# writer.prune_memories wrapper
# ---------------------------------------------------------------------------


class _FakeStore:
    def __init__(self, counts=None, raise_on_prune=False):
        self._counts = counts or {}
        self.raise_on_prune = raise_on_prune
        self.pruned_with = None

    def count(self, table):
        return self._counts.get(table, 0)

    def prune(self, keep):
        if self.raise_on_prune:
            raise RuntimeError("simulated store failure")
        self.pruned_with = keep
        return {t: 0 for t in ALL_MEMORY_TABLES}


class _FakeMemClient:
    def __init__(self, store):
        self.vector_store = store


def test_prune_memories_noop_without_vector_store():
    class _NoStore:
        pass
    assert writer_mod.prune_memories(_NoStore(), keep_per_table=10) == {}


def test_prune_memories_noop_when_store_lacks_prune():
    class _StoreNoPrune:
        pass
    assert writer_mod.prune_memories(_FakeMemClient(_StoreNoPrune()), 10) == {}


def test_prune_memories_always_prunes_without_high_water():
    store = _FakeStore()
    writer_mod.prune_memories(_FakeMemClient(store), keep_per_table=50)
    assert store.pruned_with == 50


def test_prune_memories_high_water_skips_under_threshold():
    # keep=100, high_water=1.5 → threshold 150; counts below → skip.
    store = _FakeStore(counts={t: 120 for t in ALL_MEMORY_TABLES})
    result = writer_mod.prune_memories(
        _FakeMemClient(store), keep_per_table=100, high_water=1.5,
    )
    assert result == {}
    assert store.pruned_with is None  # never pruned


def test_prune_memories_high_water_prunes_over_threshold():
    store = _FakeStore(counts={"memory_fact": 200, "memory_preference": 0,
                               "memory_episode": 0})
    writer_mod.prune_memories(
        _FakeMemClient(store), keep_per_table=100, high_water=1.5,
    )
    assert store.pruned_with == 100  # memory_fact 200 > 150 → pruned


def test_prune_memories_never_raises_on_store_error():
    store = _FakeStore(raise_on_prune=True)
    # Must swallow and return {} — retention failure can't break a write.
    assert writer_mod.prune_memories(_FakeMemClient(store), 10) == {}


# ---------------------------------------------------------------------------
# _keep_per_table env parsing
# ---------------------------------------------------------------------------


def test_keep_per_table_default(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_MEMORY_KEEP_PER_TABLE", raising=False)
    assert writer_mod._keep_per_table() == writer_mod._DEFAULT_KEEP_PER_TABLE


def test_keep_per_table_valid_override(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_KEEP_PER_TABLE", "1000")
    assert writer_mod._keep_per_table() == 1000


@pytest.mark.parametrize("bad", ["not-int", "0", "-5", ""])
def test_keep_per_table_falls_back_on_bad(monkeypatch, bad):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_KEEP_PER_TABLE", bad)
    assert writer_mod._keep_per_table() == writer_mod._DEFAULT_KEEP_PER_TABLE
