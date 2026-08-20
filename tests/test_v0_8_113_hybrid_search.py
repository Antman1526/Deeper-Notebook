"""v0.8.113 — hybrid retrieval: fuse the two search legs instead of picking one.

`/api/search` ran exactly one leg and discarded the other. Keyword and semantic
retrieval fail in different directions — text search misses paraphrase, vector
search misses exact identifiers and error strings — so answering with one loses
recall on every query.

These pin the fusion's behaviour, and in particular the properties that make it
safe: it must never drop a result, never duplicate one, and never reorder
equal-scoring rows between identical calls.
"""

from __future__ import annotations

import pytest

from deeper_notebook.search.fusion import (
    DEFAULT_RRF_K,
    reciprocal_rank_fusion,
)


def _row(identifier: str, **extra):
    return {"id": identifier, **extra}


# --- core behaviour -----------------------------------------------------------


def test_a_document_found_by_both_legs_outranks_one_found_by_either():
    """The whole point: agreement between legs is evidence."""
    text = [_row("a"), _row("b")]
    vector = [_row("c"), _row("b")]

    fused = reciprocal_rank_fusion([text, vector], limit=10)

    assert [row["id"] for row in fused][0] == "b"


def test_every_input_row_survives_when_limit_allows():
    text = [_row("a"), _row("b")]
    vector = [_row("c")]

    fused = reciprocal_rank_fusion([text, vector], limit=10)

    assert sorted(row["id"] for row in fused) == ["a", "b", "c"]


def test_a_document_in_both_legs_appears_once():
    fused = reciprocal_rank_fusion([[_row("a")], [_row("a")]], limit=10)

    assert [row["id"] for row in fused] == ["a"]


def test_the_higher_ranked_leg_supplies_the_row():
    """Whichever leg ranked it higher had more confidence, so its fields win."""
    text = [_row("x"), _row("shared", origin="text")]
    vector = [_row("shared", origin="vector")]

    fused = reciprocal_rank_fusion([text, vector], limit=10)
    shared = next(row for row in fused if row["id"] == "shared")

    # vector ranked it #1, text ranked it #2 — vector's copy is kept.
    assert shared["origin"] == "vector"


def test_limit_is_respected():
    legs = [[_row(str(i)) for i in range(10)], [_row(str(i)) for i in range(10, 20)]]

    assert len(reciprocal_rank_fusion(legs, limit=5)) == 5


@pytest.mark.parametrize("limit", [0, -1])
def test_a_non_positive_limit_returns_nothing(limit):
    assert reciprocal_rank_fusion([[_row("a")]], limit=limit) == []


# --- degenerate inputs, which a search endpoint will absolutely see -----------


def test_one_empty_leg_degrades_to_the_other():
    """An unavailable embedding model must not empty the results."""
    fused = reciprocal_rank_fusion([[], [_row("a"), _row("b")]], limit=10)

    assert [row["id"] for row in fused] == ["a", "b"]


def test_all_legs_empty_yields_nothing_rather_than_raising():
    assert reciprocal_rank_fusion([[], []], limit=10) == []


def test_rows_without_an_id_are_kept_not_dropped():
    """Losing a result to a missing field is worse than ranking it poorly."""
    fused = reciprocal_rank_fusion([[{"title": "no id here"}], [_row("a")]], limit=10)

    assert len(fused) == 2


def test_alternate_id_spellings_still_fuse_as_one_document():
    """The two legs come from different SurrealQL functions."""
    fused = reciprocal_rank_fusion(
        [[{"item_id": "shared"}], [{"item_id": "shared"}]], limit=10
    )

    assert len(fused) == 1


def test_non_dict_rows_do_not_crash_the_fusion():
    fused = reciprocal_rank_fusion([["a string"], [_row("a")]], limit=10)

    assert len(fused) == 2


# --- properties that make it testable and trustworthy -------------------------


def test_identical_inputs_produce_identical_output():
    """A search endpoint that reshuffles ties between calls cannot be tested."""
    legs = [[_row("a"), _row("b"), _row("c")], [_row("c"), _row("a"), _row("b")]]

    first = [row["id"] for row in reciprocal_rank_fusion(legs, limit=10)]
    second = [row["id"] for row in reciprocal_rank_fusion(legs, limit=10)]

    assert first == second


def test_a_single_leg_preserves_its_own_ordering():
    """Fusing one leg must be a no-op, or hybrid could be worse than not fusing."""
    leg = [_row("a"), _row("b"), _row("c")]

    fused = reciprocal_rank_fusion([leg], limit=10)

    assert [row["id"] for row in fused] == ["a", "b", "c"]


def test_scores_use_rank_not_magnitude():
    """RRF exists because the legs' scores are incomparable.

    Vector search returns cosine similarity in [0, 1]; text search returns an
    unbounded SurrealDB relevance score. A blend would need calibration that
    rots as the corpus grows. Rank is immune, so a leg reporting enormous
    numbers must not gain any advantage.
    """
    modest = [_row("modest", score=0.01)]
    enormous = [_row("enormous", score=999_999.0)]

    fused = reciprocal_rank_fusion([modest, enormous], limit=10)

    # Both are rank 1 in their own leg, so they tie and first-seen order holds.
    assert [row["id"] for row in fused] == ["modest", "enormous"]


def test_k_damps_the_head_of_each_list():
    """Smaller k lets one leg's top hit outweigh agreement; larger k flattens it.

    The contest has to be genuinely close for k to matter: a single rank-1 hit
    against a document both legs rank DEEP. My first version of this test pitted
    rank-1 against a document ranked #2 and #1, which agreement wins at every
    value of k — it proved nothing.
    """
    # `agreed` must be buried in BOTH legs. My earlier attempts left it at rank 1
    # in the second leg, where its own 1/2 contribution decided the outcome and
    # k never mattered.
    deep = [_row("solo")] + [_row(f"filler{i}") for i in range(8)] + [_row("agreed")]
    other = [_row(f"other{i}") for i in range(9)] + [_row("agreed")]

    # k=1:    solo = 1/2 = 0.500   vs  agreed = 2 x 1/11 = 0.182  -> solo
    # k=1000: solo = 1/1001 ≈ 0.001 vs agreed = 2/1010 ≈ 0.002    -> agreed
    assert reciprocal_rank_fusion([deep, other], limit=10, k=1)[0]["id"] == "solo"
    assert reciprocal_rank_fusion([deep, other], limit=10, k=1000)[0]["id"] == "agreed"


def test_default_k_matches_the_published_constant():
    assert DEFAULT_RRF_K == 60


# --- the endpoint: hybrid must degrade, never fail ----------------------------


@pytest.mark.asyncio
async def test_hybrid_endpoint_fuses_both_legs(monkeypatch):
    """End to end through the router, with both legs stubbed."""
    from fastapi.testclient import TestClient

    import api.routers.search as search_router
    from api.main import app

    async def fake_vector(**_kwargs):
        return [{"id": "shared"}, {"id": "vector_only"}]

    async def fake_text(**_kwargs):
        return [{"id": "text_only"}, {"id": "shared"}]

    async def fake_embedding():
        return object()

    monkeypatch.setattr(search_router, "vector_search", fake_vector)
    monkeypatch.setattr(search_router, "text_search", fake_text)
    monkeypatch.setattr(
        search_router.model_manager, "get_embedding_model", fake_embedding
    )

    response = TestClient(app).post(
        "/api/search", json={"query": "anything", "type": "hybrid"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    ids = [row["id"] for row in body["results"]]

    assert body["search_type"] == "hybrid"
    # Found by both legs, so it outranks either leg's exclusive hit.
    assert ids[0] == "shared"
    assert set(ids) == {"shared", "vector_only", "text_only"}


@pytest.mark.asyncio
async def test_hybrid_degrades_to_text_when_no_embedding_model(monkeypatch):
    """The `vector` branch raises 400 here; hybrid must answer instead.

    An operator with no embedding model configured should still get results
    from a hybrid query rather than an error telling them to go configure one.
    """
    from fastapi.testclient import TestClient

    import api.routers.search as search_router
    from api.main import app

    async def fake_text(**_kwargs):
        return [{"id": "text_only"}]

    async def no_embedding():
        return None

    async def exploding_vector(**_kwargs):  # pragma: no cover - must never run
        raise AssertionError("vector leg must be skipped without an embedding model")

    monkeypatch.setattr(search_router, "text_search", fake_text)
    monkeypatch.setattr(search_router, "vector_search", exploding_vector)
    monkeypatch.setattr(
        search_router.model_manager, "get_embedding_model", no_embedding
    )

    response = TestClient(app).post(
        "/api/search", json={"query": "anything", "type": "hybrid"}
    )
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()["results"]] == ["text_only"]


@pytest.mark.asyncio
async def test_hybrid_survives_one_leg_erroring(monkeypatch):
    """One failing leg must not sink the query."""
    from fastapi.testclient import TestClient

    import api.routers.search as search_router
    from api.main import app

    async def fake_vector(**_kwargs):
        raise RuntimeError("index unavailable")

    async def fake_text(**_kwargs):
        return [{"id": "text_only"}]

    async def fake_embedding():
        return object()

    monkeypatch.setattr(search_router, "vector_search", fake_vector)
    monkeypatch.setattr(search_router, "text_search", fake_text)
    monkeypatch.setattr(
        search_router.model_manager, "get_embedding_model", fake_embedding
    )

    response = TestClient(app).post(
        "/api/search", json={"query": "anything", "type": "hybrid"}
    )
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()["results"]] == ["text_only"]


@pytest.mark.asyncio
async def test_hybrid_reports_504_only_when_every_leg_is_gone(monkeypatch):
    from fastapi.testclient import TestClient

    import api.routers.search as search_router
    from api.main import app

    async def boom(**_kwargs):
        raise RuntimeError("down")

    async def fake_embedding():
        return object()

    monkeypatch.setattr(search_router, "vector_search", boom)
    monkeypatch.setattr(search_router, "text_search", boom)
    monkeypatch.setattr(
        search_router.model_manager, "get_embedding_model", fake_embedding
    )

    response = TestClient(app).post(
        "/api/search", json={"query": "anything", "type": "hybrid"}
    )
    assert response.status_code == 504


def test_existing_search_types_are_unchanged():
    """Additive change: the default and both original modes still validate."""
    from api.models import SearchRequest

    assert SearchRequest(query="q").type == "text"
    assert SearchRequest(query="q", type="vector").type == "vector"
    assert SearchRequest(query="q", type="hybrid").type == "hybrid"
