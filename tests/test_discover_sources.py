"""v0.8.87 — tests for the Discover Sources endpoint (guarded web search)."""

import deeper_notebook.tools.web_search as ws
from api.models import DiscoverSourcesRequest
from api.routers.notebooks import discover_sources


async def test_discover_disabled_when_no_provider(monkeypatch):
    monkeypatch.setattr(ws, "web_search_enabled", lambda: False)
    resp = await discover_sources("notebook:1", DiscoverSourcesRequest(query="ai"))
    assert resp.enabled is False
    assert resp.provider is None
    assert resp.results == []


async def test_discover_returns_mapped_results(monkeypatch):
    monkeypatch.setattr(ws, "web_search_enabled", lambda: True)
    monkeypatch.setattr(ws, "active_provider", lambda: "tavily")

    async def fake_search(query, *, max_results=None):
        return [
            {"title": "T1", "url": "https://example.com/a", "snippet": "s1"},
            {"title": "no url — dropped", "url": "", "snippet": "x"},
        ]

    monkeypatch.setattr(ws, "run_web_search", fake_search)

    resp = await discover_sources(
        "notebook:1", DiscoverSourcesRequest(query="ai agents", limit=5)
    )
    assert resp.enabled is True
    assert resp.provider == "tavily"
    # The result with an empty url is filtered out.
    assert len(resp.results) == 1
    assert resp.results[0].url == "https://example.com/a"
    assert resp.results[0].title == "T1"


async def test_discover_empty_query_short_circuits(monkeypatch):
    monkeypatch.setattr(ws, "web_search_enabled", lambda: True)
    monkeypatch.setattr(ws, "active_provider", lambda: "serper")

    async def boom(query, *, max_results=None):
        raise AssertionError("run_web_search should not be called for an empty query")

    monkeypatch.setattr(ws, "run_web_search", boom)

    resp = await discover_sources("notebook:1", DiscoverSourcesRequest(query="   "))
    assert resp.enabled is True
    assert resp.results == []


async def test_discover_degrades_to_empty_on_provider_error(monkeypatch):
    monkeypatch.setattr(ws, "web_search_enabled", lambda: True)
    monkeypatch.setattr(ws, "active_provider", lambda: "searxng")

    async def explode(query, *, max_results=None):
        raise RuntimeError("provider down")

    monkeypatch.setattr(ws, "run_web_search", explode)

    resp = await discover_sources("notebook:1", DiscoverSourcesRequest(query="ai"))
    assert resp.enabled is True
    assert resp.results == []  # best-effort, no 500
