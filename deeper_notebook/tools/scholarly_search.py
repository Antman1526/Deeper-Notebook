"""v0.8.82 — keyless scholarly search for the chat tool loop.

Why a second tool instead of more `web_search` providers
--------------------------------------------------------
``web_search``'s keyless tail is Wikipedia, which answers most general
questions and therefore ends the failover chain before any research-specific
provider would run. Folding OpenAlex/arXiv into that chain would make them
effectively unreachable, and on the rare query where they *did* fire they would
answer a question about prices or news with academic papers.

A separate, plainly-named tool lets the model choose. Asking about the
literature calls ``scholarly_search``; asking about the news does not.

Providers (both keyless, no account, no card)
---------------------------------------------
==========  ==========================================  ========================
Provider    Endpoint                                    Covers
==========  ==========================================  ========================
OpenAlex    ``https://api.openalex.org/works``          ~250M works, all fields
arXiv       ``http://export.arxiv.org/api/query``       physics/CS/math preprints
==========  ==========================================  ========================

OpenAlex is tried first (far broader, JSON). arXiv is the failover and also the
better answer for very recent preprints that have no DOI yet.

OpenAlex asks API users to send a contact address in the ``mailto`` parameter
to get into their faster, more reliable "polite pool". Set
``DEEPER_NOTEBOOK_SCHOLARLY_MAILTO`` to opt in; unset simply means the common
pool, never a failure.

Safety
------
All network I/O is async ``httpx``; every error degrades to an empty result so
a chat turn never dies on a failed lookup. No key is read or sent.
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict
from xml.etree import ElementTree

from loguru import logger

from deeper_notebook.environment import resolve_env

__all__ = [
    "SCHOLARLY_SEARCH_TOOL_NAME",
    "scholarly_search_enabled",
    "run_scholarly_search",
    "format_scholarly_results",
    "build_scholarly_search_tool",
    "reset_scholarly_cache",
    "parse_arxiv_atom",
]

SCHOLARLY_SEARCH_TOOL_NAME = "scholarly_search"

_OPENALEX_ENDPOINT = "https://api.openalex.org/works"
_ARXIV_ENDPOINT = "http://export.arxiv.org/api/query"
_PROVIDERS = ("openalex", "arxiv")

_DEFAULT_MAX_RESULTS = 5
_MAX_RESULTS_CEILING = 20
# v0.8.86 — bound the arXiv Atom payload before XML parsing (Bandit B314:
# entity-expansion DoS). A legitimate max_results<=20 feed is tens of KB;
# anything near the cap is not a search result.
_MAX_ARXIV_BYTES = 5_000_000
_TIMEOUT_SEC = 8.0
_TOTAL_BUDGET_SEC = 20.0

_CACHE_TTL_SEC = 900.0
_CACHE_MAX_ENTRIES = 64
_cache: "OrderedDict[tuple[str, int], list[dict]]" = OrderedDict()
_cache_times: dict[tuple[str, int], float] = {}

_ATOM = "{http://www.w3.org/2005/Atom}"


def _env(name: str) -> str:
    if name.startswith("DEEPER_NOTEBOOK_"):
        try:
            return (resolve_env(name) or "").strip()
        except KeyError:  # pragma: no cover - unregistered setting
            return ""
    return (os.environ.get(name) or "").strip()


def scholarly_search_enabled() -> bool:
    """Keyless, so on unless explicitly disabled."""
    raw = _env("DEEPER_NOTEBOOK_SCHOLARLY_SEARCH").lower()
    return raw not in {"0", "false", "no", "off", "disabled"}


def _max_results(requested: int | None) -> int:
    if requested and requested > 0:
        return min(requested, _MAX_RESULTS_CEILING)
    return _DEFAULT_MAX_RESULTS


def _cache_get(key):
    stored = _cache_times.get(key)
    if stored is None or time.monotonic() - stored > _CACHE_TTL_SEC:
        _cache.pop(key, None)
        _cache_times.pop(key, None)
        return None
    _cache.move_to_end(key)
    return list(_cache[key])


def _cache_put(key, results) -> None:
    if not results:
        return
    _cache[key] = list(results)
    _cache_times[key] = time.monotonic()
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX_ENTRIES:
        evicted, _ = _cache.popitem(last=False)
        _cache_times.pop(evicted, None)


def reset_scholarly_cache() -> None:
    _cache.clear()
    _cache_times.clear()


def _reconstruct_abstract(inverted: dict | None) -> str:
    """OpenAlex ships abstracts as an inverted index; rebuild reading order."""
    if not isinstance(inverted, dict) or not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for word, spots in inverted.items():
        if not isinstance(spots, list):
            continue
        for spot in spots:
            if isinstance(spot, int):
                positions.append((spot, str(word)))
    if not positions:
        return ""
    positions.sort()
    return " ".join(word for _, word in positions)


def parse_openalex(payload: object, n: int) -> list[dict]:
    """Map an OpenAlex ``/works`` payload to ``[{title,url,snippet}]``."""
    works = (payload or {}).get("results") if isinstance(payload, dict) else None
    out: list[dict] = []
    for work in (works or [])[:n]:
        if not isinstance(work, dict):
            continue
        title = str(work.get("display_name") or work.get("title") or "").strip()
        if not title:
            continue
        # Prefer the DOI (stable, resolvable) over the OpenAlex record id.
        url = str(work.get("doi") or work.get("id") or "").strip()
        year = work.get("publication_year")
        cited = work.get("cited_by_count")
        abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
        bits = []
        if year:
            bits.append(str(year))
        if isinstance(cited, int):
            bits.append(f"{cited} citations")
        prefix = " · ".join(bits)
        snippet = f"{prefix}. {abstract}".strip(" .") if prefix else abstract
        out.append({"title": title, "url": url, "snippet": snippet[:600]})
    return out


def parse_arxiv_atom(xml_text: str, n: int) -> list[dict]:
    """Map an arXiv Atom feed to ``[{title,url,snippet}]``.

    Uses the stdlib XML parser; a malformed or unexpected feed degrades to an
    empty list rather than raising into the chat turn. The payload is size-
    bounded before parsing, and stdlib etree does not resolve external
    entities, so the remaining B314 concern (expansion DoS) is capped.
    """
    if xml_text and len(xml_text) > _MAX_ARXIV_BYTES:
        logger.warning("arxiv feed exceeded {} bytes; discarded", _MAX_ARXIV_BYTES)
        return []
    try:
        root = ElementTree.fromstring(xml_text or "")  # nosec B314 - bounded, no entity resolution
    except ElementTree.ParseError as exc:
        logger.debug("arxiv atom parse failed: {}", exc)
        return []
    out: list[dict] = []
    for entry in root.findall(f"{_ATOM}entry")[:n]:
        title_el = entry.find(f"{_ATOM}title")
        id_el = entry.find(f"{_ATOM}id")
        summary_el = entry.find(f"{_ATOM}summary")
        published_el = entry.find(f"{_ATOM}published")
        title = " ".join((title_el.text or "").split()) if title_el is not None else ""
        url = (id_el.text or "").strip() if id_el is not None else ""
        if not title or not url:
            continue
        summary = (
            " ".join((summary_el.text or "").split())
            if summary_el is not None
            else ""
        )
        published = (published_el.text or "")[:10] if published_el is not None else ""
        snippet = f"{published}. {summary}".strip(" .") if published else summary
        out.append({"title": title, "url": url, "snippet": snippet[:600]})
    return out


async def _attempt(client, provider: str, query: str, n: int, timeout: float):
    if provider == "openalex":
        params = {"search": query, "per-page": n}
        mailto = _env("DEEPER_NOTEBOOK_SCHOLARLY_MAILTO")
        if mailto:
            # OpenAlex's "polite pool" — faster and more reliable. Optional.
            params["mailto"] = mailto
        resp = await client.get(_OPENALEX_ENDPOINT, params=params, timeout=timeout)
        resp.raise_for_status()
        return parse_openalex(resp.json(), n)

    resp = await client.get(
        _ARXIV_ENDPOINT,
        params={
            "search_query": f"all:{query}",
            "max_results": n,
            "sortBy": "relevance",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return parse_arxiv_atom(resp.text, n)


async def run_scholarly_search(
    query: str, *, max_results: int | None = None
) -> list[dict]:
    """Search the scholarly literature. Never raises into a chat turn."""
    query = (query or "").strip()
    if not query or not scholarly_search_enabled():
        return []

    from deeper_notebook.health.network import get_network_state_with_settings

    net = await get_network_state_with_settings()
    if net.status == "offline":
        logger.info("scholarly_search skipped: device offline")
        return []

    n = _max_results(max_results)
    key = (query.casefold(), n)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    # Reuse web_search's pooled client so both tools share keep-alive
    # connections instead of each paying a TLS handshake per call.
    from deeper_notebook.tools.web_search import _acquire_client

    deadline = time.monotonic() + _TOTAL_BUDGET_SEC
    client, pooled = await _acquire_client()
    try:
        for provider in _PROVIDERS:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                results = await _attempt(
                    client, provider, query, n, min(_TIMEOUT_SEC, remaining)
                )
            except Exception as exc:
                logger.warning("scholarly_search {} failed: {}", provider, exc)
                continue
            if results:
                _cache_put(key, results)
                return results
    finally:
        if not pooled:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - best-effort cleanup
                pass
    return []


def format_scholarly_results(query: str, results: list[dict]) -> str:
    if not results:
        return f"No scholarly results found for {query!r}."
    lines = [f"Scholarly results for {query!r}:"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"[{i}] {r.get('title') or '(untitled)'}\n"
            f"{r.get('url') or ''}\n{r.get('snippet') or ''}".rstrip()
        )
    return "\n\n".join(lines)


def build_scholarly_search_tool(captures: list | None = None):
    """Build the ``StructuredTool`` the chat model binds for literature search."""
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    class ScholarlySearchInput(BaseModel):
        query: str = Field(..., description="Topic, title, author, or research question.")

    async def _invoke(query: str) -> str:
        results = await run_scholarly_search(query)
        text = format_scholarly_results(query, results)
        if captures is not None:
            captures.append(
                {
                    "index": len(captures) + 1,
                    "name": SCHOLARLY_SEARCH_TOOL_NAME,
                    "args": {"query": query},
                    "text": text[:4000],
                    "blocks": [],
                }
            )
        return text

    return StructuredTool.from_function(
        coroutine=_invoke,
        name=SCHOLARLY_SEARCH_TOOL_NAME,
        description=(
            "Search academic and scientific literature (OpenAlex, then arXiv) "
            "for papers, studies, preprints, and citations. Use this for "
            "research questions, prior work, methods, or 'what does the "
            "literature say' — NOT for news, prices, or general web lookups "
            "(use web_search for those). Returns titles, DOI/arXiv links, "
            "publication years, citation counts, and abstracts."
        ),
        args_schema=ScholarlySearchInput,
    )
