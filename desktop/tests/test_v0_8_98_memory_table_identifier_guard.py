"""v0.8.98 — the memory store validates table identifiers by construction.

`SurrealMemoryStore.count(table)` interpolates its argument straight into
SurrealQL. Every caller today passes a member of ALL_MEMORY_TABLES, so it is
safe *by convention* — but the repository's SurrealQL contract requires
identifiers be whitelist-validated *by construction*, and the line carries a
a B608 suppression asserting exactly that. This suite makes it true:
a non-whitelisted identifier must be refused before it can reach a query
string, so the tag stops being a promise and becomes an enforced invariant.
"""

from __future__ import annotations

import pytest

from desktop.memory.constants import ALL_MEMORY_TABLES


def _store():
    """A store with a recording fake client, no live SurrealDB."""
    from desktop.memory.surreal_store import SurrealMemoryStore

    executed: list[str] = []

    class _FakeClient:
        def query(self, query, variables=None):  # noqa: ANN001 - test double
            executed.append(query)
            return [{"n": 0}]

    store = SurrealMemoryStore.from_test_client(_FakeClient())
    return store, executed


@pytest.mark.parametrize("table", ALL_MEMORY_TABLES)
def test_count_accepts_every_whitelisted_table(table: str) -> None:
    store, executed = _store()
    store.count(table)
    assert executed, "a whitelisted table must still reach the query path"
    assert table in executed[-1]


@pytest.mark.parametrize(
    "hostile",
    [
        "memory_fact; REMOVE TABLE memory_fact",
        "memory_fact WHERE 1=1",
        "not_a_table",
        "",
        "memory_fact\nDELETE memory_preference",
        "*",
    ],
)
def test_count_refuses_non_whitelisted_identifiers(hostile: str) -> None:
    """A hostile or unknown identifier must never reach the query string."""
    store, executed = _store()
    with pytest.raises(ValueError):
        store.count(hostile)
    assert executed == [], "refused identifiers must not execute any query"
