"""v0.7.129 — End-to-end notebook lifecycle against a real SurrealDB.

What this catches that the mocked unit tests don't:

  * **Edge-table direction.** Multiple bugs in the past inverted `in`
    vs `out` in `reference` / `artifact` edges (CLAUDE.md root gotcha).
    A mocked unit test passes whichever direction you assert; the real
    DB only returns rows for the correct direction.

  * **Delete cascade.** `Notebook.delete()` cascades `reference`,
    `artifact`, and (with `delete_exclusive_sources=True`) source rows.
    A previous regression deleted only edges and orphaned sources;
    only a real-DB query against `SELECT count() FROM reference WHERE
    out = $nb` after delete would have caught it.

  * **Migration ordering.** The session fixture runs every forward
    migration (1..N) against a fresh namespace. A migration that
    silently depends on a later table would explode here, not in
    production.
"""

from __future__ import annotations

import pytest

from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.domain.notebook import Asset, Note, Notebook, Source

pytestmark = pytest.mark.integration_surreal


# ---------------------------------------------------------------------------
# Smoke test — proves the fixture itself works before we exercise domain code.
# A failure here means the fixture, migration runner, or SurrealDB connection
# is broken; downstream test failures with the same root cause would be
# harder to debug.
# ---------------------------------------------------------------------------


async def test_fixture_provisions_isolated_namespace(clean_namespace):
    """The session fixture must mint a unique throwaway namespace and
    leave it empty of user data before each test runs."""
    meta = clean_namespace
    assert meta["namespace"].startswith("onp_test_")
    assert meta["database"].startswith("onp_test_")

    # Every domain table should be empty post-truncate.
    for table in ("notebook", "source", "note", "reference", "artifact"):
        rows = await repo_query(f"SELECT count() AS n FROM {table} GROUP ALL;")
        # `GROUP ALL` returns `[]` for empty tables and `[{"n": <int>}]`
        # for non-empty ones — assert either explicitly so a future
        # SurrealDB version change to "always return one row with n=0"
        # doesn't silently break this assertion.
        n = rows[0]["n"] if rows else 0
        assert n == 0, f"Table {table} not empty: {n} rows"


# ---------------------------------------------------------------------------
# Edge-direction regression test
#
# `Notebook.get_sources()` runs:
#     select in as source from reference where out=$id fetch source
# meaning `reference.in` is the SOURCE and `reference.out` is the
# NOTEBOOK. Source.add_to_notebook() must therefore relate FROM source
# TO notebook. Any inversion (notebook → source) would make
# get_sources() return [] even with edges in the DB.
# ---------------------------------------------------------------------------


async def test_reference_edge_direction_source_to_notebook(clean_namespace):
    nb = Notebook(name="Research", description="Real-DB edge-direction test")
    await nb.save()
    assert nb.id is not None

    src = Source(
        title="Research paper",
        full_text="Hello SurrealDB",
        asset=Asset(url="https://example.com/paper"),
    )
    await src.save()
    assert src.id is not None

    # The method-under-test: should create reference edge with the
    # source as `in` and the notebook as `out`.
    await src.add_to_notebook(nb.id)

    # Verify via get_sources() — the production read path.
    fetched = await nb.get_sources()
    assert len(fetched) == 1
    assert str(fetched[0].id) == str(src.id)

    # Defensive: also assert the edge direction at the raw SurrealQL
    # level so a regression in get_sources() (e.g. swapping in/out in
    # the SELECT) doesn't accidentally mask a regression in
    # add_to_notebook().
    edges = await repo_query(
        "SELECT in, out FROM reference WHERE out = $nb",
        {"nb": ensure_record_id(nb.id)},
    )
    assert len(edges) == 1
    assert str(edges[0]["in"]) == str(src.id)
    assert str(edges[0]["out"]) == str(nb.id)


# ---------------------------------------------------------------------------
# Idempotency of add_to_notebook
#
# v0.7.NN history: Source.add_to_notebook used to create a duplicate
# reference edge on every call, so a UI double-click inflated
# source_count. The fix added a pre-check `SELECT * FROM reference
# WHERE out=$nb AND in=$src` and skipped relate() if it returned a row.
# ---------------------------------------------------------------------------


async def test_add_to_notebook_is_idempotent(clean_namespace):
    nb = Notebook(name="Idem", description="Dup-edge regression")
    await nb.save()
    src = Source(title="Doc", full_text="x")
    await src.save()

    await src.add_to_notebook(nb.id)
    await src.add_to_notebook(nb.id)  # Second call must be a no-op.

    edges = await repo_query(
        "SELECT count() AS n FROM reference WHERE out = $nb AND in = $src GROUP ALL;",
        {"nb": ensure_record_id(nb.id), "src": ensure_record_id(src.id)},
    )
    n = edges[0]["n"] if edges else 0
    assert n == 1, f"Expected exactly 1 reference edge, got {n}"


# ---------------------------------------------------------------------------
# Artifact-edge direction (note → notebook)
# ---------------------------------------------------------------------------


async def test_artifact_edge_direction_note_to_notebook(clean_namespace):
    nb = Notebook(name="Notes-NB", description="Artifact-edge direction")
    await nb.save()

    note = Note(title="Idea", content="Some idea text", note_type="human")
    await note.save()
    assert note.id is not None

    await note.add_to_notebook(nb.id)

    fetched = await nb.get_notes()
    assert len(fetched) == 1
    assert str(fetched[0].id) == str(note.id)

    edges = await repo_query(
        "SELECT in, out FROM artifact WHERE out = $nb",
        {"nb": ensure_record_id(nb.id)},
    )
    assert len(edges) == 1
    assert str(edges[0]["in"]) == str(note.id)


# ---------------------------------------------------------------------------
# Delete cascade — the big one
#
# Notebook.delete(delete_exclusive_sources=False) MUST:
#   * delete every `reference` edge with out=$nb
#   * delete every `artifact` edge with out=$nb
#   * leave the underlying source / note rows ALONE (other notebooks
#     might still reference them)
#
# A previous regression deleted only the reference edges and orphaned
# the artifacts. Without a real DB query against the artifact table
# after delete, that bug ships.
# ---------------------------------------------------------------------------


async def test_notebook_delete_cascades_edges_but_keeps_records(clean_namespace):
    nb = Notebook(name="Doomed", description="Cascade test")
    await nb.save()

    src = Source(title="S", full_text="t")
    await src.save()
    await src.add_to_notebook(nb.id)

    note = Note(title="N", content="c", note_type="human")
    await note.save()
    await note.add_to_notebook(nb.id)

    # Sanity — both edges exist before delete.
    pre_refs = await repo_query(
        "SELECT count() AS n FROM reference WHERE out = $nb GROUP ALL;",
        {"nb": ensure_record_id(nb.id)},
    )
    pre_arts = await repo_query(
        "SELECT count() AS n FROM artifact WHERE out = $nb GROUP ALL;",
        {"nb": ensure_record_id(nb.id)},
    )
    assert (pre_refs[0]["n"] if pre_refs else 0) == 1
    assert (pre_arts[0]["n"] if pre_arts else 0) == 1

    summary = await nb.delete(delete_exclusive_sources=False)

    # Edges gone…
    post_refs = await repo_query(
        "SELECT count() AS n FROM reference WHERE out = $nb GROUP ALL;",
        {"nb": ensure_record_id(nb.id)},
    )
    post_arts = await repo_query(
        "SELECT count() AS n FROM artifact WHERE out = $nb GROUP ALL;",
        {"nb": ensure_record_id(nb.id)},
    )
    assert (post_refs[0]["n"] if post_refs else 0) == 0
    assert (post_arts[0]["n"] if post_arts else 0) == 0

    # …but the source row itself still exists (delete_exclusive_sources=False).
    src_rows = await repo_query(
        "SELECT id FROM source WHERE id = $src",
        {"src": ensure_record_id(src.id)},
    )
    assert len(src_rows) == 1, "Source row was incorrectly deleted on notebook teardown"

    # The summary dict should report exactly what was nuked, using
    # the documented keys from Notebook.delete()'s docstring:
    # `deleted_notes`, `deleted_sources`, `unlinked_sources`.
    # (Original draft used invented `artifact_count` / `reference_count`
    # keys — caught by the first real CI run on v0.7.129c.)
    assert isinstance(summary, dict)
    assert summary.get("deleted_notes") == 1, (
        f"Expected 1 deleted note, got summary={summary}"
    )
    assert summary.get("unlinked_sources") == 1, (
        f"Expected 1 unlinked source, got summary={summary}"
    )
    # With delete_exclusive_sources=False, the source must NOT be in
    # deleted_sources — only unlinked.
    assert summary.get("deleted_sources") == 0, (
        f"Source was incorrectly deleted (should only be unlinked): {summary}"
    )


# ---------------------------------------------------------------------------
# Delete cascade with exclusive-source pruning
#
# When `delete_exclusive_sources=True`, sources that are *only*
# referenced by this notebook should be cascaded. Sources also
# referenced by another notebook must survive.
# ---------------------------------------------------------------------------


async def test_delete_exclusive_sources_prunes_orphans_only(clean_namespace):
    nb_a = Notebook(name="A", description="alpha")
    await nb_a.save()
    nb_b = Notebook(name="B", description="beta")
    await nb_b.save()

    shared = Source(title="Shared", full_text="cross-linked doc")
    await shared.save()
    exclusive = Source(title="Exclusive", full_text="lives only in A")
    await exclusive.save()

    await shared.add_to_notebook(nb_a.id)
    await shared.add_to_notebook(nb_b.id)
    await exclusive.add_to_notebook(nb_a.id)

    await nb_a.delete(delete_exclusive_sources=True)

    exclusive_rows = await repo_query(
        "SELECT id FROM source WHERE id = $src",
        {"src": ensure_record_id(exclusive.id)},
    )
    shared_rows = await repo_query(
        "SELECT id FROM source WHERE id = $src",
        {"src": ensure_record_id(shared.id)},
    )

    assert len(exclusive_rows) == 0, (
        "Source linked only to deleted notebook should have been cascaded"
    )
    assert len(shared_rows) == 1, (
        "Source still linked to notebook B must NOT be deleted"
    )
