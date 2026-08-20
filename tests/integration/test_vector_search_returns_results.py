"""v0.8.114 — semantic search must actually return the documents it embedded.

THE DEFECT THIS EXISTS FOR

`fn::vector_search` used `<|100|>` (the MTREE form of SurrealDB's KNN operator)
against HNSW indexes. Nothing raised. The predicate simply matched nothing, so
every semantic query returned an empty list with HTTP 200 while the corpus sat
fully embedded. It survived from migration 21 because every surrounding signal
looked healthy: sources reported embedded, chunk counts were non-zero, the query
vector was a well-formed 768-dim array, the index reported the matching
DIMENSION and TYPE, and `REBUILD INDEX` returned OK.

The only thing that would have caught it is asking the database for results and
checking that some came back. That is all this file does.

`tests/test_v0_8_114_knn_operator_arity.py` guards the same defect statically and
runs unconditionally; this one is stronger but only runs with
`SURREAL_INTEGRATION=1`. Keep both.
"""

from __future__ import annotations

import math

import pytest

from deeper_notebook.database.repository import repo_query

pytestmark = pytest.mark.integration_surreal

# nomic-embed-text-v1.5's output size, which every HNSW index here declares.
_DIMENSION = 768


def _normalize(raw: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in raw))
    return [value / norm for value in raw]


def _unit_vector(seed: float) -> list[float]:
    """A deterministic, normalized 768-dim vector.

    Normalized because the function filters on cosine similarity and an
    unnormalized vector makes the threshold behave unpredictably across seeds —
    which would make a failure here ambiguous between "search is broken" and
    "the fixture picked a bad vector".
    """
    return _normalize([math.sin(seed + index) for index in range(_DIMENSION)])


async def _insert_embedded_source(content: str, vector: list[float]) -> None:
    created = await repo_query(
        "CREATE source SET title = $title, asset = NONE, full_text = $content",
        {"title": "vector search fixture", "content": content},
    )
    # repo_query runs results through parse_record_ids, which turns the RecordID
    # into the string "source:xxxx". Handing that straight back fails the
    # `record<source>` field type, so it is rebuilt into a record id server-side.
    table, _, identifier = str(created[0]["id"]).partition(":")
    await repo_query(
        "CREATE source_embedding SET source = type::thing($table, $identifier), "
        "order = 0, content = $content, embedding = $embedding",
        {
            "table": table,
            "identifier": identifier,
            "content": content,
            "embedding": vector,
        },
    )


async def test_vector_search_finds_an_embedded_chunk(clean_namespace):
    """The whole regression in one assertion: embed a chunk, search for it.

    Against the pre-fix function this returns `[]` — no error, no warning.
    """
    vector = _unit_vector(0.5)
    await _insert_embedded_source("the mitochondria is the powerhouse", vector)

    results = await repo_query(
        "RETURN fn::vector_search($query, $match_count, true, true, $min_similarity)",
        {"query": vector, "match_count": 10, "min_similarity": 0.0},
    )

    assert results, (
        "vector search returned nothing for a query vector identical to a stored "
        "embedding. If the KNN operator arity does not match the index type, this "
        "is exactly what it looks like: empty, silent, and successful."
    )


async def test_vector_search_returns_results_in_descending_similarity(clean_namespace):
    """Ordering, with enough documents that a wrong order cannot pass by luck.

    This is the test for the third defect. The final aggregation carried
    ORDER BY on the same statement as GROUP BY, which SurrealDB 2.6.5 ignores,
    so results came back unsorted and LIMIT sliced an arbitrary subset. Two
    documents were not enough to detect that — a shuffle of two is sorted half
    the time. Six graded documents make an accidental pass vanishingly unlikely.
    """
    query = _unit_vector(0.5)
    other = _unit_vector(40.0)

    # Graded blends: more `other` mixed in means lower cosine against `query`.
    for index, weight in enumerate((0.0, 0.2, 0.4, 0.6, 0.8, 1.0)):
        blended = _normalize([q + weight * o for q, o in zip(query, other)])
        await _insert_embedded_source(f"document {index}", blended)

    results = await repo_query(
        "RETURN fn::vector_search($query, $match_count, true, true, $min_similarity)",
        {"query": query, "match_count": 10, "min_similarity": 0.0},
    )

    assert len(results) >= 4, f"expected the graded documents to be found: {results}"
    similarities = [float(row["similarity"]) for row in results]
    assert similarities == sorted(similarities, reverse=True), (
        f"results are not ordered by similarity: {similarities}"
    )
    # The exact match must lead, not merely be present somewhere in the page.
    assert results[0]["matches"] == ["document 0"]


async def test_match_count_returns_the_best_matches_not_an_arbitrary_slice(
    clean_namespace,
):
    """LIMIT must apply to a SORTED set.

    With ordering broken, asking for the top 2 of 6 returned two arbitrary rows
    that happened to clear the threshold. Non-emptiness and even correct
    ordering *within the page* can both hold while the page itself is the wrong
    two documents, so this asserts on identity rather than on count.
    """
    query = _unit_vector(0.5)
    other = _unit_vector(40.0)

    for index, weight in enumerate((0.0, 0.2, 0.4, 0.6, 0.8, 1.0)):
        blended = _normalize([q + weight * o for q, o in zip(query, other)])
        await _insert_embedded_source(f"document {index}", blended)

    results = await repo_query(
        "RETURN fn::vector_search($query, $match_count, true, true, $min_similarity)",
        {"query": query, "match_count": 2, "min_similarity": 0.0},
    )

    assert len(results) == 2
    assert [row["matches"] for row in results] == [["document 0"], ["document 1"]]


async def test_min_similarity_still_filters(clean_namespace):
    """The threshold argument must keep working after the operator change.

    An impossible threshold must yield nothing — proving the empty result in the
    pre-fix state was a bug and not just how this function reports 'no match'.
    """
    vector = _unit_vector(0.5)
    await _insert_embedded_source("some content", vector)

    results = await repo_query(
        "RETURN fn::vector_search($query, $match_count, true, true, $min_similarity)",
        {"query": vector, "match_count": 10, "min_similarity": 1.1},
    )

    assert results == []
