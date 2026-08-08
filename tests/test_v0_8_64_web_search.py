"""v0.8.64 — native env-keyed web_search chat tool.

Covers the new `deeper_notebook/tools/web_search.py` module (provider detection,
per-provider request/parse, opt-in gating, formatting, the StructuredTool
builder + citation capture) AND its integration into the chat tool loop
(bound only when a key is set and not disabled via the MCP picker).

No live network: httpx.AsyncClient is monkeypatched. No secret values are ever
asserted on or logged.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from deeper_notebook.graphs import chat as chat_mod
from deeper_notebook.tools import web_search as ws

_ALL_ENV = (
    "SERPER_API_KEY",
    "TAVILY_API_KEY",
    "SEARXNG_BASE_URL",
    "DEEPER_NOTEBOOK_WEB_SEARCH_PROVIDER",
    "DEEPER_NOTEBOOK_WEB_SEARCH_MAX_RESULTS",
    "DEEPER_NOTEBOOK_WEB_SEARCH_TIMEOUT_SEC",
)


@pytest.fixture(autouse=True)
def _clean_web_env(monkeypatch):
    """Start every test from a fully unconfigured state so the host's real
    environment (or a stray .env) can't flip a provider on/off."""
    for name in _ALL_ENV:
        monkeypatch.delenv(name, raising=False)
    yield


# ---------------------------------------------------------------- httpx mock


def _fake_httpx(payload, *, raise_exc=None, calls=None):
    """Return a drop-in `httpx.AsyncClient` replacement.

    Records each call into `calls` (a list) and returns `payload` from
    `.json()`. If `raise_exc` is set, the request method raises it (to exercise
    the best-effort error path).
    """

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class _Client:
        def __init__(self, *a, **k):
            self._kw = k

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            if raise_exc is not None:
                raise raise_exc
            if calls is not None:
                calls.append(("post", url, kw))
            return _Resp()

        async def get(self, url, **kw):
            if raise_exc is not None:
                raise raise_exc
            if calls is not None:
                calls.append(("get", url, kw))
            return _Resp()

    return _Client


# ---------------------------------------------------------- provider detection


def test_disabled_with_no_env(monkeypatch):
    assert ws.active_provider() is None
    assert ws.web_search_enabled() is False


def test_serper_detected(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    assert ws.active_provider() == "serper"
    assert ws.web_search_enabled() is True


def test_precedence_serper_over_tavily_over_searxng(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://x")
    assert ws.active_provider() == "serper"


def test_tavily_when_only_tavily(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    assert ws.active_provider() == "tavily"


def test_searxng_when_only_searxng(monkeypatch):
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")
    assert ws.active_provider() == "searxng"


def test_whitespace_only_value_is_unset(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "   ")
    assert ws.active_provider() is None


def test_provider_override_respected(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_PROVIDER", "tavily")
    assert ws.active_provider() == "tavily"


def test_stale_override_ignored_when_provider_unconfigured(monkeypatch):
    # Override names searxng, but only serper is configured → fall back to serper
    # rather than silently disabling the working key.
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_PROVIDER", "searxng")
    assert ws.active_provider() == "serper"


# ------------------------------------------------------------------- tunables


def test_max_results_default_and_clamp(monkeypatch):
    assert ws._max_results() == 5
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_MAX_RESULTS", "3")
    assert ws._max_results() == 3
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_MAX_RESULTS", "9999")
    assert ws._max_results() == 20  # ceiling
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_MAX_RESULTS", "garbage")
    assert ws._max_results() == 5  # falls back


def test_timeout_default_and_clamp(monkeypatch):
    assert ws._timeout_sec() == 10.0
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_TIMEOUT_SEC", "0.1")
    assert ws._timeout_sec() == 1.0  # floor
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_TIMEOUT_SEC", "nope")
    assert ws._timeout_sec() == 10.0


def test_total_budget_default_and_clamp(monkeypatch):
    assert ws._total_budget_sec() == 25.0
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_TOTAL_BUDGET_SEC", "5")
    assert ws._total_budget_sec() == 5.0
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_TOTAL_BUDGET_SEC", "9999")
    assert ws._total_budget_sec() == 120.0  # ceiling
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_TOTAL_BUDGET_SEC", "garbage")
    assert ws._total_budget_sec() == 25.0  # falls back


# ---------------------------------------------------------- run_web_search()


@pytest.mark.asyncio
async def test_no_provider_returns_empty(monkeypatch):
    assert await ws.run_web_search("hello") == []


@pytest.mark.asyncio
async def test_blank_query_returns_empty(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    assert await ws.run_web_search("   ") == []


@pytest.mark.asyncio
async def test_serper_request_and_parse(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    calls: list = []
    payload = {
        "organic": [
            {"title": "T1", "link": "http://a", "snippet": "S1"},
            {"title": "T2", "link": "http://b", "snippet": "S2"},
        ]
    }
    monkeypatch.setattr(httpx, "AsyncClient", _fake_httpx(payload, calls=calls))
    out = await ws.run_web_search("python", max_results=2)
    assert out == [
        {"title": "T1", "url": "http://a", "snippet": "S1"},
        {"title": "T2", "url": "http://b", "snippet": "S2"},
    ]
    # hit the Serper endpoint with the query in the body
    method, url, kw = calls[0]
    assert method == "post"
    assert url == ws._SERPER_ENDPOINT
    assert kw["json"]["q"] == "python"


@pytest.mark.asyncio
async def test_tavily_request_and_parse(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    calls: list = []
    payload = {"results": [{"title": "Tv", "url": "http://t", "content": "C"}]}
    monkeypatch.setattr(httpx, "AsyncClient", _fake_httpx(payload, calls=calls))
    out = await ws.run_web_search("q")
    assert out == [{"title": "Tv", "url": "http://t", "snippet": "C"}]
    method, url, kw = calls[0]
    assert url == ws._TAVILY_ENDPOINT
    assert kw["json"]["query"] == "q"


@pytest.mark.asyncio
async def test_searxng_request_and_parse(monkeypatch):
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080/")  # trailing slash
    calls: list = []
    payload = {"results": [{"title": "Sx", "url": "http://s", "content": "C"}]}
    monkeypatch.setattr(httpx, "AsyncClient", _fake_httpx(payload, calls=calls))
    out = await ws.run_web_search("q")
    assert out == [{"title": "Sx", "url": "http://s", "snippet": "C"}]
    method, url, kw = calls[0]
    assert method == "get"
    assert url == "http://127.0.0.1:8080/search"  # trailing slash normalised
    assert kw["params"]["format"] == "json"


@pytest.mark.asyncio
async def test_error_degrades_to_empty(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_httpx({}, raise_exc=RuntimeError("boom"))
    )
    assert await ws.run_web_search("q") == []


@pytest.mark.asyncio
async def test_malformed_payload_degrades_to_empty(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    # Provider returns an unexpected shape (a list, or missing 'organic')
    monkeypatch.setattr(httpx, "AsyncClient", _fake_httpx({"unexpected": 1}))
    assert await ws.run_web_search("q") == []
    monkeypatch.setattr(httpx, "AsyncClient", _fake_httpx(["not", "a", "dict"]))
    assert await ws.run_web_search("q") == []


# ----------------------------------------------- v0.8.65 failover chain


def _scripted_httpx(handler, *, calls=None):
    """httpx.AsyncClient replacement where `handler(method, url, kw)` returns a
    payload dict/list OR raises (to simulate 429/timeout/connection error)."""

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            if calls is not None:
                calls.append(("post", url, kw))
            return _Resp(handler("post", url, kw))

        async def get(self, url, **kw):
            if calls is not None:
                calls.append(("get", url, kw))
            return _Resp(handler("get", url, kw))

    return _Client


def test_searxng_urls_parses_comma_and_space(monkeypatch):
    monkeypatch.setenv(
        "SEARXNG_BASE_URL",
        "https://a.example/, https://b.example/  https://c.example/",
    )
    assert ws._searxng_urls() == [
        "https://a.example/",
        "https://b.example/",
        "https://c.example/",
    ]


def test_provider_chain_auto_is_full_failover(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("SEARXNG_BASE_URL", "https://a.example/,https://b.example/")
    chain = ws._provider_chain()
    assert chain == [
        ("serper", None),
        ("tavily", None),
        ("searxng", "https://a.example/"),
        ("searxng", "https://b.example/"),
    ]
    assert ws.active_provider() == "serper"


def test_provider_chain_override_searxng_is_all_urls_only(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("SEARXNG_BASE_URL", "https://a.example/,https://b.example/")
    monkeypatch.setenv("DEEPER_NOTEBOOK_WEB_SEARCH_PROVIDER", "searxng")
    chain = ws._provider_chain()
    assert chain == [
        ("searxng", "https://a.example/"),
        ("searxng", "https://b.example/"),
    ]


@pytest.mark.asyncio
async def test_searxng_url_failover(monkeypatch):
    """First SearXNG instance 429s → second instance answers → results returned."""
    monkeypatch.setenv(
        "SEARXNG_BASE_URL", "https://down.example/,https://up.example/"
    )

    def handler(method, url, kw):
        if "down.example" in url:
            raise RuntimeError("429 Too Many Requests")
        return {"results": [{"title": "Up", "url": "http://up", "content": "c"}]}

    calls: list = []
    monkeypatch.setattr(httpx, "AsyncClient", _scripted_httpx(handler, calls=calls))
    out = await ws.run_web_search("q")
    assert out == [{"title": "Up", "url": "http://up", "snippet": "c"}]
    # both instances were attempted, in order
    assert calls[0][1].startswith("https://down.example")
    assert calls[1][1].startswith("https://up.example")


@pytest.mark.asyncio
async def test_cross_provider_failover_serper_to_tavily(monkeypatch):
    """Serper errors → Tavily is tried next and succeeds."""
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("TAVILY_API_KEY", "k")

    def handler(method, url, kw):
        if "serper" in url:
            raise RuntimeError("boom")
        return {"results": [{"title": "Tv", "url": "http://t", "content": "c"}]}

    monkeypatch.setattr(httpx, "AsyncClient", _scripted_httpx(handler))
    out = await ws.run_web_search("q")
    assert out == [{"title": "Tv", "url": "http://t", "snippet": "c"}]


@pytest.mark.asyncio
async def test_evidence_reports_provider_that_won_failover(monkeypatch):
    """Evidence names the provider that actually returned the fallback result."""
    monkeypatch.setenv("SERPER_API_KEY", "serper")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")

    def handler(method, url, kw):
        if "serper" in url:
            raise RuntimeError("serper unavailable")
        return {
            "results": [
                {
                    "title": "T",
                    "url": "https://example.com",
                    "content": "S",
                }
            ]
        }

    monkeypatch.setattr(httpx, "AsyncClient", _scripted_httpx(handler))
    evidence = await ws.run_web_search_with_evidence("q")

    assert evidence[0].provider == "tavily"
    assert evidence[0].degraded is True


@pytest.mark.asyncio
async def test_raw_web_search_wrapper_preserves_legacy_shape(monkeypatch):
    """The additive evidence path must not alter the raw search contract."""
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _scripted_httpx(
            lambda *args: {
                "results": [
                    {
                        "title": "T",
                        "url": "https://example.com",
                        "content": "S",
                    }
                ]
            }
        ),
    )

    assert await ws.run_web_search("q") == [
        {"title": "T", "url": "https://example.com", "snippet": "S"}
    ]


@pytest.mark.asyncio
async def test_paid_empty_stops_chain(monkeypatch):
    """A paid provider returning a legit empty 2xx is accepted — the chain does
    NOT cascade to the next paid provider (protects Tavily's limited quota)."""
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("TAVILY_API_KEY", "k")

    def handler(method, url, kw):
        if "serper" in url:
            return {"organic": []}  # legit empty
        raise AssertionError("tavily must not be reached on a paid empty result")

    calls: list = []
    monkeypatch.setattr(httpx, "AsyncClient", _scripted_httpx(handler, calls=calls))
    out = await ws.run_web_search("q")
    assert out == []
    assert len(calls) == 1  # only serper called


@pytest.mark.asyncio
async def test_all_attempts_fail_returns_empty(monkeypatch):
    monkeypatch.setenv("SEARXNG_BASE_URL", "https://a.example/,https://b.example/")

    def handler(method, url, kw):
        raise RuntimeError("down")

    monkeypatch.setattr(httpx, "AsyncClient", _scripted_httpx(handler))
    assert await ws.run_web_search("q") == []


@pytest.mark.asyncio
async def test_per_request_timeout_passed(monkeypatch):
    """Each attempt receives a per-request `timeout` kwarg so the chain can
    shrink later attempts as the total budget runs down (v0.8.65)."""
    monkeypatch.setenv("SERPER_API_KEY", "k")
    calls: list = []
    payload = {"organic": [{"title": "T", "link": "http://a", "snippet": "S"}]}
    monkeypatch.setattr(
        httpx, "AsyncClient", _scripted_httpx(lambda *a: payload, calls=calls)
    )
    await ws.run_web_search("q")
    assert calls, "no request was made"
    _, _, kw = calls[0]
    assert "timeout" in kw
    assert isinstance(kw["timeout"], (int, float)) and kw["timeout"] > 0


# ----------------------------------------------------------- format_results()


def test_format_results_empty():
    assert "No web results" in ws.format_results("q", [])


def test_format_results_numbered():
    text = ws.format_results(
        "q", [{"title": "T", "url": "http://u", "snippet": "S"}]
    )
    assert "[1]" in text and "http://u" in text and "T" in text


# ----------------------------------------------------- build_web_search_tool()


@pytest.mark.asyncio
async def test_tool_builder_name_and_capture(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")

    async def _fake_run(query, **kw):
        return [{"title": "T", "url": "http://x", "snippet": "S"}]

    monkeypatch.setattr(ws, "run_web_search", _fake_run)
    captures: list = []
    tool = ws.build_web_search_tool(captures)
    assert tool.name == "web_search"

    out = await tool.coroutine(query="hello")
    assert "T" in out and "http://x" in out
    assert len(captures) == 1
    cap = captures[0]
    assert cap["name"] == "web_search"
    assert cap["args"] == {"query": "hello"}
    assert cap["index"] == 1
    assert "blocks" in cap


# --------------------------------------------------------- loop integration


class _FakeAIMessage:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.content = ""


class _RecordingModel:
    """Mirrors test_v0_8_56's _ScriptedModel but records the bound tool list."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.bound = None

    def bind_tools(self, tools):
        self.bound = tools
        return self

    async def ainvoke(self, payload):
        if not self._responses:
            return _FakeAIMessage([])
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_loop_binds_web_search_when_key_set(monkeypatch):
    monkeypatch.setattr(
        chat_mod, "_resolve_chat_tools", AsyncMock(return_value=[])
    )
    monkeypatch.setenv("SERPER_API_KEY", "k")  # opt in
    model = _RecordingModel([_FakeAIMessage([])])
    await chat_mod.bind_mcp_and_run_tool_loop(model, [], max_iterations=2)
    assert model.bound is not None
    assert any(getattr(t, "name", None) == "web_search" for t in model.bound)


@pytest.mark.asyncio
async def test_loop_binds_web_search_even_when_mcp_resolve_fails(monkeypatch):
    """v0.8.65d — a DB/MCP-registry error must NOT drop the DB-independent
    web_search tool. Pre-fix, MCP resolve + web_search bind shared one
    try/except, so a SurrealDB blip during MCP server lookup silently disabled
    web search too."""

    async def _boom(**kwargs):
        raise RuntimeError("surrealdb unreachable")

    monkeypatch.setattr(chat_mod, "_resolve_chat_tools", _boom)
    monkeypatch.setenv("SERPER_API_KEY", "k")  # web search configured
    model = _RecordingModel([_FakeAIMessage([])])
    await chat_mod.bind_mcp_and_run_tool_loop(model, [], max_iterations=2)
    assert model.bound is not None, "web_search should still bind despite MCP failure"
    assert any(getattr(t, "name", None) == "web_search" for t in model.bound)


@pytest.mark.asyncio
async def test_loop_omits_web_search_without_key(monkeypatch):
    monkeypatch.setattr(
        chat_mod, "_resolve_chat_tools", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "deeper_notebook.tools.opencode.opencode_enabled", lambda: False
    )
    # no provider env → tool absent → with no MCP tools either, bind never runs
    model = _RecordingModel([_FakeAIMessage([])])
    await chat_mod.bind_mcp_and_run_tool_loop(model, [], max_iterations=2)
    assert model.bound is None


@pytest.mark.asyncio
async def test_loop_omits_web_search_when_disabled_by_picker(monkeypatch):
    monkeypatch.setattr(
        chat_mod, "_resolve_chat_tools", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "deeper_notebook.tools.opencode.opencode_enabled", lambda: False
    )
    monkeypatch.setenv("SERPER_API_KEY", "k")  # key set...
    model = _RecordingModel([_FakeAIMessage([])])
    # ...but the user disabled "web_search" via the per-request MCP picker
    await chat_mod.bind_mcp_and_run_tool_loop(
        model, [], max_iterations=2, exclude_server_names=["web_search"]
    )
    assert model.bound is None


# --------------------------------------------------- v0.8.65 status endpoint


def test_web_search_status_endpoint(monkeypatch):
    """GET /api/mcp/web-search reports availability + provider LABEL (no key),
    so the chat MCP picker can render a synthetic toggle."""
    from fastapi.testclient import TestClient

    # Importing api.main runs load_dotenv() on first import, which can
    # re-populate the real .env's keys AFTER conftest's autouse fixture cleared
    # them. Re-clear here so the 'disabled' assertion is order-independent.
    from api.main import app

    for name in _ALL_ENV:
        monkeypatch.delenv(name, raising=False)

    client = TestClient(app)

    r = client.get("/api/mcp/web-search")
    assert r.status_code == 200
    assert r.json() == {"enabled": False, "provider": None, "tool_name": "web_search"}

    # configure a provider → enabled, provider is a label only
    monkeypatch.setenv("SERPER_API_KEY", "k")
    r2 = client.get("/api/mcp/web-search")
    body = r2.json()
    assert body["enabled"] is True
    assert body["provider"] == "serper"
    assert body["tool_name"] == "web_search"
