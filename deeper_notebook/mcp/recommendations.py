"""v0.8.41 — Curated MCP server recommendations.

Read-only table of MCP servers we've validated work well with our chat
graph's v0.8.16 tool loop. Selection inspired by the XDA Developers
article on local-LLM stacks; we kept only the picks that genuinely
extend our research-assistant use case (skipped Mem0 — we already
integrate it server-side via v0.7.68/70 memory writer; skipped Qdrant
— SurrealDB native vector search; skipped Context7 — our users
research, they don't code).

Unlike the v0.8.39b GGUF downloader, we CAN'T install MCP servers
for the user — they live in Docker containers, npm packages, or
standalone Python processes the user has to start themselves. Our
contribution is:

  1. A curated list of "known-good" servers with metadata + install
     instructions (link to upstream docs).
  2. A "default URL" for the localhost binding each server uses out
     of the box, so the "Connect" button can pre-fill the new-server
     form.
  3. Tag-based categorization so the frontend can group recommendations
     by capability (web search / browser / scraping).

The user installs the server externally, then clicks Connect → we
POST to the existing `POST /api/mcp` create endpoint with the
pre-filled name + URL. They see the test-connection feedback inline
the same way manual entries get it.

Pattern matches `deeper_notebook/local_models/downloader.py:RECOMMENDATIONS`
intentionally — both are curated lists of "things you can plug into
Deeper Notebook that we've made sure work."
"""

from __future__ import annotations

# Each entry is a recommendation card the frontend renders. Fields:
#   id            — stable React key, kebab-case slug
#   label         — display name (one or two words)
#   description   — one-sentence pitch
#   default_url   — localhost URL the upstream binds to out-of-box
#   install_url   — link to upstream install/quick-start docs
#   tags          — categorization (search / browser / scraping / docs)
#   replaces      — optional paid SaaS this open-source alternative
#                   replaces (lifted from the XDA article framing)
#
# Order in the list = order in the UI. SearXNG first because it's the
# most-broadly-useful pick — search is the highest-leverage tool a
# research assistant can have.
RECOMMENDATIONS: list[dict] = [
    {
        "id": "searxng",
        "label": "SearXNG (web search)",
        "description": (
            "Local meta-search engine that aggregates Google / Bing / "
            "DuckDuckGo / 70+ other sources without API keys. The chat "
            "graph's web-search tool will route through this — no "
            "outbound API spend."
        ),
        "default_url": "http://127.0.0.1:8080",
        "install_url": "https://github.com/searxng/searxng",
        "tags": ["search", "recommended"],
        "replaces": None,
    },
    {
        "id": "crawl4ai",
        "label": "Crawl4AI (web → markdown)",
        "description": (
            "Clean HTML-to-markdown extraction for the chat graph's "
            "fetch-url tool. Python-based, runs locally; handles "
            "JavaScript-rendered pages out of the box."
        ),
        "default_url": "http://127.0.0.1:11235",
        "install_url": "https://github.com/unclecode/crawl4ai",
        "tags": ["scraping"],
        "replaces": "Firecrawl ($16/mo)",
    },
    {
        "id": "playwright",
        "label": "Playwright MCP (browser automation)",
        "description": (
            "Microsoft-maintained MCP server exposing a browser via "
            "accessibility-tree introspection. Useful for tasks the "
            "chat needs to perform inside a real page (form fill, "
            "DOM walk) — niche but high-leverage when it applies."
        ),
        "default_url": "http://127.0.0.1:8931",
        "install_url": "https://github.com/microsoft/playwright-mcp",
        "tags": ["browser"],
        "replaces": None,
    },
]
