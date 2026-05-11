# Open Notebook Plus — Memory Architecture

**Last updated:** 2026-05-11
**Status:** Design doc + roadmap. Reflects what ships in v0.3 and what's planned for v0.4.

This document describes how Open Notebook Plus stores, retrieves, and reasons over knowledge across sessions — what we call the app's **memory**. It covers what we inherit from upstream `lfnovo/open-notebook`, what Hermes 3 (the bundled default chat model) contributes, and the open-source libraries we use or plan to use.

The goal: turn Open Notebook Plus into a **truly persistent local AI knowledge layer** — one that remembers your sources, your conversations, your annotations, and the patterns of how you reason — without ever sending data to a cloud.

---

## Why "memory" matters here

NotebookLM is amnesiac. Each chat starts blank. The notebook itself stores sources, but cross-notebook patterns ("things I've read about retrieval-augmented generation across all my work"), agent state ("the research thread I was pursuing last week"), and personal preferences ("when I ask for summaries, use bullet points, not paragraphs") all vanish.

Open Notebook Plus has the database, the local model, and the open-source ecosystem to fix this. v0.3 inherits the upstream's per-notebook memory; v0.4 adds **cross-notebook episodic memory** using the same Hermes 3 / nomic-embed stack that already ships in the .app.

---

## The four memory layers

```
                ┌──────────────────────────────────────┐
                │  Layer 4: Procedural memory          │  v0.4
                │   (HOW you work — habits, prefs)     │
                ├──────────────────────────────────────┤
                │  Layer 3: Episodic memory            │  v0.4
                │   (WHAT happened — past chats,       │
                │    summaries, research threads)      │
                ├──────────────────────────────────────┤
                │  Layer 2: Semantic memory            │  v0.3 (upstream)
                │   (WHAT'S KNOWN — sources, notes,    │
                │    insights, embeddings)             │
                ├──────────────────────────────────────┤
                │  Layer 1: Working memory             │  v0.3 (upstream)
                │   (RIGHT NOW — current chat context, │
                │    LangGraph checkpoints)            │
                └──────────────────────────────────────┘
                  All four run locally on SurrealDB +
                  the user's chosen local LLM.
```

### Layer 1 — Working memory (already shipping)

**What it is:** The current chat's conversation, the active LangGraph workflow state, and the immediate context window of the LLM.

**Implementation (upstream):**
- LangGraph state machines (`open_notebook/graphs/chat.py`, `ask.py`) hold per-turn state.
- `langgraph-checkpoint-sqlite` persists graph state across requests, so an in-progress workflow survives a refresh.
- Files: `~/.open-notebook-plus/venv/lib/.../langgraph_checkpoint_sqlite/` runtime; checkpoints written under `/data/sqlite-db/` inside upstream's data dir.

**What Open Notebook Plus inherits:** All of it, unchanged. The launcher just runs upstream's existing graphs.

### Layer 2 — Semantic memory (already shipping)

**What it is:** Everything you've explicitly added to a notebook — sources (PDFs, web pages, audio transcripts), notes you've written, AI-generated insights — plus the vector embeddings that make all of that semantically searchable.

**Implementation (upstream):**
- SurrealDB tables: `source`, `note`, `source_insight`, `notebook`, with `belongs_to` / `references` relationships.
- Embeddings stored inline on each record via SurrealDB's built-in vector type. The embedding model is configurable; v0.3's default is **nomic-embed-text v1.5** (a 137M-param model, 273 MB GGUF, served by a second local llama.cpp instance).
- The "Ask" workflow (`open_notebook/graphs/ask.py`) does similarity search across embeddings + chunk-rerank + answer synthesis.

**What v0.3 added:**
- Auto-download of `nomic-embed-text-v1.5.f16.gguf` into `~/Desktop/AI_Models/GGUF/` on first launch.
- A second `llama.cpp` server instance with `--embedding true` serving the model.
- Auto-register a credential + model record pointing at the embed server.

### Layer 3 — Episodic memory (v0.4 plan)

**What it is:** Memory of past conversations and how they connected. "When I asked about quantum encryption last month, you mentioned a specific paper — what was the citation?" Today that information sits in a closed `chat_session` record nobody queries.

**Plan for v0.4:**

After each chat session ends, a background task — a **memory writer agent** — runs over the conversation transcript and writes structured memory records to SurrealDB. The agent is Hermes 3 (the bundled local chat model), using its built-in `<tool_call>` structured-output capability:

```json
{"name": "remember_fact",
 "arguments": {
   "fact": "The user is interested in retrieval-augmented generation, particularly self-RAG (Asai et al. 2023).",
   "scope": "user_profile",
   "confidence": 0.85,
   "source_chat_id": "chat_session:abc"
 }}
{"name": "remember_episode",
 "arguments": {
   "summary": "User asked about ARGUS retrieval; we discussed limitations vs. self-RAG; user noted they want to try this approach in their dissertation.",
   "topics": ["retrieval-augmented generation", "self-RAG", "dissertation"],
   "outcome": "next_step_identified",
   "source_chat_id": "chat_session:abc"
 }}
```

These tool calls are emitted by Hermes 3 at end-of-chat and persisted as SurrealDB rows. The episodic memory layer then becomes searchable via the same nomic-embed pipeline.

**Why Hermes 3 specifically:** Hermes 3 is trained on the [Hermes Function Calling format](https://github.com/NousResearch/Hermes-Function-Calling) — when prompted with a system message describing `remember_fact` and `remember_episode` tools, it reliably emits structured JSON. Other models (Qwen2.5, Mistral, etc.) work too via function-calling tuning, but Hermes is the cleanest out-of-the-box experience and ships as our auto-picked default.

### Layer 4 — Procedural memory (v0.4 plan)

**What it is:** The "way I work." Preferences ("bullet points, not paragraphs"), recurring patterns ("when I save a paper, also generate a 100-word abstract"), workflows ("for code-review notebooks, run insights through the linter-rubric transformation").

**Plan for v0.4:**

Procedural memory is a stricter subset of episodic memory — facts about the *user* and the *workflow*, not the content. Same Hermes-3-as-memory-writer pattern, with a `remember_preference` tool whose extracted records are surfaced in the chat system prompt on every subsequent turn.

---

## Open-source memory tech being evaluated for v0.4

Each of these is locally hostable and license-compatible:

| Library | License | Purpose | Fit for Open Notebook Plus |
|---|---|---|---|
| **mem0** (mem0.ai) | Apache 2.0 | Layered memory (user / session / agent), already integrates with LangChain | Strong candidate for Layer 3/4 wrapper — handles the write/read API around our SurrealDB store |
| **Letta** (formerly MemGPT) | Apache 2.0 | Agent-managed long-term + short-term memory with explicit `core_memory_*` tools | Heavier framework; useful as a model for *how* the Hermes agent should reason about its own memory |
| **LangGraph memory** (built-in) | MIT | Already in upstream; supports persistent checkpoints | We're using this for Layer 1 already; can extend for Layer 3 with a custom store |
| **Chroma** | Apache 2.0 | Local vector DB | Not needed — SurrealDB's built-in vectors are enough |
| **NousResearch/Hermes-Function-Calling** | Apache 2.0 | Reference implementation of Hermes tool-call format | Direct dependency for the v0.4 memory writer agent |
| **NousResearch/hermes-agent** v2026.5.7 | (TBD) | Agent runtime for Hermes models | To investigate during v0.4 — may replace our hand-rolled memory writer with their canonical runtime |

**Likely v0.4 stack:** `mem0` as the orchestration layer + Hermes 3 as the memory-writer LLM + SurrealDB as the persistent store + nomic-embed for vector retrieval. Wired together by a new `desktop/memory/` package mirroring the existing `desktop/providers/` and `desktop/desktop_shims/` patterns.

---

## How Hermes agents work in our stack (v0.3 state)

Today (v0.3), Hermes 3 Llama-3.1 8B Q4_K_M is:

1. **Auto-downloaded** if absent (a separate task fetched it during v0.2 model downloads — already in `~/Desktop/AI_Models/GGUF/Hermes-3-Llama-3.1-8B-Q4_K_M.gguf`).
2. **Auto-picked** as the default chat model when the wizard runs (`desktop/__main__.py:_pick_default_gguf`).
3. **Served by `llama_cpp.server`** on a dynamic port via the launcher's `LlamaCppProvider`.
4. **Registered as a Credential + Model** in SurrealDB via `desktop/auto_register.py`.
5. **Selected as the script-writer** for the default Episode Profile that generates Audio Overviews.

In v0.4 it additionally becomes:

6. **Memory writer agent.** End-of-chat hook runs the conversation through Hermes 3 with a memory-writer system prompt + `remember_*` tool definitions. Tool calls are captured and persisted as memory records.
7. **Memory retriever agent.** On chat start, a similarity search over the user's episodic memory surfaces relevant past episodes, summaries, and preferences. These are injected into the system prompt so the model "remembers" what you've previously discussed.

---

## What ships in v0.3 vs. what's deferred

| Capability | v0.3 ship | v0.4 plan |
|---|---|---|
| Per-notebook chat history | ✅ (upstream) | ✅ |
| Per-notebook embedded source search | ✅ (upstream + our embed server) | ✅ |
| LangGraph checkpoint persistence | ✅ (upstream) | ✅ |
| Cross-notebook semantic search | ⚠️ partial (upstream supports if user crosses notebooks manually) | ✅ unified |
| Episodic memory (facts learned from chats) | ❌ | ✅ Hermes 3 + mem0 |
| Procedural memory (user preferences) | ❌ | ✅ Hermes 3 + mem0 |
| Memory dashboard ("what does Open Notebook Plus know about me?") | ❌ | ✅ new Settings page |
| Memory export / wipe | ❌ | ✅ JSON export, "forget everything" button |
| Multi-device sync of memory | ❌ | ⏳ v0.5 (Tailscale/Syncthing) |

---

## Privacy guarantees

All four memory layers run **on this machine, with this user's models, in this user's database**. No memory is ever transmitted to a third party unless the user explicitly:

- Adds an OpenAI / Anthropic / Google API key in Settings → Credentials, AND
- Switches the default chat model to that provider.

Even then, only the *content of the current prompt* leaves the machine — never the persistent memory store, which lives entirely in SurrealDB under `~/.open-notebook-plus/surreal_data/`.

The memory wipe operation in v0.4 will be a single SurrealDB transaction that drops the `memory_episode`, `memory_fact`, and `memory_preference` tables — i.e., factory-reset of long-term memory while leaving notebooks intact. There will be a stronger "wipe everything" button that drops the whole namespace.

---

## File / module map (current + planned)

```
desktop/
├── (v0.3 — already shipping)
│   ├── providers/llamacpp.py          ← serves Hermes 3 for chat
│   ├── launcher.py:_spawn_llamacpp_embed  ← serves nomic-embed
│   └── auto_register.py               ← registers credentials + Episode Profile
│
└── (v0.4 — planned)
    └── memory/
        ├── __init__.py
        ├── writer.py                  ← post-chat Hermes agent that emits remember_* calls
        ├── retriever.py               ← pre-chat lookup of relevant past memory
        ├── store.py                   ← SurrealDB read/write for memory records
        ├── prompts.py                 ← memory-writer / retriever system prompts
        └── tests/test_writer.py       ← golden-output tests for tool extraction

upstream/  (data only, not modified)
├── open_notebook/graphs/chat.py       ← we add an after_invoke hook for memory.writer
└── open_notebook/database/migrations/ ← v0.4 adds X_memory.surrealql
```

---

## How to extend (after v0.4 lands)

To wire a new tool into the Hermes memory writer:

1. Define a function-call schema in `desktop/memory/prompts.py` (Hermes JSON-schema-ish format).
2. Add a handler in `desktop/memory/writer.py:_apply_tool_call` that maps the tool call to a SurrealDB write.
3. Add a migration in `open_notebook/database/migrations/` for any new schema fields.
4. Test it with `desktop/memory/tests/test_writer.py` — feed a synthetic conversation through the writer, assert the right tool calls fire.

---

## References

- **Upstream open-notebook docs**: [docs/](docs/), [README.upstream.md](README.upstream.md)
- **Hermes 3 model card**: https://huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B
- **Hermes Function Calling**: https://github.com/NousResearch/Hermes-Function-Calling
- **Hermes Agent v2026.5.7**: https://github.com/NousResearch/hermes-agent/releases/tag/v2026.5.7
- **mem0**: https://github.com/mem0ai/mem0
- **Letta**: https://github.com/letta-ai/letta
- **LangGraph memory primitives**: https://langchain-ai.github.io/langgraph/concepts/memory/
- **SurrealDB vector search**: https://surrealdb.com/docs/surrealdb/embedding/vector-search
