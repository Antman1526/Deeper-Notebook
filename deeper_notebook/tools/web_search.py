"""v0.8.64 — Native env-keyed web-search tool for the chat tool loop.

Background
----------
Until now this fork's only web-search path was an MCP server the user had to
stand up themselves (the curated SearXNG / Crawl4AI recommendations in
``deeper_notebook/mcp/recommendations.py``). Users coming from upstream search
tools expect to drop a provider API key into ``.env`` and immediately get web
search in chat. This module adds exactly that: a built-in ``web_search`` tool
the chat model can call, backed by whichever provider key is present.

Providers
---------

==================== ================================= ==========================
Env var              Provider                          Notes
==================== ================================= ==========================
``SERPER_API_KEY``   Serper (Google Search API)        https://serper.dev
``TAVILY_API_KEY``   Tavily search API                 https://tavily.com
``BRAVE_API_KEY``    Brave Search API                  https://brave.com/search/api
``SEARXNG_BASE_URL`` A self-hosted SearXNG instance    e.g. ``http://127.0.0.1:8080``
*(none)*             Wikipedia ``api.php``             keyless, always available
==================== ================================= ==========================

Precedence is Serper > Tavily > Brave > SearXNG > Wikipedia, overridable via
``DEEPER_NOTEBOOK_WEB_SEARCH_PROVIDER`` (a stale override naming an unconfigured
provider is ignored, so it can't disable a perfectly good key).

v0.8.82 — default changed
-------------------------
This module used to be *default-off*: with no key, :func:`web_search_enabled`
returned ``False`` and the tool was never bound, leaving a local model with no
web reach at all. A keyless Wikipedia provider now sits at the tail of the
chain, so the tool exists on a fresh install.

Two honest limits on that:

* Wikipedia is encyclopedic, **not** a general web index. Questions about
  prices, live events, or anything post-dating an article will not be served
  well. Real general web search still needs one of the keys above — all three
  have a free tier.
* DuckDuckGo was evaluated as a keyless general provider and **rejected**: both
  its HTML endpoint and its official Instant Answer API answer HTTP 202 with an
  anti-bot challenge to scripted clients, so it would have shipped as a
  provider that silently returns nothing.

Set ``DEEPER_NOTEBOOK_WEB_SEARCH_KEYLESS=0`` to restore the previous key-only
contract exactly.

Latency
-------
``httpx.AsyncClient`` is pooled across calls (keep-alive instead of a fresh TLS
handshake per search) and identical recent queries are served from a bounded
TTL cache (``DEEPER_NOTEBOOK_WEB_SEARCH_CACHE_TTL_SEC``, default 300s, ``0``
disables). Empty results are never cached.

Safety
------
- All network I/O uses ``httpx.AsyncClient`` so the chat event loop never
  blocks (the recurring "sync-call-in-``async def``" bug class — see CLAUDE.md).
- Best-effort: any provider/transport error logs at WARNING and returns an
  empty result list; the chat turn continues (the model is told "no results"
  rather than the turn crashing).
- The API key is read from the environment and sent ONLY to the provider's
  HTTPS endpoint (or the user's own SearXNG URL). It is **never logged** — only
  the provider *name* and the error text appear in logs.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from collections import OrderedDict
from html import unescape

from loguru import logger

from deeper_notebook.environment import resolve_env
from deeper_notebook.tools.web_evidence import WebEvidence, normalize_web_results

__all__ = [
    "WEB_SEARCH_TOOL_NAME",
    "active_provider",
    "web_search_enabled",
    "keyless_enabled",
    "reset_web_search_caches",
    "run_web_search",
    "run_web_search_with_evidence",
    "format_results",
    "build_web_search_tool",
]

WEB_SEARCH_TOOL_NAME = "web_search"

_SERPER_ENDPOINT = "https://google.serper.dev/search"
_TAVILY_ENDPOINT = "https://api.tavily.com/search"
# v0.8.85 — Brave Search API (free tier: 2,000 queries/month). .env.example
# advertised it before the branch existed; now it is real.
_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

# v0.8.82 — keyless provider. Needs no API key and no self-hosting, so the
# chain is never empty and a local model has some web reach out of the box.
#
# Wikipedia's api.php is an official, stable, keyless JSON API. It is the only
# keyless *general* provider here on purpose: there is no free keyless
# general-web search engine. DuckDuckGo was evaluated and rejected — both its
# HTML endpoint and its Instant Answer API answer HTTP 202 with an anti-bot
# challenge for scripted clients, so it would have shipped as a provider that
# silently returns nothing. Real general web search still needs a (free-tier)
# key; see the provider table above.
_KEYLESS_PROVIDERS = ("wikipedia",)
_WIKI_LANG_PATTERN = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})?$")


def _wiki_lang() -> str:
    """v0.8.85 — Wikipedia language edition (DEEPER_NOTEBOOK_WEB_SEARCH_WIKI_LANG).

    Defaults to ``en``; anything that does not look like a Wikipedia language
    subdomain falls back rather than building a bogus hostname."""
    raw = _env("DEEPER_NOTEBOOK_WEB_SEARCH_WIKI_LANG").lower()
    return raw if raw and _WIKI_LANG_PATTERN.fullmatch(raw) else "en"


def _wikipedia_endpoint() -> str:
    return f"https://{_wiki_lang()}.wikipedia.org/w/api.php"


_DEFAULT_MAX_RESULTS = 5
_DEFAULT_TIMEOUT_SEC = 10.0
_MAX_RESULTS_CEILING = 20
_TIMEOUT_CEILING_SEC = 60.0
# Keyless attempts are cheap and never bill, so they get a tighter deadline than
# a paid provider: a slow free endpoint should yield to the next one quickly
# instead of eating the shared budget.
_KEYLESS_TIMEOUT_SEC = 6.0
# v0.8.65 — total wall-clock budget across the whole failover chain. Kept under
# the chat loop's per-tool-call timeout (DEEPER_NOTEBOOK_MCP_TOOL_TIMEOUT_SEC, default 30s)
# so web_search self-bounds + returns a graceful empty rather than being hard-
# killed mid-attempt. Each attempt gets min(per-attempt timeout, remaining
# budget) so a slow/hanging early instance can't starve a fast later one.
_DEFAULT_TOTAL_BUDGET_SEC = 25.0
_TOTAL_BUDGET_CEILING_SEC = 120.0

# v0.8.82 — latency work. Two costs dominated a web_search call: a fresh TLS
# handshake per call (the client was constructed per search) and re-running an
# identical query inside one agent loop. A pooled client fixes the first, a
# small TTL cache the second.
_DEFAULT_CACHE_TTL_SEC = 300.0
_CACHE_TTL_CEILING_SEC = 3600.0
_CACHE_MAX_ENTRIES = 128
_cache: "OrderedDict[tuple[str, int], tuple[float, list[dict], str | None, bool]]" = (
    OrderedDict()
)
_pooled_client = None
_pooled_client_loop = None
_pooled_client_factory = None


def _env(name: str) -> str:
    """Read an env var, trimmed; '' when unset. Centralised so empty/whitespace
    values are treated as unset everywhere (a blank key must not "enable" a
    provider that then 401s on every turn)."""
    if name.startswith("DEEPER_NOTEBOOK_"):
        return (resolve_env(name) or "").strip()
    return (os.environ.get(name) or "").strip()


def keyless_enabled() -> bool:
    """Whether the no-API-key provider may be used. Default ON.

    v0.8.82 deliberately flips this module's historical "no key → no tool"
    behaviour: the tool now exists by default so a local model can reach at
    least Wikipedia with zero setup. Set ``DEEPER_NOTEBOOK_WEB_SEARCH_KEYLESS=0``
    to restore the previous key-only contract (the whole tool then disappears
    again unless a key or SearXNG URL is configured).
    """
    raw = _env("DEEPER_NOTEBOOK_WEB_SEARCH_KEYLESS").lower()
    if raw in {"0", "false", "no", "off", "disabled"}:
        return False
    return True


def _cache_ttl_sec() -> float:
    raw = _env("DEEPER_NOTEBOOK_WEB_SEARCH_CACHE_TTL_SEC")
    if not raw:
        return _DEFAULT_CACHE_TTL_SEC
    try:
        t = float(raw)
    except ValueError:
        return _DEFAULT_CACHE_TTL_SEC
    return max(0.0, min(t, _CACHE_TTL_CEILING_SEC))


def _searxng_urls() -> list[str]:
    """Parse ``SEARXNG_BASE_URL`` into an ordered list of instance URLs.

    v0.8.65 — accepts a single URL or several separated by commas/whitespace,
    so the operator can list fallbacks. Public SearXNG instances frequently
    rate-limit (HTTP 429) or disable the JSON API, so :func:`run_web_search`
    tries each URL in order until one answers. Order in the env var = try order.
    """
    raw = _env("SEARXNG_BASE_URL")
    if not raw:
        return []
    return [u.strip() for u in re.split(r"[,\s]+", raw) if u.strip()]


def _provider_chain() -> list[tuple[str, str | None]]:
    """Ordered list of ``(provider, target)`` attempts to try in sequence.

    v0.8.65 — web search is now a *failover chain*, not a single provider:

    - With a valid ``DEEPER_NOTEBOOK_WEB_SEARCH_PROVIDER`` override → only that provider
      (SearXNG still expands to ALL its configured URLs for per-instance
      failover).
    - Otherwise (auto, or a stale override naming an unconfigured provider) →
      the full precedence chain Serper → Tavily → each SearXNG URL. Later
      entries act as failover only when an earlier attempt *errors*, so the
      happy path still stops at the first provider (no extra API spend).

    A stale override is ignored (falls back to auto) so it can't silently
    disable a perfectly good key.
    """
    serper = bool(_env("SERPER_API_KEY"))
    tavily = bool(_env("TAVILY_API_KEY"))
    brave = bool(_env("BRAVE_API_KEY"))
    searxng_urls = _searxng_urls()
    keyless = keyless_enabled()
    available = {
        "serper": serper,
        "tavily": tavily,
        "brave": brave,
        "searxng": bool(searxng_urls),
        "wikipedia": keyless,
    }

    chain: list[tuple[str, str | None]] = []

    def add(provider: str) -> None:
        if provider == "serper" and serper:
            chain.append(("serper", None))
        elif provider == "tavily" and tavily:
            chain.append(("tavily", None))
        elif provider == "brave" and brave:
            chain.append(("brave", None))
        elif provider == "searxng":
            for url in searxng_urls:
                chain.append(("searxng", url))
        elif provider in _KEYLESS_PROVIDERS and keyless:
            chain.append((provider, None))

    override = _env("DEEPER_NOTEBOOK_WEB_SEARCH_PROVIDER").lower()
    if override in available and available[override]:
        add(override)
    else:
        add("serper")
        add("tavily")
        add("brave")
        add("searxng")
        # v0.8.82 — keyless tail. Appended LAST so a configured key still wins
        # and no existing deployment changes behaviour; its only effect is that
        # an unconfigured install now has a working chain instead of none.
        for provider in _KEYLESS_PROVIDERS:
            add(provider)
    return chain


def active_provider() -> str | None:
    """Return the provider :func:`run_web_search` tries FIRST, or ``None`` if no
    provider is configured. (The full attempt order is :func:`_provider_chain`.)
    """
    chain = _provider_chain()
    return chain[0][0] if chain else None


def web_search_enabled() -> bool:
    """True iff at least one provider attempt (key or SearXNG URL) is configured."""
    return bool(_provider_chain())


def _max_results() -> int:
    raw = _env("DEEPER_NOTEBOOK_WEB_SEARCH_MAX_RESULTS")
    if not raw:
        return _DEFAULT_MAX_RESULTS
    try:
        n = int(raw)
    except ValueError:
        return _DEFAULT_MAX_RESULTS
    return max(1, min(n, _MAX_RESULTS_CEILING))


def _timeout_sec() -> float:
    raw = _env("DEEPER_NOTEBOOK_WEB_SEARCH_TIMEOUT_SEC")
    if not raw:
        return _DEFAULT_TIMEOUT_SEC
    try:
        t = float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT_SEC
    return max(1.0, min(t, _TIMEOUT_CEILING_SEC))


def _total_budget_sec() -> float:
    raw = _env("DEEPER_NOTEBOOK_WEB_SEARCH_TOTAL_BUDGET_SEC")
    if not raw:
        return _DEFAULT_TOTAL_BUDGET_SEC
    try:
        t = float(raw)
    except ValueError:
        return _DEFAULT_TOTAL_BUDGET_SEC
    return max(1.0, min(t, _TOTAL_BUDGET_CEILING_SEC))


def _normalise(items, *, url_key: str, snippet_key: str, n: int) -> list[dict]:
    """Map a provider's raw result list to ``[{title,url,snippet}]``.

    Defensive: a non-dict entry or a shape change degrades to skipped/empty
    rather than raising — the chat turn must survive a provider tweaking its
    JSON.
    """
    out: list[dict] = []
    for o in (items or [])[:n]:
        if not isinstance(o, dict):
            continue
        out.append(
            {
                "title": str(o.get("title") or ""),
                "url": str(o.get(url_key) or ""),
                "snippet": str(o.get(snippet_key) or ""),
            }
        )
    return out


async def _do_attempt(
    client, provider: str, target: str | None, query: str, n: int, timeout: float
) -> list[dict]:
    """Run ONE provider attempt. Raises on transport/HTTP error so the caller
    treats that attempt as failed and moves to the next in the chain.

    v0.8.65 — `timeout` is applied PER REQUEST (not on the client) so the chain
    can shorten later attempts as the total budget runs down.
    """
    if provider == "serper":
        resp = await client.post(
            _SERPER_ENDPOINT,
            headers={
                "X-API-KEY": _env("SERPER_API_KEY"),
                "Content-Type": "application/json",
            },
            json={"q": query, "num": n},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return _normalise(
            data.get("organic") if isinstance(data, dict) else None,
            url_key="link",
            snippet_key="snippet",
            n=n,
        )

    if provider == "tavily":
        resp = await client.post(
            _TAVILY_ENDPOINT,
            json={
                "api_key": _env("TAVILY_API_KEY"),
                "query": query,
                "max_results": n,
                "search_depth": "basic",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return _normalise(
            data.get("results") if isinstance(data, dict) else None,
            url_key="url",
            snippet_key="content",
            n=n,
        )

    if provider == "brave":
        resp = await client.get(
            _BRAVE_ENDPOINT,
            params={"q": query, "count": n},
            headers={
                "X-Subscription-Token": _env("BRAVE_API_KEY"),
                "Accept": "application/json",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        web = (data or {}).get("web") if isinstance(data, dict) else None
        return _normalise(
            web.get("results") if isinstance(web, dict) else None,
            url_key="url",
            snippet_key="description",
            n=n,
        )

    if provider == "wikipedia":
        resp = await client.get(
            _wikipedia_endpoint(),
            params={
                "action": "query",
                "list": "search",
                "format": "json",
                "srsearch": query,
                "srlimit": n,
            },
            headers={"User-Agent": "DeeperNotebook/1.0 (local research app)"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        hits = ((data or {}).get("query") or {}).get("search") or []
        out: list[dict] = []
        for hit in hits[:n]:
            if not isinstance(hit, dict):
                continue
            title = str(hit.get("title") or "")
            if not title:
                continue
            # `snippet` is HTML with <span class="searchmatch"> highlighting.
            snippet = unescape(re.sub(r"<[^>]+>", "", str(hit.get("snippet") or "")))
            out.append(
                {
                    "title": title,
                    "url": f"https://{_wiki_lang()}.wikipedia.org/wiki/"
                    + title.replace(" ", "_"),
                    "snippet": snippet.strip(),
                }
            )
        return out

    # searxng — `target` is the specific instance URL for this attempt.
    base = (target or "").rstrip("/")
    resp = await client.get(
        f"{base}/search",
        params={"q": query, "format": "json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return _normalise(
        data.get("results") if isinstance(data, dict) else None,
        url_key="url",
        snippet_key="content",
        n=n,
    )


async def _acquire_client() -> tuple[object, bool]:
    """Return ``(client, pooled)``; the caller closes it only when not pooled.

    Reusing one ``httpx.AsyncClient`` keeps TLS connections alive between tool
    calls, which is where most of a repeat search's latency went. Two guards
    keep the pool honest:

    * the client is rebuilt when the running event loop changes (a pooled
      client is bound to the loop that created it); and
    * it is rebuilt when ``httpx.AsyncClient`` is not the object the pool was
      built from, so a monkeypatched client in a test is never served from a
      previous test's pool.
    """
    global _pooled_client, _pooled_client_loop, _pooled_client_factory
    import httpx

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    factory = httpx.AsyncClient
    if (
        _pooled_client is not None
        and _pooled_client_loop is loop
        and _pooled_client_factory is factory
        and not getattr(_pooled_client, "is_closed", False)
    ):
        return _pooled_client, True

    # Redirect policy is deliberately left at the httpx default (off) so every
    # attempt behaves exactly as it did before pooling was introduced.
    try:
        client = factory(
            limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
        )
    except Exception:  # pragma: no cover - defensive against client API drift
        client = factory()
    _pooled_client = client
    _pooled_client_factory = factory
    _pooled_client_loop = loop
    return client, True


def reset_web_search_caches() -> None:
    """Drop the result cache and forget the pooled client. For tests/teardown."""
    global _pooled_client, _pooled_client_loop
    _cache.clear()
    _pooled_client = None
    _pooled_client_loop = None


def _cache_get(key: tuple[str, int]):
    ttl = _cache_ttl_sec()
    if ttl <= 0:
        return None
    entry = _cache.get(key)
    if entry is None:
        return None
    stored_at, results, provider, degraded = entry
    if time.monotonic() - stored_at > ttl:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return list(results), provider, degraded


def _cache_put(key: tuple[str, int], results, provider, degraded) -> None:
    if _cache_ttl_sec() <= 0 or not results:
        return
    _cache[key] = (time.monotonic(), list(results), provider, degraded)
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)


async def _run_web_search_result(
    query: str, *, max_results: int | None = None
) -> tuple[list[dict], str | None, bool]:
    """Run one web search failover chain and return result metadata.

    v0.8.65 — tries each attempt in :func:`_provider_chain` in order:
      * an attempt that *errors* (timeout, 429, connection refused, non-2xx)
        falls through to the next attempt;
      * a SearXNG attempt that returns no results also falls through (a blocked
        JSON mirror often answers 200-but-empty) — it's free, so try the next;
      * a paid provider (Serper/Tavily) returning a legitimate empty 2xx result
        is accepted as-is rather than spending quota on the next paid provider.

    The whole chain is bounded by a total wall-clock budget
    (``DEEPER_NOTEBOOK_WEB_SEARCH_TOTAL_BUDGET_SEC``, default 25s, kept under the chat
    loop's 30s per-tool-call timeout) and each attempt gets
    ``min(per-attempt timeout, remaining budget)`` so a slow/hanging early
    instance can't starve a fast later one or freeze the chat turn.

    Returns ``[]`` if every attempt fails. Never raises into the chat turn.
    """
    chain = _provider_chain()
    query = (query or "").strip()
    if not chain or not query:
        return [], None, False

    # v0.8.68 — offline short-circuit (spec §6). Without this, an offline
    # machine burned the full 25s provider-failover budget per tool call
    # before returning empty. The model still gets the standard empty-result
    # shape; the log line tells the operator why. SearXNG note: a self-hosted
    # instance on localhost would also be skipped here, but a localhost
    # SearXNG can't search the web without internet anyway.
    from deeper_notebook.health.network import get_network_state_with_settings

    _net = await get_network_state_with_settings()
    if _net.status == "offline":
        logger.info("v0.8.68 web_search skipped: device offline")
        return [], None, False

    n = max_results if (max_results and max_results > 0) else _max_results()

    # v0.8.82 — serve an identical recent query from memory. Agent loops
    # re-issue the same search often; this turns the repeat into a no-op.
    cache_key = (query.casefold(), n)
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("web_search cache hit for {!r}", query)
        return cached

    per_attempt_cap = _timeout_sec()
    deadline = time.monotonic() + _total_budget_sec()

    # No fixed client timeout — each request gets a per-call timeout below so
    # the chain can shrink later attempts as the budget runs down.
    client, pooled = await _acquire_client()
    try:
        for attempt_index, (provider, target) in enumerate(chain):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.debug(
                    "web_search total budget exhausted; stopping failover chain"
                )
                break
            cap = (
                min(per_attempt_cap, _KEYLESS_TIMEOUT_SEC)
                if provider in _KEYLESS_PROVIDERS
                else per_attempt_cap
            )
            attempt_timeout = min(cap, remaining)
            try:
                results = await _do_attempt(
                    client, provider, target, query, n, attempt_timeout
                )
            except Exception as exc:
                # WARNING (not DEBUG): a *configured* attempt failing is worth
                # seeing. We log provider + (for searxng) the instance URL +
                # error text — NEVER the API key (which lives in the request
                # headers/body, not in `exc`'s string form for these endpoints).
                logger.warning(
                    "web_search attempt via {}{} failed: {}",
                    provider,
                    f" ({target})" if target else "",
                    exc,
                )
                continue
            if results:
                _cache_put(cache_key, results, provider, attempt_index > 0)
                return results, provider, attempt_index > 0
            if provider == "searxng" or provider in _KEYLESS_PROVIDERS:
                # Free attempt answered 200-but-empty (a blocked mirror, or a
                # layout change the parser no longer recognises). Costs nothing
                # to try the next one.
                logger.debug(
                    "web_search {} {} returned no results; trying next",
                    provider,
                    target or "",
                )
                continue
            # Paid provider returned a legitimate empty result — accept it.
            return results, provider, attempt_index > 0
    finally:
        if not pooled:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - best-effort cleanup
                pass
    return [], None, False


async def run_web_search(query: str, *, max_results: int | None = None) -> list[dict]:
    """Run a web search while preserving the legacy raw result shape."""
    results, _provider, _degraded = await _run_web_search_result(
        query, max_results=max_results
    )
    return results


async def run_web_search_with_evidence(
    query: str, *, max_results: int | None = None
) -> tuple[WebEvidence, ...]:
    """Run the existing provider chain and return immutable evidence records."""
    results, provider, degraded = await _run_web_search_result(
        query, max_results=max_results
    )
    if not results or provider is None:
        return ()
    return normalize_web_results(
        results,
        query=query,
        provider=provider,
        max_results=max_results,
        degraded=degraded,
    )


def format_results(query: str, results: list[dict]) -> str:
    """Render results into the plain-text block the model reads as a
    ToolMessage. Numbered so the model can cite ``[1]``/``[2]`` inline."""
    if not results:
        return f"No web results found for {query!r}."
    lines = [f"Web search results for {query!r}:"]
    for i, r in enumerate(results, 1):
        title = r.get("title") or "(untitled)"
        url = r.get("url") or ""
        snippet = r.get("snippet") or ""
        lines.append(f"[{i}] {title}\n{url}\n{snippet}".rstrip())
    return "\n\n".join(lines)


def build_web_search_tool(captures: list | None = None):
    """Build the ``StructuredTool`` the chat model binds + invokes.

    Mirrors the MCP ``_make_tool`` capture shape (``{index, name, args, text,
    blocks}``) so web results render as the same citation pills as MCP tool
    results. ``captures`` is the shared per-turn accumulator from
    ``bind_mcp_and_run_tool_loop`` (may be ``None`` in unit tests).
    """
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    provider = active_provider() or "web"

    class WebSearchInput(BaseModel):
        query: str = Field(..., description="The search query to run on the web.")

    async def _invoke(query: str) -> str:
        results = await run_web_search(query)
        text = format_results(query, results)
        if captures is not None:
            captures.append(
                {
                    "index": len(captures) + 1,
                    "name": WEB_SEARCH_TOOL_NAME,
                    "args": {"query": query},
                    "text": text[:4000],
                    "blocks": [],
                }
            )
        return text

    return StructuredTool.from_function(
        coroutine=_invoke,
        name=WEB_SEARCH_TOOL_NAME,
        description=(
            f"Search the public web (via {provider}) for current or up-to-date "
            "information that is NOT in the notebook context. Returns a ranked "
            "list of result titles, URLs, and snippets. Use this when the user "
            "asks about recent events, live facts, prices, or anything outside "
            "the provided sources."
        ),
        args_schema=WebSearchInput,
    )
