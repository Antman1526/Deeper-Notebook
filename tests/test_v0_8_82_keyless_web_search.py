"""v0.8.82 — keyless web search, result cache, and pooled client.

Before this change a model had web reach only when the operator supplied a
Serper/Tavily key or self-hosted SearXNG. These tests pin the new contract: the
chain is never empty, the keyless provider sits strictly *after* the configured
ones, and the old key-only behaviour is restorable with a single env var.

No live network anywhere: ``httpx.AsyncClient`` is monkeypatched.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from deeper_notebook.environment import SETTINGS as _SETTINGS
from deeper_notebook.tools import web_search as ws


def _clear_setting(monkeypatch, canonical: str) -> None:
    """Delete a setting under every spelling the resolver accepts.

    Product env normalization mirrors a canonical name into its legacy aliases,
    and monkeypatch cannot undo writes it did not make — so a bare
    ``delenv(canonical)`` lets "disabled" leak into later test modules. The
    spellings come from the resolver's own registry rather than being written
    out here, so this stays correct if the alias scheme changes.
    """
    aliases = _SETTINGS.get(canonical)
    for name in aliases.precedence if aliases else (canonical,):
        monkeypatch.delenv(name, raising=False)


_KEY_ENV = (
    "SERPER_API_KEY",
    "TAVILY_API_KEY",
    "SEARXNG_BASE_URL",
    "BRAVE_API_KEY",
    "DEEPER_NOTEBOOK_WEB_SEARCH_PROVIDER",
    "DEEPER_NOTEBOOK_WEB_SEARCH_KEYLESS",
    "DEEPER_NOTEBOOK_WEB_SEARCH_CACHE_TTL_SEC",
    "DEEPER_NOTEBOOK_WEB_SEARCH_MAX_RESULTS",
)

WIKI_PAYLOAD = {
    "query": {
        "search": [
            {
                "title": "Ada Lovelace",
                "snippet": 'An <span class="searchmatch">English</span> mathematician',
            },
            {"title": "Analytical Engine", "snippet": "A <b>machine</b>"},
        ]
    }
}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in _KEY_ENV:
        monkeypatch.delenv(name, raising=False)
    for canonical in (
        "DEEPER_NOTEBOOK_WEB_SEARCH_KEYLESS",
        "BRAVE_API_KEY",
        "DEEPER_NOTEBOOK_WEB_SEARCH_PROVIDER",
        "DEEPER_NOTEBOOK_WEB_SEARCH_CACHE_TTL_SEC",
        "DEEPER_NOTEBOOK_WEB_SEARCH_MAX_RESULTS",
    ):
        _clear_setting(monkeypatch, canonical)
    ws.reset_web_search_caches()
    yield
    ws.reset_web_search_caches()


@pytest.fixture(autouse=True)
def _online(monkeypatch):
    """The chain short-circuits when offline; these tests assert chain walking."""

    class _Net:
        status = "online"

    async def _state():
        return _Net()

    monkeypatch.setattr(
        "deeper_notebook.health.network.get_network_state_with_settings", _state
    )
    yield


def _fake_client(*, json_payload=None, calls=None, fail=None):
    """Drop-in AsyncClient recording calls and returning a canned response."""

    class _Resp:
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return json_payload or {}

    class _Client:
        def __init__(self, *a, **k):
            self.is_closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def aclose(self):
            self.is_closed = True

        async def post(self, url, **kw):
            if fail:
                raise fail
            if calls is not None:
                calls.append(("post", url, kw))
            return _Resp()

        async def get(self, url, **kw):
            if fail:
                raise fail
            if calls is not None:
                calls.append(("get", url, kw))
            return _Resp()

    return _Client


# ------------------------------------------------------------------- the ask


def test_web_search_is_available_with_zero_configuration():
    """The headline change: a fresh install has web reach, no key required."""
    assert ws.web_search_enabled() is True
    assert ws.active_provider() == "wikipedia"


def test_keyless_kill_switch_restores_key_only_contract(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_KEYLESS", "0")
    assert ws.web_search_enabled() is False
    assert ws.active_provider() is None


def test_configured_key_still_wins_and_keyless_is_the_tail(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    chain = ws._provider_chain()
    assert chain[0] == ("serper", None)
    assert [p for p, _ in chain] == ["serper", "wikipedia"]


def test_full_chain_order_is_preserved_with_keyless_appended(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")
    assert [p for p, _ in ws._provider_chain()] == [
        "serper",
        "tavily",
        "searxng",
        "wikipedia",
    ]


def test_explicit_keyless_override_selects_only_that_provider(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_PROVIDER", "wikipedia")
    assert [p for p, _ in ws._provider_chain()] == ["wikipedia"]


# ----------------------------------------------------------------- end to end


def test_wikipedia_attempt_builds_urls_and_strips_markup(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_client(json_payload=WIKI_PAYLOAD, calls=calls)
    )
    results = asyncio.run(ws.run_web_search("ada lovelace"))
    assert results[0]["url"] == "https://en.wikipedia.org/wiki/Ada_Lovelace"
    # the <span class="searchmatch"> highlighting is stripped, text preserved
    assert results[0]["snippet"] == "An English mathematician"
    assert results[1]["url"] == "https://en.wikipedia.org/wiki/Analytical_Engine"
    assert calls[0][0] == "get"
    assert calls[0][1] == ws._wikipedia_endpoint()


def test_wikipedia_malformed_payload_degrades_to_empty(monkeypatch):
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_client(json_payload={"query": {"search": "nope"}})
    )
    assert asyncio.run(ws.run_web_search("q")) == []


def test_empty_free_attempt_falls_through_to_keyless(monkeypatch):
    """A SearXNG mirror answering 200-but-empty must not end the chain."""
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")
    seen: list = []

    async def _attempt(client, provider, target, query, n, timeout):
        seen.append(provider)
        if provider == "searxng":
            return []
        return [{"title": "t", "url": "https://w", "snippet": "s"}]

    monkeypatch.setattr(ws, "_do_attempt", _attempt)
    results = asyncio.run(ws.run_web_search("q"))
    assert seen == ["searxng", "wikipedia"]
    assert results[0]["url"] == "https://w"


def test_keyless_attempts_get_the_tighter_timeout(monkeypatch):
    seen: list = []

    async def _attempt(client, provider, target, query, n, timeout):
        seen.append((provider, timeout))
        return []

    monkeypatch.setattr(ws, "_do_attempt", _attempt)
    asyncio.run(ws.run_web_search("q"))
    assert seen, "chain did not run"
    for provider, timeout in seen:
        assert timeout <= ws._KEYLESS_TIMEOUT_SEC, (provider, timeout)


def test_transport_failure_still_degrades_to_empty(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(fail=RuntimeError("boom")))
    assert asyncio.run(ws.run_web_search("q")) == []


# --------------------------------------------------------------------- cache


def test_repeat_query_is_served_from_cache(monkeypatch):
    calls: list = []

    async def _attempt(client, provider, target, query, n, timeout):
        calls.append(query)
        return [{"title": "t", "url": "https://x", "snippet": "s"}]

    monkeypatch.setattr(ws, "_do_attempt", _attempt)
    first = asyncio.run(ws.run_web_search("same query"))
    second = asyncio.run(ws.run_web_search("same query"))
    assert first == second
    assert calls == ["same query"], "second search should not touch the network"


def test_cache_is_case_insensitive(monkeypatch):
    calls: list = []

    async def _attempt(client, provider, target, query, n, timeout):
        calls.append(query)
        return [{"title": "t", "url": "https://x", "snippet": "s"}]

    monkeypatch.setattr(ws, "_do_attempt", _attempt)
    asyncio.run(ws.run_web_search("Ada Lovelace"))
    asyncio.run(ws.run_web_search("ada lovelace"))
    assert len(calls) == 1


def test_cache_can_be_disabled(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_CACHE_TTL_SEC", "0")
    calls: list = []

    async def _attempt(client, provider, target, query, n, timeout):
        calls.append(query)
        return [{"title": "t", "url": "https://x", "snippet": "s"}]

    monkeypatch.setattr(ws, "_do_attempt", _attempt)
    asyncio.run(ws.run_web_search("q"))
    asyncio.run(ws.run_web_search("q"))
    assert len(calls) == 2


def test_empty_results_are_not_cached(monkeypatch):
    """A failed lookup must not poison the cache for five minutes."""
    calls: list = []

    async def _attempt(client, provider, target, query, n, timeout):
        calls.append(query)
        return []

    monkeypatch.setattr(ws, "_do_attempt", _attempt)
    asyncio.run(ws.run_web_search("q"))
    asyncio.run(ws.run_web_search("q"))
    assert len(calls) == 2, "empty result should not have been cached"


def test_cache_is_bounded(monkeypatch):
    async def _attempt(client, provider, target, query, n, timeout):
        return [{"title": "t", "url": "https://x", "snippet": "s"}]

    monkeypatch.setattr(ws, "_do_attempt", _attempt)
    for i in range(ws._CACHE_MAX_ENTRIES + 20):
        asyncio.run(ws.run_web_search(f"query {i}"))
    assert len(ws._cache) <= ws._CACHE_MAX_ENTRIES


# -------------------------------------------------------------------- client


def test_client_is_not_reused_across_different_patched_classes(monkeypatch):
    """The pool must never hand a later caller a previous caller's client."""
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(json_payload=WIKI_PAYLOAD))
    asyncio.run(ws.run_web_search("first"))
    first = ws._pooled_client
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(json_payload=WIKI_PAYLOAD))
    asyncio.run(ws.run_web_search("second"))
    assert ws._pooled_client is not first


def test_pooled_client_is_reused_for_repeat_searches(monkeypatch):
    """Same class + same loop → one client, so TLS connections stay warm."""
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(json_payload=WIKI_PAYLOAD))

    async def _two():
        await ws.run_web_search("alpha")
        first = ws._pooled_client
        await ws.run_web_search("beta")
        return first is ws._pooled_client

    assert asyncio.run(_two()) is True


# v0.8.85 — Brave provider + Wikipedia language edition.


def test_brave_sits_between_tavily_and_searxng(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("BRAVE_API_KEY", "k")
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")
    assert [p for p, _ in ws._provider_chain()] == [
        "serper",
        "tavily",
        "brave",
        "searxng",
        "wikipedia",
    ]


def test_brave_request_and_parse(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "brave-key")
    calls: list = []
    payload = {
        "web": {
            "results": [
                {"title": "T1", "url": "https://a", "description": "D1"},
                {"title": "T2", "url": "https://b", "description": "D2"},
            ]
        }
    }
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_client(json_payload=payload, calls=calls)
    )
    results = asyncio.run(ws.run_web_search("q"))
    assert calls[0][1] == ws._BRAVE_ENDPOINT
    assert calls[0][2]["headers"]["X-Subscription-Token"] == "brave-key"
    assert [r["snippet"] for r in results] == ["D1", "D2"]


def test_brave_override_selects_only_brave(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("BRAVE_API_KEY", "k")
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_PROVIDER", "brave")
    assert [p for p, _ in ws._provider_chain()] == ["brave"]


def test_wiki_lang_default_and_override(monkeypatch):
    assert ws._wikipedia_endpoint() == "https://en.wikipedia.org/w/api.php"
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_WIKI_LANG", "de")
    assert ws._wikipedia_endpoint() == "https://de.wikipedia.org/w/api.php"


def test_wiki_lang_rejects_garbage(monkeypatch):
    for bad in ("EN GB", "evil.example.com", "a", "x" * 20, "de/../en"):
        monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_WIKI_LANG", bad)
        assert ws._wikipedia_endpoint() == "https://en.wikipedia.org/w/api.php", bad


def test_wiki_result_urls_follow_language(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_WIKI_LANG", "fr")
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(json_payload=WIKI_PAYLOAD))
    results = asyncio.run(ws.run_web_search("ada"))
    assert results[0]["url"].startswith("https://fr.wikipedia.org/wiki/")
