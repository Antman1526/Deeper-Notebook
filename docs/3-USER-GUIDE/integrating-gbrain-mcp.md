# Integrating gbrain as an MCP source

*Deeper Notebook v0.8.2+*

[gbrain](https://github.com/garrytan/gbrain) is an open-source "memory
system" — a TypeScript/Bun service that indexes a folder of markdown
files in git, runs hybrid retrieval (vector + BM25 + reciprocal rank
fusion) on top of a Postgres / pgvector store, and adds a self-wiring
typed knowledge graph (`attended`, `works_at`, `invested_in`, …) on top.
It exposes itself as an **MCP server** so any MCP client can ask it
questions.

Deeper Notebook v0.8.0 shipped an MCP **client**. Combining the two
gives your local chat model on-demand access to gbrain's hybrid retrieval
without any code change in either project — gbrain stays where it is,
Deeper Notebook calls it as a tool from chat turns.

This guide walks through the three-step setup.

---

## What you get

When gbrain is registered as an MCP source in Deeper Notebook:

- Every chat turn in any notebook can call `mcp_search` / `mcp_fetch`,
  which now route to gbrain.
- The model emits `[mcp:N]` citation markers per the v0.8.0 chat system
  prompt (see [Citations](citations.md)).
- The frontend renders each marker as a pill; clicking the pill shows
  the actual gbrain query + truncated result text — wired through the
  v0.8.1 Item 3 payload pipeline.
- Smart routing (Phase 3) still picks local-vs-cloud per turn based on
  context size and sidecar health. MCP tool calls happen on either
  side; the gbrain result text is part of the LLM context, so an
  oversized gbrain result can flip the next turn to the cloud branch.

Importantly, gbrain runs **outside** Deeper Notebook's process. It
keeps its own Postgres / PGLite database and markdown brain repo. Your
notebook sources, notes, podcasts, and chat history stay in
SurrealDB. The only seam is the HTTP MCP call.

---

## Step 1: Get gbrain running with its MCP server enabled

Follow gbrain's own
[installation guide](https://github.com/garrytan/gbrain). For a
single-user setup the PGLite backend is enough:

```bash
# from gbrain's own repo
bun install
bun run gbrain init
bun run gbrain mcp serve --port 8742
```

The MCP server URL will be `http://127.0.0.1:8742/mcp` (or whichever
port you chose). Verify it responds:

```bash
curl -sS http://127.0.0.1:8742/mcp/health | jq .
# Expect: {"status":"ok","tools":["search","think","find_trajectory",...]}
```

If the URL isn't reachable, fix that first — Deeper Notebook's
registration step assumes the URL is live (it does a test-connect
before saving).

> **Privacy note.** gbrain's MCP server has no auth by default. Bind it
> to `127.0.0.1` only and leave it off your firewall. If you expose
> gbrain across a LAN, put it behind a reverse proxy with auth before
> registering it in Deeper Notebook.

---

## Step 2: Register gbrain in Deeper Notebook → Settings → MCP Servers

1. Launch Deeper Notebook and sign in.
2. Sidebar → **Settings → MCP Servers** (added in v0.8.0 Phase 2 Task
   10).
3. Click **Add server**. Fill in:
   - **Name**: `gbrain` (or whatever you want to see in the popover
     when chat cites it).
   - **URL**: `http://127.0.0.1:8742/mcp` (match the port from Step 1).
4. Click **Add**. The Settings page lists the new row.
5. Click **Test** on the row. You should see a green toast confirming
   "Connected — N tool(s) available". If the toast is red, the most
   common causes are:
   - gbrain isn't running on that port (`curl` it again).
   - Wrong URL path — gbrain's MCP endpoint is `/mcp` not `/`.
   - Deeper Notebook's backend can't reach gbrain because the host
     is `localhost` vs `127.0.0.1` mismatch on a particular network
     stack. Try the other form.

If you run multiple MCP servers, use the **▲ / ▼** buttons (v0.8.1
Item 5) to put gbrain at the top — `_resolve_chat_tools()` binds the
highest-priority enabled server first. Tied priorities fall back to
insertion order, so reordering matters.

---

## Step 3: Ask something that needs gbrain in any notebook chat

Open any notebook → chat panel → ask a question the LLM can't answer
from notebook context alone. Examples that should reach for gbrain:

- *"What did we decide in the Q2 strategy review?"* — gbrain answers
  from your team's brain repo, model cites `[mcp:1]`.
- *"Who attended the December customer call?"* — exercises gbrain's
  knowledge-graph edges.
- *"Summarize what we know about Acme Corp."* — `mcp_search` over the
  brain repo, then synthesis by your local or cloud model.

In the chat response, each `[mcp:N]` marker becomes a clickable pill.
Hover (or click on touch) to see:

- **Tool**: `web_search` (gbrain's search) or `fetch_url` (gbrain's
  document fetcher).
- **Arguments**: the actual query the model sent to gbrain.
- **Result**: the first ~500 chars of what gbrain returned.

If a pill popover shows the "Result not available for this older
session" fallback, it means the chat turn happened before this feature
shipped (v0.8.1 Item 3) or you registered gbrain after the turn ran.
New turns will populate.

---

## When to use gbrain vs Deeper Notebook sources

| Need | Use |
|------|-----|
| Tight feedback loop on one or two documents — annotate, transform, podcast | Deeper Notebook **sources** in that notebook |
| Cross-notebook recall over months of accumulated team knowledge | **gbrain** via MCP |
| "Who knows about X?" / "Find the trajectory of decision Y" / typed graph queries | **gbrain** (uses its `whoknows` / `find_trajectory` skills) |
| Source-grounded chat with explicit `[source:ID]` / `[note:ID]` citations to the document you're staring at | Deeper Notebook **notebook context** |
| Podcasts, transformations, vector search across a single notebook | Deeper Notebook |

The two are intentionally complementary. Don't ingest gbrain's
markdown brain into Deeper Notebook as sources — you'll duplicate
storage and confuse provenance. Keep them separate; let MCP be the
only seam.

---

## Troubleshooting

**The chat never calls `mcp_search` even with gbrain registered.**
Either the system prompt didn't render with the MCP block (check
`prompts/chat/system.jinja` exists and contains "MCP TOOL CITATIONS")
or the chat graph's `_resolve_chat_tools()` returned an empty list
(check the backend log for `phase1.health` warnings; also check that
the row in Settings → MCP Servers is **enabled**).

**Pill popovers are blank.**
This is the v0.8.0 placeholder behavior for chat turns that ran before
v0.8.1 Item 3 landed. Send a new chat turn and check the new pills.
If new pills are also blank, look in the network tab for the
`mcp_tool_calls` NDJSON event on `/api/chat/stream` (or the
`mcp_tool_calls` field on `/api/chat/execute`'s response) — if it's
missing, the capture in `_resolve_chat_tools()` isn't firing.

**Smart routing keeps picking cloud after registering gbrain.**
gbrain's result text bloats the chat context. `pick_provider()` checks
`content_tokens < local_chat_n_ctx - 1000`; if gbrain returns a 4 KB
excerpt, the next turn may overflow your 32k local n_ctx and the
router flips to cloud. Either:
- Raise `OPEN_NOTEBOOK_LOCAL_N_CTX` (default 32768) if your sidecar
  was built with more headroom.
- Or force local with `OPEN_NOTEBOOK_CHAT_PROVIDER=local` per the
  Phase 3 documentation.

**gbrain went down — does my notebook chat still work?**
Yes. `_resolve_chat_tools()` wraps `bind_tools` in `try/except` (v0.8.0
Task 8), so a flaky MCP server doesn't break the LLM invocation —
the chat just proceeds without MCP tools that turn.

---

## See also

- [Citations](citations.md) — how `[mcp:N]` / `[source:ID]` markers
  render as pills.
- [Chat effectively](chat-effectively.md) — building good prompts so
  the model knows when to reach for tools.
- gbrain's own
  [company-brain tutorial](https://github.com/garrytan/gbrain/blob/master/docs/tutorials/company-brain.md)
  for setting up gbrain for a team rather than solo use.
