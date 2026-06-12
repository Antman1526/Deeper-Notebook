# Open Notebook Plus v0.4 — Memory layer design spec

**Date:** 2026-05-11
**Author:** Anthony Henry (with Claude Opus 4.7)
**Repo:** https://github.com/Antman1526/open-notebook-Plus
**Branch target:** `desktop-app` (or `v0.4-design` worktree)
**Status:** Draft — pending user review
**Related:** [MEMORY.md](../../../MEMORY.md), [v0.3 design](2026-05-11-open-notebook-plus-v0.3-design.md)

## Goals (v0.4)

Turn Open Notebook Plus from "themed wrapper with voice features" into a **truly persistent local AI knowledge layer** by adding cross-session memory. The killer differentiator vs. NotebookLM is that we *remember* — across chats, across notebooks, across days — what you've taught the app and what you were doing.

Four surface additions, all fully offline:

1. **Episodic memory** (Layer 3) — Hermes 3 memory writer agent extracts facts + episode summaries from chats into SurrealDB. Retrieved at the top of each subsequent chat as system-prompt grounding.
2. **Procedural memory** (Layer 4) — User preferences ("bullet points, not paragraphs") and workflow habits learned over time. Same writer infrastructure; just a different `kind` of record.
3. **Ambient memory bridge** (Layer 0) — Optional OpenChronicle integration via MCP. If the daemon's installed at `127.0.0.1:8742/mcp`, ambient context (recent screen activity, viewed files/URLs) is surfaced into the chat system prompt. Resolves ambiguous references like "explain this" / "the bug we discussed."
4. **Memory dashboard** — Separate PyWebView window (mirrors model-manager) showing preferences/facts/episodes with per-record delete + ambient-memory pause toggle.

## Non-goals

- **No mem0 fork/replacement.** We use `mem0ai/mem0` as-is via its custom-store interface.
- **No "smart" retrieval ranking.** v0.4 uses similarity + recency-decay only. Learned ranking is post-v0.5.
- **No memory export/wipe UI.** Deferred to v0.4.1 (data is in SurrealDB; users can wipe manually if needed).
- **No edit-existing-record UI.** Only delete in v0.4 — editing comes in v0.4.1.
- **No upstream React component forks.** Memory dashboard is a separate PyWebView window; Settings page link is injected via the existing JS-injection pipe.
- **No bundling of OpenChronicle.** Detected via MCP ping; install is the user's choice through Open Notebook Plus's onboarding nudge.
- **No accessibility-permission UX from our side.** OpenChronicle handles that during its own install.
- **No multi-device memory sync.** Deferred to v0.5 (Tailscale/Syncthing).

## Architecture

```
+--------------------------------------------------------------+
|  Open Notebook Plus.app (v0.4)                               |
|                                                              |
|  PyWebView windows                                           |
|   ├─ wizard           (NEW screen 5.5: OpenChronicle nudge) |
|   ├─ main window     (existing)                             |
|   ├─ model-manager   (existing)                             |
|   └─ memory dashboard (NEW — opens from tray + injected     |
|       Settings link)                                        |
|                                                              |
|  Supervisor children (10 total — was 8 in v0.3)             |
|   ├── SurrealDB                  (existing)                 |
|   ├── FastAPI                    (existing)                 |
|   ├── Worker (surreal-commands)  (existing — registers     |
|   │   two NEW handlers: memory_extract_turn,                |
|   │   memory_summarize_session)                             |
|   ├── Next.js                    (existing)                 |
|   ├── llama.cpp (chat)           (existing)                 |
|   ├── llama.cpp (embed)          (existing)                 |
|   ├── Whisper STT shim           (existing)                 |
|   ├── Piper TTS shim             (existing)                 |
|   ├── NEW: Memory retriever shim (FastAPI, /api/memory/*)   |
|   └── NEW: OpenChronicle bridge  (only spawned if detected) |
|                                                              |
|  ProgressBus extended: memory.* + openchronicle.* events    |
+--------------------------------------------------------------+

Data layout:
  ~/.open-notebook-plus/
    ├── surreal_data/  (existing — 3 new tables added by migration)
    │   ├── memory_fact         NEW (atomic facts)
    │   ├── memory_preference   NEW (procedural)
    │   └── memory_episode      NEW (per-chat-session summaries)
    └── logs/
        └── memory.log          NEW
```

## Feature 1 — Episodic & procedural memory via mem0

### 1.1 — SurrealDB adapter for mem0

New module `desktop/memory/surreal_store.py` — implements mem0's custom-vector-store interface against SurrealDB:

```python
class SurrealMemoryStore:
    def insert(self, vectors: list[list[float]], payloads: list[dict],
               ids: list[str]) -> None
    def search(self, query_vector: list[float], filters: dict | None,
               limit: int = 5) -> list[MemoryHit]
    def delete(self, vector_id: str) -> None
    def update(self, vector_id: str, payload: dict, vector=None) -> None
    def get(self, vector_id: str) -> MemoryHit | None
```

The three tables (`memory_fact`, `memory_preference`, `memory_episode`) share schema — `id`, `kind`, `text`, `embedding` (vector), `metadata` (object), `created_at`, `confidence`, `scope` — and the adapter routes to the right one via `metadata.kind`.

### 1.2 — mem0 client configuration

New module `desktop/memory/client.py`:

```python
def build_memory_client(cfg, embed_url, llm_url) -> Memory:
    return Memory.from_config({
        "vector_store": {"provider": "custom",
                         "config": {"client": SurrealMemoryStore(...)}},
        "embedder": {"provider": "openai",
                     "config": {"base_url": embed_url,
                                "model": "nomic-embed-text-v1.5"}},
        "llm": {"provider": "openai",
                "config": {"base_url": llm_url,
                           "model": "Hermes-3-Llama-3.1-8B-Q4_K_M"}},
    })
```

**No new model servers.** mem0's internal classification/dedup calls go to the chat llama.cpp server already running for the user's chat model; embeddings go to the existing nomic-embed server. Both are OpenAI-compatible.

### 1.3 — Bootstrap addition

`mem0ai==<latest>` (verify on PyPI at implementation time) appended to `desktop/requirements.lock`. Adds ~50 MB to the venv install on first launch via the existing bootstrap.

## Feature 2 — The hybrid writer (per-turn + per-session)

### 2.1 — Per-turn extractor

After each assistant response renders, the chat workflow dispatches a `surreal-commands` command `open_notebook.memory_extract_turn` with `{chat_session_id, user_text, assistant_text}`. The worker (already a supervised child) runs the extractor:

```
SYSTEM: You are a memory extractor. From the conversation turn below, identify
EXPLICIT facts about the user or their workflow that should be remembered for
future conversations. Only extract what was explicitly stated.

Tools available:
  remember_preference(text, scope: "user"|"notebook", confidence: float)
  remember_fact(text, scope, confidence)

If the turn contains no explicit facts/preferences, emit no tool calls.

USER TURN: <user_text>
ASSISTANT TURN: <assistant_text>
```

Hermes 3's structured-tool-call output is parsed and each `remember_*` call becomes a `memory.add(...)` invocation through mem0. mem0 handles dedup, so "I prefer bullet points" doesn't write twice for slightly different phrasings.

**Latency cost: 1–3 s per turn on Mac arm64 with Hermes 3 8B Q4_K_M.** Runs as a background task; the user's chat turn is unaffected.

### 2.2 — Per-session summarizer

A session "ends" when:
- The user starts a new chat (previous session's last message is > 5 min old), OR
- The app quits, OR
- 30 minutes elapse with no activity in the session.

When any of those triggers, dispatch `open_notebook.memory_summarize_session` with the full transcript. The handler runs Hermes 3 against the transcript and emits a single `remember_episode` tool call:

```
remember_episode(
  summary="User explored RAG; we discussed self-RAG vs ARGUS; user decided
           to try self-RAG in their dissertation.",
  topics=["retrieval-augmented generation", "self-RAG", "dissertation"],
  outcome="next_step_identified",
  source_chat_id="chat_session:abc"
)
```

One episode record per session.

### 2.3 — Implementation files

```
desktop/memory/
├── __init__.py
├── surreal_store.py     # mem0 adapter
├── client.py            # build_memory_client()
├── writer.py            # extract_turn() + summarize_session() + tool parsers
├── prompts.py           # extractor + summarizer system prompts
└── tests/
    ├── test_writer_extract_turn.py
    ├── test_writer_summarize_session.py
    └── test_surreal_store.py
```

`surreal-commands` registrations live alongside the existing upstream `commands/` directory:

```
commands/
└── memory_commands.py   # NEW (in upstream/commands but kept under desktop's wing)
```

We add this file via auto-creation at startup (similar to how we drop a default Episode Profile in v0.3) rather than modifying upstream's `commands/` tree. The launcher's `_phase_register_memory_commands(ctx)` writes `commands/memory_commands.py` to the bundled-upstream directory at first launch, hooked into `surreal-commands` discovery.

## Feature 3 — Memory retriever

### 3.1 — The shim

New shim `upstream/desktop_shims/memory_shim.py`. Runs as a supervised FastAPI child (same pattern as Whisper/Piper):

```
GET  /health
GET  /api/memory/relevant?topic=<text>&k=5
        → top-K records ranked by similarity + recency-decay
        → returns mix of facts, preferences, episodes
GET  /api/memory/preferences        → list (for dashboard)
GET  /api/memory/facts              → list
GET  /api/memory/episodes           → list
GET  /api/memory/search?q=<text>    → semantic search across all
DELETE /api/memory/{kind}/{id}      → forget one record
GET  /api/memory/ambient/status     → bridge state
POST /api/memory/ambient/pause      → pause bridge for this session
GET  /api/theme                     → theme JSON for the dashboard
```

The shim instantiates `build_memory_client(...)` once at startup and reuses it across requests.

### 3.2 — How retrieval injects into chat

The retriever shim exposes `/api/memory/relevant`. The upstream chat workflow needs to call it at the top of each turn. Two integration paths:

- **(A) Auto-register as a Memory Credential** — POST a `Memory (local)` credential to upstream's credentials API. If upstream's chat workflow has a memory-provider abstraction, we plug into it. (Likely the case — `langchain` has memory primitives upstream already imports.)
- **(B) Tiny patch to `open_notebook/graphs/chat.py`** — if (A) doesn't work, add a `before-model` hook that fetches `/api/memory/relevant` and injects the top-K into the system prompt. ~15 lines, one upstream file.

**Decision at implementation time, not now.** The plan task explicitly tries (A) first and documents the (B) fallback so the implementer knows the path.

### 3.3 — System prompt injection format

```
SYSTEM: <existing upstream system prompt>

What we remember about this user:
- (preference, 0.92) Prefers bullet points over paragraphs.
- (fact, 0.85) Working on a dissertation about retrieval-augmented generation.

Recent episodes:
- 3 days ago: User explored self-RAG vs. ARGUS; decided to try self-RAG.

Recent screen activity (last 10 minutes, via OpenChronicle):
- Viewed paper "Self-RAG: Learning to Retrieve, Generate, and Critique..." in Safari
- Edited file ~/dissertation/chapter3.md in VS Code

USER: <user_message>
```

The "Recent screen activity" block only appears if OpenChronicle bridge is healthy.

## Feature 4 — OpenChronicle Layer 0 bridge

### 4.1 — Detection at startup

New phase in `desktop/app.py`:

```python
def _phase_detect_openchronicle(ctx):
    import httpx
    try:
        r = httpx.get("http://127.0.0.1:8742/mcp", timeout=0.5)
        ctx.openchronicle_available = r.status_code < 500
    except Exception:
        ctx.openchronicle_available = False
```

Slots between `_phase_select_provider` and `_phase_start_supervisor`. Result flows forward via `ctx`.

### 4.2 — The bridge shim

New shim `upstream/desktop_shims/openchronicle_shim.py`. MCP client talking to OpenChronicle's daemon, exposed as a small HTTP API:

```
GET  /health
GET  /context/recent?minutes=10              → list of recent events
GET  /context/search?topic=<text>&limit=5    → topic-matched events
```

Uses the `mcp` Python package (MIT). Auto-reconnects with backoff if the MCP connection drops.

Spawned by Supervisor's `_spawn_openchronicle_bridge(port)` only if `ctx.openchronicle_available` is True. Otherwise silently skipped.

### 4.3 — Retriever integration

The memory retriever (Feature 3) hits the OpenChronicle bridge's `/context/search` after its own mem0 lookup, and inlines results into the system prompt as "Recent screen activity".

### 4.4 — Privacy controls

- **Default off without OpenChronicle.** No installation → no bridge → no ambient capture data ever in our process.
- **Session pause** via Memory dashboard → POST `/api/memory/ambient/pause`. Survives until app restart OR user re-toggles.
- **Per-notebook ignore** via the dashboard — a checkbox on each notebook saying "ignore ambient context for this notebook" (useful for private/sensitive work).
- **No silent persistence of ambient items** — OpenChronicle events flow through into the system prompt at retrieval time but are NEVER copied into our `memory_*` tables. Ambient context lives only in OpenChronicle's own SQLite.

## Feature 5 — Memory dashboard

A separate PyWebView window using the existing `aiohttp_window.start_aiohttp_server_thread` helper from the v0.3 refactor.

### 5.1 — Window structure

```
+---------------------------------------------------------------+
|  Open Notebook Plus — Memory                                  |
|                                                               |
|  Notebook memory (what you've taught Open Notebook Plus)     |
|  ─ Preferences (N)                                           |
|     • [list with confidence + timestamp + delete-on-hover]   |
|  ─ Facts about you (N)            [show all]                 |
|  ─ Episodes (N)                   [show all] [search …]      |
|                                                               |
|  Ambient context (OpenChronicle)                ⏸ [pause]    |
|  ─ Last sync: 2 minutes ago                                  |
|  ─ Events captured today: 1,247                              |
|  ─ [Open OpenChronicle settings →]                           |
|                                                               |
|  [Forget this record] on hover, per row                      |
+---------------------------------------------------------------+
```

### 5.2 — Implementation

```
desktop/memory_dashboard/
├── __init__.py
├── server.py           # aiohttp; routes API calls through to memory_shim
└── static/
    ├── index.html
    ├── style.css       # theme-aware via var(--*)
    └── dashboard.js
```

Uses the shared `aiohttp_window.start_aiohttp_server_thread` — adding this window is ~80 LOC of UI + ~50 LOC of server.

### 5.3 — Tray + Settings link injection

- Tray menu (`desktop/tray.py`) gains "Memory…" entry between "Manage Models…" and "Quit".
- JS injection (`desktop/first_run/static/voice_injection.js` or a sibling file `memory_injection.js`) adds a "Memory" card to upstream's Settings page linking to the dashboard URL. Brittle to upstream DOM changes — documented in `CONTRIBUTING.md`.

## Feature 6 — Wizard screen 5.5 (OpenChronicle onboarding)

### 6.1 — New screen

Insert in `desktop/first_run/static/index.html` between `theme` and `done`:

```html
<section data-screen="ambient-memory" hidden>
  <div class="icon-row"><svg>…brain glyph…</svg></div>
  <h2>✨ Enhance with ambient memory? <span class="hint">(optional)</span></h2>
  <p>Open Notebook Plus can remember what you were working on…</p>
  <ul class="examples">
    <li>"What was the bug in that file?"</li>
    <li>"Summarize the article I just read."</li>
    <li>"Continue what I was doing."</li>
  </ul>
  <p>
    This uses <strong>OpenChronicle</strong>
    (<a href="…">MIT</a>), a separate free app that reads your screen via macOS
    accessibility to build local-only memory. Nothing leaves your machine.
  </p>
  <div class="button-row">
    <button data-back="theme">Back</button>
    <button data-next="done" data-onclick="skip_openchronicle">Skip — set up later</button>
    <button class="primary" data-next="done"
            data-onclick="open_openchronicle_install">Open install page</button>
  </div>
</section>
```

### 6.2 — Config field

Add to `desktop/config.py`:

```python
openchronicle_choice: str = "skip"   # "skip" | "prompt" | "configured"
```

- `"skip"` — user clicked Skip. Never re-prompt.
- `"prompt"` — user clicked Open install page. Re-prompt via main-UI toast if still not detected on subsequent launches.
- `"configured"` — set automatically by `_phase_detect_openchronicle` once detection succeeds. No further nags.

### 6.3 — Main-UI reminder toast

If `openchronicle_choice == "prompt"` AND detection fails, set `window.ONP_REMIND_OPENCHRONICLE = true` in the injected JS bundle. The toast helper (already exists from v0.3) renders:

```
OpenChronicle not detected. Install for ambient memory →   [ ✕ ]
```

The X has a "Don't ask again" tooltip; clicking POSTs to `/api/config/dismiss_openchronicle_reminder` which sets `openchronicle_choice="skip"` and persists.

## Tasks summary (informational; full plan via writing-plans)

13 tasks. Each maps to one or more commits in the writing-plans output:

| # | Task | New files | Modified files |
|---|------|-----------|---------------|
| 1 | Add `mem0ai` + `mcp` Python pkgs to `requirements.lock` | — | `desktop/requirements.lock` |
| 2 | SurrealDB adapter for mem0 | `desktop/memory/surreal_store.py` | — |
| 3 | mem0 client factory | `desktop/memory/client.py` | — |
| 4 | Memory writer (extractor + summarizer + prompts) | `desktop/memory/writer.py`, `prompts.py` | — |
| 5 | `commands/memory_commands.py` auto-write on first launch | — | `desktop/app.py` (new phase) |
| 6 | Memory retriever shim | `upstream/desktop_shims/memory_shim.py` | — |
| 7 | Supervisor spawns retriever shim | — | `desktop/launcher.py` |
| 8 | Auto-register Memory credential + integration path | — | `desktop/auto_register/voice.py` (or new memory.py) |
| 9 | OpenChronicle bridge shim | `upstream/desktop_shims/openchronicle_shim.py` | — |
| 10 | Supervisor + app detect + spawn OpenChronicle bridge | — | `desktop/launcher.py`, `desktop/app.py` |
| 11 | Memory dashboard window | `desktop/memory_dashboard/{server,static}.*` | — |
| 12 | Tray "Memory…" entry + Settings page link injection | `desktop/first_run/static/memory_injection.js` | `desktop/tray.py`, `desktop/window.py` |
| 13 | Wizard screen 5.5 + config field + reminder toast | — | `desktop/first_run/static/{index.html,wizard.js,voice_injection.js}`, `desktop/config.py` |
| 14 | SurrealDB migration for 3 new tables | `migrations_v04/X_memory.surql` | (auto-applied via upstream's migration system) |
| 15 | Manual E2E smoke (post-build) | — | — |

Test count grows from 88 → ~115 with: SurrealStore adapter tests, writer extractor + summarizer golden-output tests, retriever shim tests, OpenChronicle bridge tests (mocked MCP), dashboard server tests, wizard screen tests.

## Definition of done

- [ ] A fresh chat asks "what do you remember about me?" — assistant lists facts/preferences from prior sessions. No cloud calls.
- [ ] Across two chat sessions: user mentions a preference ("I like bullet points") in session 1; in session 2 (after navigating away + back) the assistant respects it without being re-told.
- [ ] The Memory dashboard window opens from the tray and lists at least 3 records after a few chat sessions of use.
- [ ] OpenChronicle disabled path: no daemon installed → app boots fine, no errors, no "OpenChronicle missing" log noise (just a benign `openchronicle.detect available=False` event).
- [ ] OpenChronicle enabled path: daemon installed + reachable → "Recent screen activity" block appears in the system prompt (verifiable by inspecting `api.log` for the formatted prompt).
- [ ] Wizard screen 5.5 appears in a fresh install; choosing "Skip" persists; choosing "Open install page" launches the browser and persists `"prompt"`; subsequent launch shows the reminder toast.
- [ ] On clean install: ~/.open-notebook-plus/logs/memory.log exists after first chat and shows writer + retriever activity.
- [ ] All 115+ tests pass on the CI Mac arm64 + Windows x64 runners.

## Open questions resolved during implementation

These are flagged as "decide-during-implementation" so the plan can document the chosen path:

1. **mem0 + SurrealDB schema fields** — final field names align with mem0's expected adapter contract (which we'll learn by reading mem0's reference adapter for, e.g., Qdrant).
2. **Retriever ↔ chat integration** — try the credential path (3.2a) first; fall back to a 15-line patch in `open_notebook/graphs/chat.py` if needed. The fallback is documented in the plan; we re-flag if the upstream code path is unclear.
3. **Episode session-end detection** — implementer chooses where to hook (worker idle timer vs. chat workflow finish handler). Either is acceptable.
4. **OpenChronicle MCP wire format** — implementer reads OpenChronicle's docs at https://github.com/Einsia/OpenChronicle to align the bridge shim with the actual MCP tool names exposed (the design uses `recent_activity` + `search` as placeholders).

## Future scope (placeholders, not specs)

- **v0.4.1** — Memory export (JSON), memory edit (not just delete), "forget everything" big-red-button, multi-language support for the writer.
- **v0.5** — Visual understanding (image upload, local VLM Qwen2-VL, mind-map / knowledge-graph view, PDF OCR). Originally on the v0.4 list; deferred so memory ships first.
- **v0.6** — Ecosystem hub: MCP server mode so external tools query our memory, browser extension for one-click sources, multi-device sync via Tailscale/Syncthing.
- **v0.7** — Productization: auto-update, codesigning, branded icon.
