# Free MCP servers for internet search

*Open Notebook Plus v0.8.15+*

The v0.8.0 Phase 2 MCP integration lets your local LLM call any MCP
server registered in **Settings → MCP Servers**. This page lists
three **free** MCP servers that give your model live internet
access — web search, URL fetching, deep research — without paying
for OpenAI or Anthropic.

All three run **locally** on your machine. Your queries never go
through a third-party LLM. The MCP server contacts the search
provider directly; the local LLM consumes the result.

> **Prerequisite check.** Your selected chat model must support
> tool-calling. See
> [Local-model tool-calling compatibility](../4-AI-PROVIDERS/local-models-tool-calling.md).
> If you're running Gemma-2 or Yi-1.5, MCP will silently no-op — pick
> a Hermes-3, Qwen2.5, or Llama-3.2 GGUF instead.

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
default. To use it from Open Notebook Plus (which speaks streamable
HTTP), wrap it with the `mcp-proxy` adapter:

```bash
BRAVE_API_KEY=<your-key-here> npx -y @modelcontextprotocol/server-brave-search \
  | npx -y @modelcontextprotocol/server-proxy --port 8765 --mode http
```

Or run the streamable-HTTP build directly if a community fork is
available — check the
[modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
README for the latest official transport.

### Step 4 — Register in Open Notebook Plus

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

## Why no zero-key search server here?

Search-engine APIs without a key (scraping Google, DuckDuckGo HTML,
etc.) break frequently because the underlying engines block
unauthenticated traffic. We've intentionally left them off this
list — operators kept reporting "the chat says Tool failed" because
the upstream scraper rate-limited them. Brave's free 2000/month
tier solves this without adding cost.

If you genuinely need zero-signup, run **Option 2 (Fetch) alone**
and let the model ask the user for URLs to read. The chat works;
it just can't search.

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
