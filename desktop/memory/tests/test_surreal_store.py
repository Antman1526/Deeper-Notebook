from __future__ import annotations

from unittest.mock import MagicMock

# Importing _register installs the synthetic `mem0.configs.vector_stores.surreal`
# module — must happen before surreal_store is imported because surreal_store
# inherits from VectorStoreBase (a sibling of the synthetic module's parent pkg).
import pytest

# Importing _register installs the synthetic `mem0.configs.vector_stores.surreal`
# module — only meaningful when REAL mem0 is present (it inherits from mem0's
# VectorStoreBase then). In the lightweight dev/test venv mem0 is absent;
# surreal_store falls back to `object` for its base (see its defensive import),
# so the pure store-logic tests below — which all drive a MOCK client via
# `from_test_client` — run without standing up the whole mem0 stack. Guard the
# import so this file is collectable in both environments.
try:  # pragma: no cover - exercised only when mem0 is installed
    from desktop.memory import _register  # noqa: F401
except ImportError:  # pragma: no cover - mem0-less dev/test venv
    pass

from desktop.memory.surreal_store import (
    OutputData,
    SurrealMemoryStore,
    _validate_vector_id,
)


def _fake_client(responses: dict):
    """Mock pretending to be a surrealdb async client.

    Matches SurrealQL by prefix of the first non-whitespace word.
    """
    client = MagicMock()

    async def query(sql, vars=None):
        for prefix, resp in responses.items():
            if sql.strip().startswith(prefix):
                return resp
        return [[]]

    client.query.side_effect = query
    return client


def test_insert_routes_facts_to_memory_fact_table():
    store = SurrealMemoryStore.from_test_client(_fake_client({"CREATE": [[]]}))
    store.insert(
        vectors=[[0.1, 0.2, 0.3]],
        payloads=[
            {
                "kind": "fact",
                "text": "User likes coffee",
                "metadata": {"scope": "user"},
                "confidence": 0.9,
            }
        ],
        ids=["fact-001"],
    )
    sent_sql = store._client.query.call_args_list[0].args[0]
    assert "memory_fact" in sent_sql


def test_insert_routes_preferences_to_memory_preference_table():
    store = SurrealMemoryStore.from_test_client(_fake_client({"CREATE": [[]]}))
    store.insert(
        vectors=[[0.1]],
        payloads=[
            {
                "kind": "preference",
                "text": "bullets",
                "metadata": {"scope": "user"},
                "confidence": 0.85,
            }
        ],
        ids=["pref-001"],
    )
    sent_sql = store._client.query.call_args_list[0].args[0]
    assert "memory_preference" in sent_sql


def test_insert_reads_real_mem0_flat_payload():
    """v0.8.66 (audit C1) regression. With infer=False, mem0's _create_memory
    stores the verbatim text under the payload key `data` and FLATTENS the
    caller's metadata (kind/scope/confidence/…) onto the payload's top level —
    there is NO nested `metadata` sub-dict and NO `text` key. The store MUST
    read that real shape, otherwise every row persists text="" / scope="user"
    and the entire memory subsystem is silently inert (all unit tests still
    pass because they mocked the boundary)."""
    from datetime import datetime as _dt

    store = SurrealMemoryStore.from_test_client(_fake_client({"CREATE": [[]]}))
    store.insert(
        vectors=[[0.1, 0.2, 0.3]],
        payloads=[
            {
                # This is exactly what mem0 1.x emits to vector_store.insert():
                "data": "User prefers async meetings",
                "kind": "preference",
                "scope": "notebook",
                "confidence": 0.73,
                "hash": "deadbeef",
                "user_id": "local",
            }
        ],
        ids=["pref-flat-001"],
    )
    call = store._client.query.call_args_list[0]
    sent_sql = call.args[0]
    row = call.args[1]["row"]
    assert "memory_preference" in sent_sql  # routed by top-level kind
    assert row["text"] == "User prefers async meetings"  # read from `data`
    assert row["scope"] == "notebook"  # read from top-level scope
    assert row["confidence"] == 0.73  # read from top-level conf
    # H5: created_at is a native datetime, not an ISO string.
    assert isinstance(row["created_at"], _dt)
    # Bulky `data`/`embedding` are not duplicated into the metadata blob, but
    # the useful descriptive fields are preserved for recall filters.
    assert "data" not in row["metadata"]
    assert row["metadata"].get("kind") == "preference"
    assert row["metadata"].get("hash") == "deadbeef"


def test_insert_still_accepts_legacy_text_and_nested_metadata():
    """Back-compat: a caller passing the OLD shape (top-level `text` + a nested
    `metadata` dict carrying scope) must still round-trip correctly."""
    store = SurrealMemoryStore.from_test_client(_fake_client({"CREATE": [[]]}))
    store.insert(
        vectors=[[0.4]],
        payloads=[
            {
                "kind": "fact",
                "text": "legacy fact",
                "metadata": {"scope": "user"},
                "confidence": 0.6,
            }
        ],
        ids=["legacy-001"],
    )
    row = store._client.query.call_args_list[0].args[1]["row"]
    assert row["text"] == "legacy fact"
    assert row["scope"] == "user"
    assert row["confidence"] == 0.6


def test_search_returns_outputdata_objects():
    fake_record = {
        "id": "memory_fact:abc",
        "text": "user lives in SF",
        "metadata": {"scope": "user"},
        "confidence": 0.8,
        "created_at": "2026-05-11T00:00:00Z",
        "score": 0.92,
    }
    store = SurrealMemoryStore.from_test_client(
        _fake_client({"SELECT": [[fake_record]]})
    )
    # mem0 2.x signature: search(query, vectors, top_k, filters)
    hits = store.search(
        query="where does user live",
        vectors=[0.1, 0.2],
        top_k=5,
        filters={"kind": "fact"},
    )
    assert len(hits) == 1
    assert isinstance(hits[0], OutputData)
    assert hits[0].id == "memory_fact:abc"
    assert hits[0].payload["text"] == "user lives in SF"
    assert hits[0].score == 0.92


def test_delete_emits_delete_sql_with_id():
    store = SurrealMemoryStore.from_test_client(_fake_client({"DELETE": [[]]}))
    store.delete("memory_fact:abc")
    sent_sql = store._client.query.call_args_list[0].args[0]
    assert "DELETE" in sent_sql
    assert "memory_fact:abc" in sent_sql


def test_list_cols_returns_three_memory_tables():
    store = SurrealMemoryStore.from_test_client(_fake_client({}))
    cols = store.list_cols()
    assert set(cols) == {"memory_fact", "memory_preference", "memory_episode"}


def test_reset_removes_and_redefines_all_three_tables():
    store = SurrealMemoryStore.from_test_client(
        _fake_client({"REMOVE": [[]], "DEFINE": [[]]})
    )
    store.reset()
    sqls = " ".join(c.args[0] for c in store._client.query.call_args_list)
    for table in ("memory_fact", "memory_preference", "memory_episode"):
        assert table in sqls


@pytest.mark.parametrize(
    "good_id",
    [
        # Plain alphanumerics
        "memory_fact:abc",
        "memory_preference:abc-123_def",
        "memory_episode:01HJZ4K0R0XYZ",
        # mem0-generated IDs include periods (timestamps) and dots — P1-HIGH-06
        "memory_fact:01HF9G2K8M.x9z",
        "memory_fact:550e8400-e29b-41d4-a716-446655440000",  # UUID
        "memory_episode:chat.session.123",  # dotted path
        "memory_preference:0x7fff5fbff850",  # hex
    ],
)
def test_validate_vector_id_accepts_whitelisted_shapes(good_id):
    assert _validate_vector_id(good_id) == good_id


@pytest.mark.parametrize(
    "bad_id",
    [
        # Wrong table
        "memory_xyz:abc",
        "user:abc",
        # Injection attempts — must STILL be rejected even with the looser id char class
        "memory_fact:abc; DROP TABLE memory_fact",
        "memory_fact:abc'",
        'memory_fact:abc"',
        "memory_fact:abc\nDELETE memory_fact",
        "memory_fact:abc memory_fact:def",
        "memory_fact:abc(injected)",
        # Empty parts
        ":abc",
        "memory_fact:",
        "",
        # Wrong case
        "Memory_Fact:abc",
    ],
)
def test_validate_vector_id_rejects_invalid_shapes(bad_id):
    with pytest.raises(ValueError, match="Invalid vector_id"):
        _validate_vector_id(bad_id)


def test_delete_rejects_injection_before_hitting_surreal():
    store = SurrealMemoryStore.from_test_client(_fake_client({"DELETE": [[]]}))
    with pytest.raises(ValueError):
        store.delete("memory_fact:abc; DROP TABLE memory_fact")
    # No SQL should have reached the mock client.
    store._client.query.assert_not_called()


def test_update_rejects_injection_before_hitting_surreal():
    store = SurrealMemoryStore.from_test_client(_fake_client({"UPDATE": [[]]}))
    with pytest.raises(ValueError):
        store.update("memory_fact:abc'--", payload={"text": "x"})
    store._client.query.assert_not_called()


def test_get_rejects_injection_before_hitting_surreal():
    store = SurrealMemoryStore.from_test_client(_fake_client({"SELECT": [[]]}))
    with pytest.raises(ValueError):
        store.get("not a valid id")
    store._client.query.assert_not_called()


def test_keyword_search_returns_none():
    """We do not wire up SurrealDB FTS in v0.4; mem0 treats None as 'skip BM25'."""
    store = SurrealMemoryStore.from_test_client(_fake_client({}))
    assert store.keyword_search("anything") is None
