"""v0.7.31 — regression tests for the /podcasts/suggest heuristics.

The endpoint analyzes selected notebook/source titles + topics + total
content volume and recommends:
  - episode_profile_name (one of v0.7.30's 9 presets)
  - length_minutes (calibrated to content volume)
  - title (from notebook name or first source)
  - briefing_addition (focuses preset on this content)

These tests pin the pure-function heuristics so a future tweak can't
silently regress the recommendation logic. The endpoint itself is
exercised via FastAPI TestClient with DB calls stubbed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import podcasts as podcasts_mod

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_score_signals_picks_tutorial_for_how_to():
    s = podcasts_mod._score_signals(
        "How to build a transformer · A beginners guide to attention"
    )
    assert s["Tutorial"] >= 2  # "how to" + "beginners"
    assert s["Tutorial"] > s["Deep Dive"]
    assert s["Tutorial"] > s["News Roundup"]


def test_score_signals_picks_debate_for_versus():
    s = podcasts_mod._score_signals(
        "Tabs vs Spaces · The case against semicolons · Pros and cons of CRDTs"
    )
    assert s["Debate"] >= 3
    assert s["Debate"] > max(v for k, v in s.items() if k != "Debate")


def test_score_signals_picks_review_for_book_keywords():
    s = podcasts_mod._score_signals(
        "Book review: Thinking Fast and Slow · A retrospective on Kahneman's thesis"
    )
    assert s["Recap & Review"] >= 2
    # "thesis" + "book" + "review" + "retrospective"


def test_score_signals_no_hits_returns_all_zero():
    s = podcasts_mod._score_signals("Random text without any signals at all")
    assert all(v == 0 for v in s.values())


def test_score_signals_picks_story_for_history():
    s = podcasts_mod._score_signals("The rise of Bitcoin · The history of CRDTs")
    assert s["Story Mode"] >= 2


def test_score_signals_picks_news_roundup():
    s = podcasts_mod._score_signals(
        "Daily AI news · This week in ML · Weekly roundup of papers"
    )
    assert s["News Roundup"] >= 3


def test_score_signals_picks_interview():
    s = podcasts_mod._score_signals(
        "Interview with Linus Torvalds · A conversation with Geoffrey Hinton"
    )
    assert s["Q&A Interview"] >= 2


# ---------------------------------------------------------------------------
# Length heuristic — volume → minutes
# ---------------------------------------------------------------------------


def test_length_quick_brief_for_small_content():
    assert podcasts_mod._length_from_volume(0, 0) == 4
    assert podcasts_mod._length_from_volume(2_500, 1) == 4
    assert podcasts_mod._length_from_volume(50_000, 1) == 4  # single source → brief


def test_length_standard_for_mid_content():
    assert podcasts_mod._length_from_volume(5_000, 3) == 7
    assert podcasts_mod._length_from_volume(14_999, 3) == 7


def test_length_medium_deep_for_large_content():
    assert podcasts_mod._length_from_volume(20_000, 5) == 11
    assert podcasts_mod._length_from_volume(59_999, 5) == 11


def test_length_deep_dive_for_huge_content():
    assert podcasts_mod._length_from_volume(60_000, 10) == 15
    assert podcasts_mod._length_from_volume(500_000, 50) == 15


# ---------------------------------------------------------------------------
# /podcasts/suggest endpoint — integration with stubbed DB
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_suggest():
    """Minimal FastAPI app exposing only /podcasts/suggest, so these
    tests don't need to spin up the full api.main lifespan."""
    a = FastAPI()
    a.include_router(podcasts_mod.router, prefix="/api")
    return a


def _make_repo_query_stub(
    *, notebook_name=None, source_ids=None, sources_data=None, presets=None
):
    """Build a stub for `repo_query` that returns the right shape per
    SQL query. Recognizes:
      - notebook name lookup
      - notebook → source ids edge fetch
      - sources INSIDE lookup
      - episode_profile name list
    """
    presets = presets or [
        "Open Notebook Plus Local",
        "Deep Dive",
        "Quick Brief",
        "Tutorial",
        "News Roundup",
        "Debate",
        "Recap & Review",
        "Story Mode",
        "Q&A Interview",
    ]
    source_ids = source_ids or []
    sources_data = sources_data or []

    async def stub(sql, vars=None):
        sql_lower = sql.lower()
        if "name from only" in sql_lower:
            return [{"name": notebook_name}] if notebook_name is not None else []
        if "<-reference<-source.id" in sql_lower:
            return [{"source_ids": source_ids}]
        if "from source where id inside" in sql_lower:
            return sources_data
        if "from episode_profile" in sql_lower:
            return [{"name": n} for n in presets]
        return []

    return stub


def test_suggest_recommends_tutorial_for_how_to_sources(app_with_suggest, monkeypatch):
    sources = [
        {
            "title": "How to build a CRDT",
            "topics": ["tutorial", "step-by-step"],
            "chars": 4000,
        },
        {"title": "A beginners guide to attention", "topics": [], "chars": 3000},
    ]
    monkeypatch.setattr(
        podcasts_mod,
        "repo_query",
        _make_repo_query_stub(
            source_ids=["source:1", "source:2"], sources_data=sources
        ),
    )
    with TestClient(app_with_suggest) as c:
        resp = c.post(
            "/api/podcasts/suggest",
            json={"source_ids": ["source:1", "source:2"]},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["episode_profile_name"] == "Tutorial"
    assert body["length_minutes"] == 7  # 7k chars + 2 sources → standard
    assert body["title"]  # not empty
    assert "Tutorial" in body["reasoning"]


def test_suggest_recommends_debate_for_versus_titles(app_with_suggest, monkeypatch):
    sources = [
        {"title": "Tabs vs Spaces", "topics": ["controversy"], "chars": 5000},
        {"title": "Pros and cons of CRDTs", "topics": [], "chars": 4000},
        {"title": "The case against semicolons", "topics": [], "chars": 3000},
    ]
    monkeypatch.setattr(
        podcasts_mod,
        "repo_query",
        _make_repo_query_stub(source_ids=["s:1", "s:2", "s:3"], sources_data=sources),
    )
    with TestClient(app_with_suggest) as c:
        resp = c.post(
            "/api/podcasts/suggest", json={"source_ids": ["s:1", "s:2", "s:3"]}
        )
    body = resp.json()
    assert body["episode_profile_name"] == "Debate"


def test_suggest_falls_back_to_quick_brief_when_small(app_with_suggest, monkeypatch):
    """One small source with no keyword signals → Quick Brief by volume rule."""
    sources = [{"title": "My note", "topics": [], "chars": 800}]
    monkeypatch.setattr(
        podcasts_mod,
        "repo_query",
        _make_repo_query_stub(source_ids=["s:1"], sources_data=sources),
    )
    with TestClient(app_with_suggest) as c:
        resp = c.post("/api/podcasts/suggest", json={"source_ids": ["s:1"]})
    body = resp.json()
    assert body["episode_profile_name"] == "Quick Brief"
    assert body["length_minutes"] == 4


def test_suggest_falls_back_to_deep_dive_when_huge(app_with_suggest, monkeypatch):
    """Large content with no keyword signals → Deep Dive by volume rule."""
    sources = [{"title": f"Doc {i}", "topics": [], "chars": 8000} for i in range(10)]
    monkeypatch.setattr(
        podcasts_mod,
        "repo_query",
        _make_repo_query_stub(
            source_ids=[f"s:{i}" for i in range(10)],
            sources_data=sources,
        ),
    )
    with TestClient(app_with_suggest) as c:
        resp = c.post(
            "/api/podcasts/suggest",
            json={"source_ids": [f"s:{i}" for i in range(10)]},
        )
    body = resp.json()
    assert body["episode_profile_name"] == "Deep Dive"
    assert body["length_minutes"] == 15


@pytest.mark.parametrize(
    ("presets", "expected"),
    [
        (
            ["Deep Dive", "Deeper Notebook Local", "Quick Brief"],
            "Deeper Notebook Local",
        ),
        (
            ["Deep Dive", "Open Notebook Plus Local", "Quick Brief"],
            "Open Notebook Plus Local",
        ),
        (
            [
                "Deep Dive",
                "Open Notebook Plus Local",
                "Deeper Notebook Local",
                "Quick Brief",
            ],
            "Deeper Notebook Local",
        ),
    ],
)
def test_suggest_medium_volume_matches_canonical_and_legacy_local_profile_names(
    app_with_suggest,
    monkeypatch,
    presets,
    expected,
):
    sources = [
        {"title": "Research A", "topics": [], "chars": 4_000},
        {"title": "Research B", "topics": [], "chars": 4_000},
    ]
    monkeypatch.setattr(
        podcasts_mod,
        "repo_query",
        _make_repo_query_stub(
            source_ids=["s:1", "s:2"],
            sources_data=sources,
            presets=presets,
        ),
    )

    with TestClient(app_with_suggest) as client:
        response = client.post(
            "/api/podcasts/suggest",
            json={"source_ids": ["s:1", "s:2"]},
        )

    assert response.status_code == 200
    assert response.json()["episode_profile_name"] == expected


def test_suggest_uses_notebook_title_when_provided(app_with_suggest, monkeypatch):
    sources = [{"title": "Source A", "topics": [], "chars": 5000}]
    monkeypatch.setattr(
        podcasts_mod,
        "repo_query",
        _make_repo_query_stub(
            notebook_name="Quantum Computing Research",
            source_ids=["s:1"],
            sources_data=sources,
        ),
    )
    with TestClient(app_with_suggest) as c:
        resp = c.post("/api/podcasts/suggest", json={"notebook_id": "notebook:42"})
    body = resp.json()
    assert body["title"] == "Quantum Computing Research"
    assert "Quantum Computing Research" in body["briefing_addition"]


def test_suggest_falls_back_when_chosen_preset_missing(app_with_suggest, monkeypatch):
    """User deleted 'Quick Brief'; the volume rule would pick it but
    we should fall back to the alphabetically-first available preset
    rather than recommend a non-existent name."""
    sources = [{"title": "Tiny", "topics": [], "chars": 500}]
    monkeypatch.setattr(
        podcasts_mod,
        "repo_query",
        _make_repo_query_stub(
            source_ids=["s:1"],
            sources_data=sources,
            presets=["Deep Dive", "Story Mode"],  # no Quick Brief
        ),
    )
    with TestClient(app_with_suggest) as c:
        resp = c.post("/api/podcasts/suggest", json={"source_ids": ["s:1"]})
    body = resp.json()
    assert body["episode_profile_name"] in {"Deep Dive", "Story Mode"}
    # Length rule unchanged — still 4 min for tiny content
    assert body["length_minutes"] == 4


def test_suggest_handles_empty_input(app_with_suggest, monkeypatch):
    """Nothing selected → don't crash. Return a sensible default."""
    monkeypatch.setattr(
        podcasts_mod,
        "repo_query",
        _make_repo_query_stub(source_ids=[], sources_data=[]),
    )
    with TestClient(app_with_suggest) as c:
        resp = c.post("/api/podcasts/suggest", json={})
    assert resp.status_code == 200
    body = resp.json()
    # Volume rule fires (0 sources → Quick Brief), title is fallback
    assert body["episode_profile_name"] in {"Quick Brief", "Open Notebook Plus Local"}
    assert body["title"] == "Untitled Episode"


def test_suggest_response_shape_stable(app_with_suggest, monkeypatch):
    """Every response must include all SuggestResponse keys so the
    frontend can rely on the shape without optional-chaining hell."""
    monkeypatch.setattr(
        podcasts_mod,
        "repo_query",
        _make_repo_query_stub(
            source_ids=["s:1"],
            sources_data=[{"title": "T", "topics": [], "chars": 1000}],
        ),
    )
    with TestClient(app_with_suggest) as c:
        resp = c.post("/api/podcasts/suggest", json={"source_ids": ["s:1"]})
    body = resp.json()
    for required in (
        "episode_profile_name",
        "length_minutes",
        "title",
        "briefing_addition",
        "reasoning",
        "matched_signals",
    ):
        assert required in body, f"missing key {required}"
    assert isinstance(body["matched_signals"], dict)
    assert isinstance(body["length_minutes"], int)
