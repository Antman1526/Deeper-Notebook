"""Task 5 — real-Surreal search-quality measurements.

Every fixture in this module is disposable through ``clean_namespace``.  The
vectors deliberately include provider-shaped non-unit output: migration 51
ensures the shipped HNSW candidate indexes use the same cosine metric as
``fn::vector_search``'s final ranker.
"""

from __future__ import annotations

import math
import time

import pytest

from deeper_notebook.database.repository import (
    ensure_record_id,
    repo_insert,
    repo_query,
)
from deeper_notebook.domain.notebook import (
    Source,
    _wait_for_source_search_index_maintenance,
)

pytestmark = pytest.mark.integration_surreal

_DIMENSION = 768
_CANDIDATE_COUNT = 101
_BM25_INDEXES = (
    ("source", "idx_source_full_text"),
    ("source", "idx_source_title"),
    ("source_embedding", "idx_source_embed_chunk"),
)


def _vector(*, first: float, second: float = 0.0) -> list[float]:
    """Return a deterministic 768-dimensional vector without hidden scaling."""
    return [first, second, *([0.0] * (_DIMENSION - 2))]


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    assert left_norm > 0.0 and right_norm > 0.0
    return dot / (left_norm * right_norm)


def _unit_vector(seed: float) -> list[float]:
    raw = [math.sin(seed * 0.173 + index * 0.071) for index in range(_DIMENSION)]
    norm = math.sqrt(sum(value * value for value in raw))
    assert norm > 0.0
    return [value / norm for value in raw]


async def _rebuild_bm25_indexes() -> None:
    for table, index in _BM25_INDEXES:
        await repo_query(f"REBUILD INDEX {index} ON TABLE {table};")


def _assert_meaningful_text_rows(rows: list[dict]) -> tuple[list[str], list[float]]:
    titles = [str(row["title"]) for row in rows]
    scores = [float(row["relevance"]) for row in rows]
    assert len(titles) >= 2, f"benchmark needs at least two survivors: {rows!r}"
    assert len(set(titles)) == len(titles), f"search rows lost identity: {rows!r}"
    assert len({round(score, 12) for score in scores}) > 1, (
        f"vacuous BM25 scores cannot establish delete behavior: {scores!r}"
    )
    assert scores == sorted(scores, reverse=True), f"BM25 order is unstable: {scores!r}"
    return titles, scores


async def _seed_bm25_delete_fixture() -> tuple[Source, tuple[str, str]]:
    """Seed a product-deletable source and two independently scored survivors."""
    await _rebuild_bm25_indexes()
    sources: list[Source] = []
    for title, repeats in (
        ("retired field report", 7),
        ("surviving handbook", 4),
        ("surviving appendix", 1),
    ):
        source = Source(
            title=title,
            full_text=" ".join(["orbital"] * repeats + ["telemetry"] * 90),
        )
        await source.save()
        assert source.id is not None
        await repo_insert(
            "source_embedding",
            [
                {
                    "source": ensure_record_id(source.id),
                    "order": 0,
                    "content": " ".join(["orbital"] * repeats + ["trajectory"] * 45),
                    "embedding": _unit_vector(float(repeats)),
                }
            ],
        )
        sources.append(source)
    return sources[0], (str(sources[1].title), str(sources[2].title))


async def _text_search_rows() -> list[dict]:
    rows = await repo_query("RETURN fn::text_search('orbital', 10, true, false)")
    assert isinstance(rows, list)
    return rows


async def _seed_scale_mismatch_fixture() -> tuple[
    list[float], list[tuple[str, list[float]]]
]:
    """Seed more Euclidean-nearer decoys than the shipped KNN candidate cap.

    The exact-cosine winner has the same direction as the query but a magnitude
    of four.  Each unit-length decoy is closer in Euclidean space but less
    relevant in cosine space.  Since ``fn::vector_search`` requests only 100
    HNSW candidates, 101 decoys prove whether the candidate metric can exclude
    the true cosine winner before its final cosine sort runs.
    """
    query = _vector(first=1.0)
    candidates = [("cosine winner", _vector(first=4.0))]
    for index in range(_CANDIDATE_COUNT):
        cosine = 0.8 - (index * 0.003)
        candidates.append(
            (
                f"euclidean candidate {index:03d}",
                _vector(first=cosine, second=math.sqrt(1.0 - cosine * cosine)),
            )
        )

    sources = await repo_insert(
        "source",
        [
            {"title": title, "asset": None, "full_text": title}
            for title, _vector_value in candidates
        ],
    )
    assert len(sources) == len(candidates)
    await repo_insert(
        "source_embedding",
        [
            {
                "source": ensure_record_id(str(source["id"])),
                "order": 0,
                "content": title,
                "embedding": vector_value,
            }
            for source, (title, vector_value) in zip(sources, candidates)
        ],
    )
    return query, candidates


async def test_surreal_2_6_5_accepts_cosine_hnsw_indexes(clean_namespace) -> None:
    """Gate the migration on the exact local SurrealDB index syntax."""
    table = "task5_cosine_probe"
    index = "task5_cosine_probe_hnsw"
    try:
        await repo_query(f"DEFINE TABLE {table} SCHEMALESS;")
        await repo_query(
            f"DEFINE INDEX {index} ON {table} FIELDS embedding HNSW "
            "DIMENSION 768 DIST COSINE;"
        )
        info = await repo_query(f"INFO FOR TABLE {table};")
        metadata = info[0] if isinstance(info, list) else info
        assert isinstance(metadata, dict)
        definitions = (metadata.get("indexes") or {}).values()
        assert any("DIST COSINE" in definition.upper() for definition in definitions)
    finally:
        await repo_query(f"REMOVE TABLE IF EXISTS {table};")


async def _hnsw_definition(table: str, index: str) -> str:
    info = await repo_query(f"INFO FOR TABLE {table};")
    metadata = info[0] if isinstance(info, list) else info
    assert isinstance(metadata, dict)
    definition = (metadata.get("indexes") or {}).get(index)
    assert isinstance(definition, str), f"missing {table}.{index}: {metadata!r}"
    return " ".join(definition.split()).upper()


async def test_fixed_source_search_rebuild_marker_has_token_cas_on_surreal_2_6_5(
    clean_namespace,
) -> None:
    """A forced kill must leave a durable, generation-safe reconciliation marker."""
    marker = "open_notebook:source_search_rebuild_pending"
    first_token = "task5-first-token"
    second_token = "task5-second-token"

    written = await repo_query(
        "UPSERT open_notebook:source_search_rebuild_pending SET "
        "source_search_rebuild_pending = true, "
        "source_search_rebuild_token = $rebuild_token RETURN AFTER;",
        {"rebuild_token": first_token},
    )
    assert written and written[0]["source_search_rebuild_token"] == first_token

    replaced = await repo_query(
        "UPSERT open_notebook:source_search_rebuild_pending SET "
        "source_search_rebuild_pending = true, "
        "source_search_rebuild_token = $rebuild_token RETURN AFTER;",
        {"rebuild_token": second_token},
    )
    assert replaced and replaced[0]["source_search_rebuild_token"] == second_token

    stale_clear = await repo_query(
        "UPDATE open_notebook:source_search_rebuild_pending "
        "SET source_search_rebuild_pending = false, "
        "source_search_rebuild_token = NONE "
        "WHERE source_search_rebuild_token = $rebuild_token RETURN AFTER;",
        {"rebuild_token": first_token},
    )
    assert stale_clear == []
    preserved = await repo_query(f"SELECT * FROM {marker};")
    assert preserved and preserved[0]["source_search_rebuild_token"] == second_token

    cleared = await repo_query(
        "UPDATE open_notebook:source_search_rebuild_pending "
        "SET source_search_rebuild_pending = false, "
        "source_search_rebuild_token = NONE "
        "WHERE source_search_rebuild_token = $rebuild_token RETURN AFTER;",
        {"rebuild_token": second_token},
    )
    assert cleared and cleared[0]["source_search_rebuild_pending"] is False
    assert "source_search_rebuild_token" not in cleared[0]


async def test_hnsw_distance_migration_round_trips_all_shipped_indexes(
    clean_namespace,
    migration_rewind,
) -> None:
    """The reversible migration changes every search index, not just sources."""
    assert await migration_rewind(50) == 51
    indexes = (
        ("source_embedding", "source_embedding_hnsw"),
        ("source_insight", "source_insight_hnsw"),
        ("note", "note_hnsw"),
    )

    for table, index in indexes:
        assert "DIST EUCLIDEAN" in await _hnsw_definition(table, index)

    from deeper_notebook.database.async_migrate import AsyncMigrationManager

    manager = AsyncMigrationManager()
    await manager.run_migration_up()
    assert await manager.get_current_version() == 51
    for table, index in indexes:
        assert "DIST COSINE" in await _hnsw_definition(table, index)

    await manager.runner.run_one_down()
    assert await manager.get_current_version() == 50
    for table, index in indexes:
        assert "DIST EUCLIDEAN" in await _hnsw_definition(table, index)

    await manager.run_migration_up()
    assert await manager.get_current_version() == 51
    for table, index in indexes:
        assert "DIST COSINE" in await _hnsw_definition(table, index)


async def test_hnsw_candidate_metric_keeps_the_exact_cosine_winner(
    clean_namespace,
) -> None:
    """A non-unit stored vector must not be lost before cosine ranking.

    This is intentionally a strict RED on the shipped Euclidean indexes.  It
    compares a hand-computed, non-vacuous cosine ground truth with the public
    ``fn::vector_search`` path rather than a direct full-table cosine query.
    """
    query, candidates = await _seed_scale_mismatch_fixture()
    exact = sorted(
        ((title, _cosine(vector_value, query)) for title, vector_value in candidates),
        key=lambda item: item[1],
        reverse=True,
    )
    assert exact[0] == ("cosine winner", 1.0)
    assert exact[1][1] < exact[0][1]
    assert len({round(score, 9) for _title, score in exact}) > 2

    results = await repo_query(
        "RETURN fn::vector_search($query, 1, true, false, -1.0)",
        {"query": query},
    )

    assert results, "the benchmark fixture must produce a non-vacuous search result"
    assert results[0]["matches"] == [exact[0][0]], (
        "the HNSW candidate metric discarded the exact cosine winner before the "
        f"function's final cosine sort: expected={exact[0][0]!r}, got={results[0]!r}"
    )


async def test_bm25_scores_survive_a_product_source_delete_before_comparison_rebuild(
    clean_namespace,
) -> None:
    """Keep the retrieval identity/order after delete and later rebuild passes.

    SurrealDB 2.6.5's repeated ``REBUILD INDEX`` calls alter raw BM25 score
    magnitudes for this corpus.  Hybrid fusion consumes rank, not those raw
    values, so the product contract is meaningful, non-tied identity/order;
    it must not claim unsupported score-magnitude idempotence.
    """
    deleted, expected_survivors = await _seed_bm25_delete_fixture()
    before = await _text_search_rows()
    before_titles, before_scores = _assert_meaningful_text_rows(before)
    assert str(deleted.title) in before_titles

    assert await deleted.delete()
    await _wait_for_source_search_index_maintenance()
    after_delete = await _text_search_rows()
    after_titles, after_scores = _assert_meaningful_text_rows(after_delete)
    assert set(after_titles) == set(expected_survivors)

    await _rebuild_bm25_indexes()
    after_second_pass = await _text_search_rows()
    second_titles, second_scores = _assert_meaningful_text_rows(after_second_pass)
    await _rebuild_bm25_indexes()
    after_third_pass = await _text_search_rows()
    third_titles, third_scores = _assert_meaningful_text_rows(after_third_pass)
    observed = (
        f"before_delete={list(zip(before_titles, before_scores))!r}, "
        f"post_delete={list(zip(after_titles, after_scores))!r}, "
        f"second_pass={list(zip(second_titles, second_scores))!r}, "
        f"third_pass={list(zip(third_titles, third_scores))!r}"
    )
    assert second_titles == after_titles == third_titles, observed
    print(
        "task5-bm25 "
        f"before={list(zip(before_titles, before_scores))!r} "
        f"post_delete={list(zip(after_titles, after_scores))!r} "
        f"second_pass={list(zip(second_titles, second_scores))!r} "
        f"third_pass={list(zip(third_titles, third_scores))!r}"
    )


async def test_hnsw_recall_and_latency_for_the_shipped_candidate_authority(
    clean_namespace,
) -> None:
    """Measure deterministic exact-cosine recall for the shipped EF=100 path.

    EF=200 is measured only as a read-only comparator.  There is no safe
    parameterized production setting, so the benchmark must not tune either
    value from this test.
    """
    vectors = [_unit_vector(float(index)) for index in range(128)]
    sources = await repo_insert(
        "source",
        [
            {"title": f"recall corpus {index:03d}", "asset": None, "full_text": ""}
            for index in range(len(vectors))
        ],
    )
    embeddings = await repo_insert(
        "source_embedding",
        [
            {
                "source": ensure_record_id(str(source["id"])),
                "order": 0,
                "content": f"recall corpus {index:03d}",
                "embedding": vector,
            }
            for index, (source, vector) in enumerate(zip(sources, vectors))
        ],
    )
    candidates = [(str(row["id"]), vector) for row, vector in zip(embeddings, vectors)]
    query_indexes = (3, 47, 91)
    k = 10

    for ef in (100, 200):
        recalls: list[float] = []
        latencies_ms: list[float] = []
        for query_index in query_indexes:
            query = vectors[query_index]
            exact = {
                identity
                for identity, _score in sorted(
                    (
                        (identity, _cosine(vector, query))
                        for identity, vector in candidates
                    ),
                    key=lambda item: item[1],
                    reverse=True,
                )[:k]
            }
            started = time.perf_counter()
            rows = await repo_query(
                f"SELECT id FROM source_embedding WHERE embedding <|{k},{ef}|> $query;",
                {"query": query},
            )
            latencies_ms.append((time.perf_counter() - started) * 1_000)
            returned = {str(row["id"]) for row in rows}
            assert len(returned) == k, f"HNSW returned too few candidates: {rows!r}"
            recalls.append(len(returned & exact) / k)

        mean_recall = sum(recalls) / len(recalls)
        median_latency = sorted(latencies_ms)[len(latencies_ms) // 2]
        assert mean_recall >= 0.9, (
            f"HNSW recall@{k} is too low for a non-vacuous benchmark: {recalls!r}"
        )
        print(
            "task5-hnsw "
            f"ef={ef} recall_at_{k}={mean_recall:.3f} "
            f"median_latency_ms={median_latency:.3f} samples={len(latencies_ms)}"
        )
