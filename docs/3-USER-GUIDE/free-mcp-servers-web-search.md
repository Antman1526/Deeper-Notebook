# Free MCP servers for internet search

*Deeper Notebook v0.8.15+*

The v0.8.0 Phase 2 MCP integration lets your local LLM call any MCP
server registered in **Settings → MCP Servers**. This page lists
**free** MCP servers that give your model live internet access — web
search, URL fetching, deep research — without paying for OpenAI or
Anthropic.

All of them run **locally** on your machine. Your queries never go
through a third-party LLM. The MCP server contacts the search
provider directly; the local LLM consumes the result.

> **Prerequisite check.** Your selected chat model must support
> tool-calling. See
> [Local-model tool-calling compatibility](../4-AI-PROVIDERS/local-models-tool-calling.md).
> If you're running Gemma-2 or Yi-1.5, MCP will silently no-op — pick
> a Hermes-3, Qwen2.5, or Llama-3.2 GGUF instead.

---

## 🆓 Option 0: SearXNG (truly free + unlimited, no API key)

**Self-hosted meta-search aggregator.** SearXNG queries dozens of
upstream engines (Google, Bing, DuckDuckGo, Brave, Wikipedia,
GitHub, …) and merges the results — without API keys. Run a local
SearXNG instance once, point an MCP wrapper at it, and you have
unlimited web search for the lifetime of your machine.

- **Cost:** $0 forever. No signup, no key, no per-query cap.
- **Setup time:** ~10 minutes (Docker + npm).
- **Strengths:** Truly unlimited. Searches Google, Bing, DDG,
  Brave, Wikipedia, ArXiv, GitHub, Stack Overflow, etc. in one
  query. Privacy-respecting (SearXNG doesn't log or track you).
- **Weaknesses:** Requires Docker (or a manual binary install).
  Upstream engines occasionally block aggregators — if Google
  rate-limits your IP for a minute, search briefly degrades to
  DDG/Brave only.

### Step 1 — Run SearXNG locally (Docker, ~2 min)

```bash
# Use the official searxng-docker image; one container, no compose needed.
docker run --rm -d \
  -p 8888:8080 \
  --name onp-searxng \
  -e BASE_URL=http://localhost:8888 \
  -e INSTANCE_NAME=onp-searxng \
  searxng/searxng:latest

# Verify it's up — should return JSON results
curl -s "http://127.0.0.1:8888/search?q=test&format=json" | head -c 200
```

If you prefer not to use Docker, the
[SearXNG install guide](https://docs.searxng.org/admin/installation-docker.html)
covers Python source install + uwsgi/nginx for permanent setups.

### Step 2 — Install an MCP → SearXNG wrapper

The MCP ecosystem moves fast — search [npm](https://www.npmjs.com/search?q=mcp+searxng)
and [PyPI](https://pypi.org/search/?q=mcp+searxng) for current
SearXNG MCP wrappers. As of this writing, popular options include
community projects under the `mcp-searxng` / `searxng-mcp` naming
patterns. The recipe is:

1. Pick a wrapper whose README mentions **streamable HTTP transport**
   (what ONP's MCPClient speaks). If a wrapper is **stdio-only**,
   bridge it with a transport adapter (search `mcp proxy` or
   `mcp streamablehttp` on the same registries).
2. Install + run it with `SEARXNG_URL=http://127.0.0.1:8888` in the
   environment so it talks to your local SearXNG.
3. Bind it to a fixed local port (e.g. `8770`) for the next step.

> **Verifying the wrapper actually works**: before registering in
> ONP, `curl http://127.0.0.1:8770/mcp` or open it in a browser —
> a working MCP server returns a JSON-RPC handshake / SSE stream
> header. If it returns 404 or connection-refused, the wrapper
> isn't running on the port you think.

### Step 3 — Register in Deeper Notebook

1. Sidebar → **Settings → MCP Servers**
2. **Add server** → Name `SearXNG`, URL `http://127.0.0.1:8770/mcp`
3. Click **Test** — should show "Connected — 1+ tool(s) available".

Per v0.8.10 the chat model will see whatever tools the SearXNG
wrapper exposes (typically `mcp_search` or `mcp_searxng_search`)
with the real Pydantic schema from v0.8.11. Per v0.8.12 the
discovery result is cached 30s. Per v0.8.13 multi-block responses
(text + image thumbnails from the search results) are preserved
in the citation pill popover.

### Why this isn't the default

SearXNG requires Docker (or a manual install), which is a barrier
for non-CLI operators. The Brave/Tavily options below are
zero-Docker but bounded by free-tier query caps. **Pick SearXNG if
you want truly unlimited; pick Brave if you want zero Docker.**

---

## 📚 Option 0b: Wikipedia (no key, no Docker, encyclopedic search)

For fact-lookup questions ("What's the capital of Bhutan?", "Who
discovered penicillin?") Wikipedia alone is often enough — and
several MCP wrappers exist with **zero ongoing setup**.

Search [npm](https://www.npmjs.com/search?q=mcp+wikipedia) and
[PyPI](https://pypi.org/search/?q=mcp+wikipedia) for current
Wikipedia MCP wrappers (the ecosystem changes frequently; package
names like `mcp-wikipedia`, `wikipedia-mcp`, or
`mcp-server-wikipedia` are common). Pick one whose README mentions
**streamable HTTP transport** and run it on a fixed port:

```bash
# Example shape (replace PACKAGE_NAME with whatever the current
# wrapper is called):
npx -y PACKAGE_NAME --port 8771 --mode http
# Then verify:
curl -sS http://127.0.0.1:8771/mcp
```

Register at `http://127.0.0.1:8771/mcp` in Settings → MCP Servers.
The model will see one or more `mcp_<tool>` entries depending on
the wrapper (typical tools: `search`, `get_article`, `summarize`).

- **Cost:** $0 forever, no key.
- **Strengths:** No Docker. Encyclopedic coverage. Wikipedia's API
  doesn't rate-limit personal use.
- **Weaknesses:** Wikipedia only — no current-events news, no
  technical docs outside Wikipedia, no source-code search.

**Pair Wikipedia + Fetch (Option 2 below).** Wikipedia gives you
broad reference, Fetch lets the user paste any URL into chat for
the model to read. Combined they cover ~80% of "answer my question
from the web" use cases without any signup.

---

## 🥇 Option 1: Brave Search (recommended)

**Anthropic's official MCP server**, wraps the Brave Search API.

- **Cost:** Free up to **2,000 queries/month**. No credit card
  required for the free tier.
- **Setup time:** ~5 minutes (sign up + paste env var).
- **Strengths:** High-quality search; same data as Brave's own
  search engine; reliable; maintained by Anthropic so won't bit-rot.
- **Weaknesses:** Requires a one-time sign-up for an API key.

### Step 1 — Get a free Brave Search API key

1. Go to <https://api.search.brave.com/app/keys>
2. Sign up (email + password, no credit card on the free tier).
3. Subscribe to the **Free** plan ("AI" or "Web Search Free").
4. Copy your API key from the dashboard.

### Step 2 — Install the MCP server

Two install paths — pick whichever matches your environment:

**npm (Node.js installed):**
```bash
npx -y @modelcontextprotocol/server-brave-search
# Verify it launches and prints "Brave Search MCP server running"
```

**uvx (Python uv installed — comes bundled with ONP):**
```bash
uvx mcp-server-brave-search
```

### Step 3 — Run it with your API key on a fixed port

The official Brave Search server speaks MCP over **stdio** by
default. To use it from Deeper Notebook (which speaks streamable
HTTP), wrap it with the `mcp-proxy` adapter:

```bash
BRAVE_API_KEY=<your-key-here> npx -y @modelcontextprotocol/server-brave-search \
  | npx -y @modelcontextprotocol/server-proxy --port 8765 --mode http
```

Or run the streamable-HTTP build directly if a community fork is
available — check the
[modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
README for the latest official transport.

### Step 4 — Register in Deeper Notebook

1. Sidebar → **Settings → MCP Servers**
2. **Add server** → Name `Brave Search`, URL `http://127.0.0.1:8765/mcp`
3. Click **Test** — should show "Connected — 2 tool(s) available"
   (typically `brave_web_search` and `brave_local_search`).

The chat model will now see `mcp_brave_web_search` and
`mcp_brave_local_search` in its tool list. Ask a current-events
question to verify; the model should emit `[mcp:1]` and the citation
pill will show the query + result text per v0.8.13.

---

## 🥈 Option 2: Fetch (no API key — pairs well with search)

**Anthropic's official MCP server** for fetching arbitrary URLs and
extracting readable content.

- **Cost:** Free, no API key, no signup.
- **Setup time:** ~2 minutes.
- **Strengths:** Zero friction. Lets the model READ a specific URL
  the user mentions; complements a search server perfectly.
- **Weaknesses:** Doesn't *search* — it fetches a known URL.

### Install + run

```bash
uvx mcp-server-fetch --port 8766 --mode http
# Or with npx:
npx -y @modelcontextprotocol/server-fetch --port 8766 --mode http
```

Register in Settings → MCP Servers with URL
`http://127.0.0.1:8766/mcp`. The model will see `mcp_fetch` and use
it whenever the user asks "What does this page say?" or pastes a
link.

### Pair both Brave + Fetch

Use the v0.8.1 Item 5 ▲/▼ priority arrows to put **Brave Search at
the top** (highest priority — chat-graph's `_resolve_chat_tools`
picks the highest-priority enabled server). With both registered
the model can search the web, then fetch the most promising result
for the full text. The system prompt's v0.8.10 wording handles
multiple tools per turn (`[mcp:1]`, `[mcp:2]`, …) automatically.

---

## 🥉 Option 3: Tavily (alternative search; free 1,000/mo)

[Tavily](https://tavily.com) is a search API designed for AI
agents. Lower free tier than Brave but cleaner JSON output that's
more LLM-friendly.

- **Cost:** Free **1,000 queries/month** (about 33/day).
- **Setup time:** ~5 minutes (sign up + paste env var).
- **Strengths:** Output format optimized for LLM consumption (less
  noise, better deduping). Includes a "deep research" mode that
  follows links automatically.
- **Weaknesses:** Lower free tier than Brave. Less robust than Brave
  on niche queries.

### Setup

1. Sign up at <https://tavily.com> for a free API key.
2. Install:
   ```bash
   npx -y tavily-mcp --port 8767 --mode http
   ```
   Set `TAVILY_API_KEY=<your-key>` in your shell first.
3. Register in Settings → MCP Servers with URL
   `http://127.0.0.1:8767/mcp`. The model will see
   `mcp_tavily_search` and (depending on version)
   `mcp_tavily_extract`.

---

## Quick decision matrix

| Need | Best fit |
|------|---------|
| Truly unlimited + no key + willing to run Docker | 🆓 **SearXNG** |
| No key + no Docker + Wikipedia is enough | 📚 **Wikipedia** |
| Best raw web-search quality + happy to sign up once | 🥇 **Brave** |
| Just need to fetch URLs the user pastes | 🥈 **Fetch** |
| Want AI-optimised results + happy to sign up once | 🥉 **Tavily** |

**For most ONP users wanting "free web search now":** start with
**Wikipedia + Fetch** (no setup friction at all). If you need
broader web results, layer **SearXNG** on top. The v0.8.1 Item 5
▲/▼ priority arrows let you keep all three registered and reorder
which the chat-graph picks first.

## Why no scraping-based zero-key search server?

Standalone DuckDuckGo-HTML-scraping or "Google parsing" MCP servers
exist on npm, but they break frequently because the underlying
engines block unauthenticated traffic. Operators kept reporting
"the chat says Tool failed" within a week of registering one.
**SearXNG sidesteps this** by rotating through dozens of engines
under the hood and falling back when individual ones block — that's
the value SearXNG adds over a raw HTML scraper.

---

## Verifying the integration

After registering any MCP server:

1. Pick a tool-call-capable chat model (Settings → Models or
   `OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID` via Settings → Launcher
   Preferences).
2. Open any notebook → chat.
3. Ask: *"What's the top story on Hacker News right now?"*
4. Watch the chat response.

You should see:

- A `[mcp:1]` marker after the model's claim (v0.8.0 Task 13 prompt
  wording). Per v0.8.10 the chat graph now actually executes the
  call — pre-v0.8.9 the marker was hallucinated.
- An expandable citation pill rendered by v0.8.1 Item 3 +
  v0.8.13 enhancements. Click the pill — the popover shows the
  real tool name, args (the search query), and a truncated excerpt
  of what the server returned. Per v0.8.13 image/PDF blocks will
  also surface here once a frontend renderer ships.
- In `~/.open-notebook-plus/logs/launcher.log`, a `phase1.health`
  line per launch (v0.8.0 Phase 1) and a `v0.8.0 chat router →`
  line per smart-routed turn (v0.8.5) — both confirm the model
  the router picked.

If the pill shows the placeholder text from v0.8.10 ("Result not
available for this older session"), the chat turn happened before
your last cache cycle; send a new message.

If the model doesn't call the tool at all even after registering,
re-check the
[Local-model tool-calling compatibility matrix](../4-AI-PROVIDERS/local-models-tool-calling.md)
— your selected model probably isn't tool-call-trained.

---

## See also

- [Integrating gbrain as an MCP source](integrating-gbrain-mcp.md) — for
  team-shared institutional knowledge instead of public web.
- [Citations](citations.md) — how `[mcp:N]` markers render.
- The [official MCP servers list](https://github.com/modelcontextprotocol/servers)
  for many more options (filesystem, GitHub, GitLab, Slack, Postgres,
  …). Same Settings → MCP Servers wiring for all of them.
