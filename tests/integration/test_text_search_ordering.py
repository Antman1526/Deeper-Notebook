"""v0.8.114 — `fn::text_search` must return results sorted by relevance.

THE DEFECT

The final aggregation carried `GROUP BY` and `ORDER BY` on the same statement,
which SurrealDB 2.6.5 ignores, so `LIMIT` sliced an unordered set and the "top
N" was an arbitrary N. Measured on the live corpus before migration 50, for the
query "architecture":

    1.889, 1.2, 2.396, 2.586, 1.2

Unlike the vector-search defect this was never invisible — it looked like
"search quality is mediocre" rather than like a bug, which is why it survived
from migration 1. It matters more since v0.8.113, because hybrid search fuses
the legs by RANK, so an unordered leg feeds noise into the fusion.

WHY THESE TESTS REBUILD THE SEARCH INDEXES

`clean_namespace` truncates tables between tests with `DELETE`. SurrealDB's
BM25 index does not recompute its collection statistics on a bulk delete, so
every subsequent `search::score()` in that namespace returns exactly `0.0`.
That is not a product bug — nothing in the app bulk-deletes its whole corpus —
but it silently makes an ordering test VACUOUS: a list of identical zeros is
trivially "sorted", so the test passes whether or not the function orders
anything. The first version of this file did exactly that.

Rebuilding after seeding restores real scores. `_assert_scores_are_meaningful`
then refuses to let these tests pass on degenerate data again.

Static coverage that needs no database is in
`tests/test_v0_8_114_search_result_ordering.py`.
"""

from __future__ import annotations

import pytest

from deeper_notebook.database.repository import repo_query

pytestmark = pytest.mark.integration_surreal

# BM25 indexes over the tables `fn::text_search` reads.
_SEARCH_INDEXES = (
    ("source", "idx_source_full_text"),
    ("source", "idx_source_title"),
    ("source_embedding", "idx_source_embed_chunk"),
    ("source_insight", "idx_source_insight"),
    ("note", "idx_note"),
    ("note", "idx_note_title"),
)


async def _rebuild_search_indexes() -> None:
    for table, name in _SEARCH_INDEXES:
        try:
            await repo_query(f"REBUILD INDEX {name} ON TABLE {table}")
        except Exception:
            # An index a future migration renames or drops must not break the
            # test; the meaningfulness check below is what actually guards us.
            pass


async def _seed_documents() -> None:
    """Five documents whose term frequencies differ, so BM25 separates them.

    The rebuild happens BEFORE the inserts, not after. `clean_namespace` has
    just emptied the tables, and rebuilding on the emptied table is what resets
    the stale collection statistics; the rows inserted afterwards are then
    indexed normally. Rebuilding after the inserts instead leaves the first
    test in a session scoring every document 0.0 — observed exactly that way.
    """
    await _rebuild_search_indexes()
    for index, repeats in enumerate((6, 4, 3, 2, 1)):
        body = " ".join(["quantum"] * repeats + ["filler words here"])
        await repo_query(
            "CREATE source SET title = $title, asset = NONE, full_text = $body",
            {"title": f"Document {index}", "body": body},
        )


def _assert_scores_are_meaningful(rows: list[dict]) -> list[float]:
    """Refuse to draw conclusions from an all-identical score list."""
    scores = [float(row["relevance"]) for row in rows]
    assert len(set(scores)) > 1, (
        f"every relevance is identical ({scores}) — the BM25 index has no usable "
        "statistics, so an ordering assertion here would prove nothing."
    )
    return scores


async def test_text_search_orders_by_relevance_and_limits_to_the_best(
    clean_namespace,
):
    """Ordering AND the LIMIT slice, in one test on one seeded corpus.

    These were two tests. They are one because the BM25 collection statistics
    only reset reliably for the FIRST test to seed a namespace: `clean_namespace`
    empties the tables with DELETE, SurrealDB does not recompute the index
    statistics on a bulk delete, and a REBUILD only reliably takes for the first
    test in the session — so whichever ordering test ran second scored every
    document 0.0 and could only pass vacuously.

    Rather than assert on degenerate data or skip whenever it appears, both
    properties are checked against a single seeded corpus. Nothing is lost:
    they were always assertions about the same query.
    """
    await _seed_documents()

    everything = await repo_query(
        "RETURN fn::text_search($query, $match_count, true, true)",
        {"query": "quantum", "match_count": 10},
    )

    assert len(everything) >= 4, f"expected the documents to be found: {everything}"
    scores = _assert_scores_are_meaningful(everything)

    # 1. Results are sorted. This is the regression migration 50 fixes.
    assert scores == sorted(scores, reverse=True), (
        f"text search results are not ordered by relevance: {scores}"
    )

    # 2. LIMIT applies to the SORTED set, so match_count returns the BEST N and
    #    not an arbitrary N. Asserted on identity: a page can be internally
    #    ordered and still contain the wrong documents.
    #
    #    The expectation comes from the unlimited query rather than a prediction
    #    about term frequency. BM25 normalizes by document length and its IDF
    #    term goes NEGATIVE for a term present in most documents, so "more
    #    occurrences" does not imply "ranks higher" — an earlier version of this
    #    test hard-coded that assumption and failed against correct behaviour.
    expected = [row["title"] for row in everything[:2]]
    limited = await repo_query(
        "RETURN fn::text_search($query, $match_count, true, true)",
        {"query": "quantum", "match_count": 2},
    )

    assert len(limited) == 2
    assert [row["title"] for row in limited] == expected
