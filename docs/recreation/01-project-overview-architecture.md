# 01 — Project Overview & Architecture

> Exhaustive recreation documentation for **Open Notebook Plus**.
> Target: an engineer (or AI) rebuilding the system from scratch.
> Repo: `Antman1526/open-notebook-Plus`, branch `desktop-app`.
> Desktop app version: **0.8.97** (`desktop/__init__.py` `__version__`).
> Upstream/Docker image version: **1.8.5** (`pyproject.toml` `version` — a *separate* version track; do not conflate).

---

## 1. What the product is

**Open Notebook Plus** is a local-first, privacy-focused **desktop research assistant** — an open-source alternative to Google's NotebookLM. It is a **fork of `lfnovo/open-notebook`** that wraps the upstream three-tier web application inside a **native desktop app** (macOS `.app`/`.dmg`, Windows local install) so that the *entire stack runs on the user's own machine*, including the LLMs.

The user uploads multi-modal content (PDFs, audio, video, web pages, text), the app extracts and embeds it, and the user can then:

- **Chat** with an AI model grounded in their sources (RAG).
- **Ask** questions that trigger search + synthesis across all sources.
- **Generate notes** and AI **insights/transformations** per source.
- **Semantic + full-text search** across everything.
- **Produce multi-speaker podcasts** from their notebook (TTS).
- Do all of the above **fully offline** using local GGUF models via llama.cpp / Ollama / MLX, or optionally with cloud providers (OpenAI, Anthropic, Google, Groq, Mistral, DeepSeek, xAI, …) through the **Esperanto** multi-provider library.

**Key values:** privacy-first (data never leaves the machine unless the user opts into a cloud provider), multi-provider AI, self-hosted, open-source.

### The dual role of "Plus"
The "Plus" fork adds a full **desktop wrapper** (`desktop/`) that:
1. Bundles a Python runtime, SurrealDB, Node, and model sidecars.
2. Boots the whole stack as child processes ("supervisor").
3. Renders the Next.js frontend inside a native **pywebview** window (WKWebView on macOS).
4. Adds local-model management, a first-run wizard, a memory layer (mem0 + OpenChronicle), and self-healing DB repair.

---

## 2. Full feature list

**Content & knowledge**
- Multi-modal ingestion (files + URLs) via **content-core** (50+ file types).
- Automatic chunking + embedding (vector search) with content-type-aware splitters.
- Per-source **insights** and reusable **transformations** (LLM prompts).
- Standalone and source-linked **notes** (auto-embedded).
- **Full-text** (`text_search`) and **semantic/vector** (`vector_search`, default `minimum_score=0.2`) search, with graceful fallback between them.

**AI interaction**
- **Chat** graph (conversational agent with message history + optional MCP tool use).
- **Ask** graph (query → retrieve → synthesize with citations).
- **Source chat** (chat scoped to one source).
- **Transformation** graph (custom per-source LLM operations).
- Smart provider routing: prefer local model when healthy, fall back to cloud (`open_notebook/ai/provision.py`).
- Per-request model override via `RunnableConfig`.

**Podcasts**
- Multi-speaker podcast generation (`podcast-creator`) with episode + speaker profiles.
- Async job queue; retry endpoint (`POST /podcasts/episodes/{id}/retry`); no silent-audio fallback.

**Memory (Plus-only)**
- **mem0** in-process memory (chat summarizer + fact extractor).
- Optional **OpenChronicle** MCP bridge for a "Capture Inbox".
- Memory dashboard window.

**Desktop platform (Plus-only)**
- First-run setup wizard (provider selection, model dir).
- Auto-download of embedding + STT + TTS models.
- Local model manager window; hot-swap chat GGUF without restart.
- System tray (Open Main / Models / Memory / Quit).
- 20+ built-in themes injected into the webview.
- Singleton enforcement + orphan process reaper.
- Automatic DB backup/export + self-healing repair on boot.
- In-app update notifier.

**Ops / security**
- Prometheus `/metrics`; health endpoints `/health`, `/livez`, `/readyz`.
- Fernet-encrypted credential store (per-provider records).
- Password auth middleware, rate limiting, security headers, request IDs.
- SSRF-protected URL validation.

---

## 3. Tech stack (with versions)

### Frontend — `frontend/` (`frontend/package.json`)
| Concern | Choice | Version |
|---|---|---|
| Framework | Next.js (App Router, standalone output) | `^16.2.3` |
| UI runtime | React / React DOM | `^19.2.3` |
| Language | TypeScript | `^5` |
| State | Zustand | `^5.0.6` |
| Data fetching | TanStack React Query | `^5.83.0` |
| Styling | Tailwind CSS v4 (`@tailwindcss/postcss`) + shadcn/ui | `^4` |
| Components | Radix UI primitives (accordion, dialog, dropdown, select, tabs, tooltip, …) | `1.x`–`2.x` |
| Forms | react-hook-form `^7.60.0` + zod `^4.0.5` + `@hookform/resolvers` `^5.1.1` |
| Markdown/math | react-markdown `^10.1.0`, remark-gfm/math, rehype-katex, `@uiw/react-md-editor` |
| Graph/flow | `@xyflow/react` `^12.11.1` |
| HTTP | axios `^1.15.0` |
| i18n | i18next `^25.7.3`, react-i18next `^16.5.0`, browser language detector |
| Virtualization | `@tanstack/react-virtual` `^3.13.24` |
| PDF | react-pdf `^10.4.1` |
| Toasts / cmd / motion | sonner, cmdk, framer-motion |
| Test | Vitest `^4.1.8`, Testing Library, jsdom |
| Lint | ESLint `^9` + `eslint-config-next` |

### Backend — `api/` + `open_notebook/` (`pyproject.toml`)
| Concern | Choice | Constraint |
|---|---|---|
| Python | CPython | `>=3.11,<3.13` (bundled desktop runtime is 3.12) |
| Web framework | FastAPI | `>=0.136.3` |
| ASGI server | uvicorn | `>=0.24.0` |
| Validation | Pydantic v2 | `>=2.9.2` |
| Logging | Loguru | `>=0.7.2` |
| Orchestration | LangChain / LangGraph | `langchain>=1.2.0`, `langgraph>=1.0.10` |
| LG checkpoints | langgraph-checkpoint-sqlite | `>=3.0.1` |
| LC providers | langchain-openai/anthropic/ollama/google-genai/groq/mistralai/deepseek/community | see pyproject |
| Tokenizer | tiktoken | `>=0.12.0` |
| DB driver | surrealdb | `>=1.0.4` |
| Multi-provider AI | esperanto | `>=2.20.0,<3` |
| Job queue | surreal-commands | `>=1.3.1,<2` |
| Content extraction | content-core | `>=1.14.1,<2` |
| Prompt templating | ai-prompter (Jinja2) | `>=0.4,<1` |
| Podcasts | podcast-creator | `>=0.12.0,<1` |
| MCP | mcp | `>=1.0.0` |
| Metrics | prometheus-client | `>=0.20.0` |
| Numerics / i18n | numpy `>=2.4.1`, pycountry `>=26.2.16`, babel `>=2.18.0` |
| Model fetch | huggingface-hub | `>=1.3.0` |

Backend dev tools (`[dependency-groups].dev`): `pytest>=9.0.3`, `pytest-asyncio>=1.2.0`, `ruff>=0.14.13`, `mypy`, `pre-commit`. Ruff/isort line length 88; ruff selects `E,F,I,UP006,UP007`.

### Database
- **SurrealDB** graph DB (`ws://…/rpc`), namespace/database both `open_notebook`. Stores records + vector embeddings; supports full-text (`search::highlight`) and vector search. Migrations auto-run on API startup via `AsyncMigrationManager` from `.surrealql` files.

### Desktop wrapper — `desktop/` (`desktop/requirements.txt`, pinned separately from pyproject)
| Concern | Package | Pin |
|---|---|---|
| Native window | pywebview | `==5.4` |
| Packaging | pyinstaller | `>=6.13.0,<7` |
| Local chat/embed server | llama-cpp-python[server] | `>=0.3.16,<0.4` |
| Apple-Silicon LLM server | mlx-lm | `>=0.30.6,<0.32` (darwin/arm64 only) |
| STT | faster-whisper | `>=1.1.0,<2` |
| TTS | piper-tts | `>=1.2.0,<2` |
| Memory | mem0ai | `>=0.1.0,<2` |
| MCP client / server | mcp `>=1.0,<2`, fastmcp `>=3.0,<4` |
| Async HTTP | aiohttp `>=3.11.18,<4`, httpx `==0.28.1` |
| Prompt optimizer | skillopt `>=0.1.0,<0.2` |

Bundled binaries live under `desktop/bin/` (fetched by `desktop/build/fetch_runtimes.py`): the `surreal` binary, a Node runtime, the `uv` binary, and a `python-build-standalone` tarball (`python-{arch}.tar.gz`).

---

## 4. Three-tier + desktop-wrapper architecture

Upstream is a classic three-tier web app. "Plus" adds a **process-supervisor + native-window wrapper** (tier 0) around it, plus **model sidecars** hanging off the API tier.

```
┌───────────────────────────────────────────────────────────────────────┐
│  TIER 0 — DESKTOP WRAPPER  (desktop/, runs natively, never in Docker)  │
│  launcher.Supervisor  +  pywebview window (WKWebView)                  │
│  system tray · first-run wizard · model manager · memory dashboard     │
└───────────────┬───────────────────────────────────────────────────────┘
                │ spawns + supervises child processes; opens webview at frontend_url
                ▼
┌───────────────────────────────────────────────────────────────────────┐
│  TIER 1 — FRONTEND   frontend/  (Next.js 16 standalone, node child)    │
│  React 19 · Zustand · TanStack Query · shadcn/Radix · Tailwind v4      │
│  Notebooks · Sources · Notes · Chat · Podcasts · Search · Settings     │
└───────────────┬───────────────────────────────────────────────────────┘
                │ HTTP REST (Next.js rewrites /api/* → dynamic uvicorn port)
                ▼
┌───────────────────────────────────────────────────────────────────────┐
│  TIER 2 — API   api/ + open_notebook/  (FastAPI on uvicorn, py child)  │
│  routers/*  ·  4 real services  ·  LangGraph graphs  ·  Esperanto      │
│  Fernet credential store · migrations · Prometheus · health endpoints  │
│                                                                         │
│  ── async job worker (surreal-commands): podcasts, embeddings,         │
│     insights, transformations  (separate python child, imports        │
│     `commands/`)                                                        │
└───────┬──────────────────────────────────────┬────────────────────────┘
        │ SurrealQL (ws://…/rpc)                │ OpenAI-compatible HTTP (/v1)
        ▼                                       ▼
┌─────────────────────────┐   ┌────────────────────────────────────────┐
│  TIER 3 — SurrealDB      │   │  LOCAL MODEL SIDECARS (per-launch)      │
│  graph DB + vectors      │   │  llama.cpp chat · llama.cpp embed       │
│  ns/db = open_notebook   │   │  faster-whisper (STT) · piper (TTS)     │
│  (surreal binary child)  │   │  mem0 memory retriever · OpenChronicle  │
└─────────────────────────┘   └────────────────────────────────────────┘
```

### Component relationships
- **Frontend → API:** the browser hits `/api/*`; Next.js rewrites proxy to the API. In dev the API is `http://localhost:5055`; in the packaged app the port is dynamic and injected via env (`API_URL`, `INTERNAL_API_URL`, `NEXT_PUBLIC_API_URL`) and patched into the Next.js standalone rewrites at boot (`desktop/next_rewrites_patcher.py`).
- **API → SurrealDB:** async driver, connection-pooled, lazy-initialized on first `repo_query`.
- **API → AI:** `open_notebook/ai/provision.py` picks a provider (local vs cloud) and returns a LangChain model via **Esperanto**; credentials are decrypted from the DB (Fernet) or fall back to env vars (`open_notebook/ai/key_provider.py`).
- **API → local sidecars:** the API talks to the llama.cpp chat/embed servers over OpenAI-compatible `/v1`; the frontend voice UI talks to whisper/piper shims directly on their dynamic ports.
- **Worker:** the `surreal-commands` worker imports `commands/` and executes fire-and-forget jobs (podcasts, embeddings, insights, source processing) submitted by the API/domain models.

---

## 5. Request / data-flow diagrams (ASCII)

### Source ingestion (upload → searchable)
```
UI upload ──POST /sources──▶ api/routers/sources.py
                                │ create Source record (SurrealDB)
                                │ submit "process_source" job (fire-and-forget)
                                ▼
                    surreal-commands worker (commands/source_commands.py)
                                │ source_graph.ainvoke:  extract → transform → save
                                │ (content-core extracts text/metadata)
                                ▼
                        submit "embed_source" job (commands/embedding_commands.py)
                                │ chunk_text() (content-type aware, 1500/225)
                                │ generate_embeddings() (batches of 50, Esperanto)
                                ▼
                        write SourceEmbedding rows ──▶ SurrealDB (vector index)
UI polls  GET /commands/{id}  ◀── job status
```

### Chat turn (SSE stream)
```
UI ──POST /chat (message, notebook_id, session_id)──▶ api/routers/chat.py
        │ load ChatSession history (SurrealDB, capped)
        │ build context from notebook sources/notes
        ▼
   chat graph (open_notebook/graphs/chat.py)
        │ provision_langchain_model()  (local-if-healthy else cloud, Esperanto)
        │ optional MCP tool loop
        │ checkpoint state → SQLite (langgraph-checkpoint-sqlite)
        ▼
   token stream ──SSE──▶ UI  (disconnect-aware; reader.cancel on abort)
```

### Ask / RAG synthesis
```
UI ──POST (question)──▶ ask graph (open_notebook/graphs/ask.py)
        │ query_process → vector_search + text_search over sources
        │ assemble evidence → final_answer prompt (prompts/ask/*.jinja)
        ▼
   answer + citations ──▶ UI
```

---

## 6. Process model (desktop)

When the user double-clicks the `.app`, the frozen PyInstaller launcher runs `desktop.app.run()`, which builds one **`Supervisor`** (`desktop/launcher.py`) that spawns and monitors a tree of child processes. Ports are all allocated dynamically and atomically via `desktop/ports.py :: find_free_ports(9)` (SO_REUSEADDR probe sockets, de-dup + re-probe).

```
Open Notebook Plus.app (frozen launcher, pywebview main thread)
│
├─ surreal-<arch>  start --user --pass --bind 127.0.0.1:<surreal_port>  file://<data_dir>
│      (SurrealDB; data at ~/.open-notebook-plus/surreal_data)   [core]
│
├─ <venv python> -m uvicorn api.main:app --host 127.0.0.1 --port <api_port>
│      cwd = upstream_root; waits on /readyz (migrations applied)  [core]
│
├─ <venv python> -m surreal_commands.cli.worker --import-modules commands --max-tasks 5
│      (async job worker; no port)                                [core]
│
├─ node <next standalone server>  PORT=<frontend_port>
│      (Next.js; rewrites patched to api_port; waits on "/" 3× 200) [core]
│
├─ llama.cpp embed sidecar   (llama_cpp.server, nomic-embed GGUF)  [optional]
├─ faster-whisper STT shim   (/v1/audio/transcriptions)           [optional]
├─ piper TTS shim            (/v1/audio/speech)                    [optional]
├─ llama.cpp chat sidecar    (chat GGUF, --n_gpu_layers -1 on mac) [optional]
├─ mem0 memory retriever shim                                     [optional]
└─ OpenChronicle MCP bridge  (only if a live MCP daemon detected) [optional]

Plus in-process (aiohttp threads in the launcher, not subprocesses):
  · launcher control plane (restart/hot-swap callbacks)
  · model-manager window server        (mm_port)
  · memory-dashboard window server     (memory_dashboard_port)
  · system tray
  · pywebview main window → http://127.0.0.1:<frontend_port>/
```

Core services block startup with early-exit-on-dead-child gates (`_wait_tcp` / `_wait_http` poll `proc.poll()`); optional sidecars are best-effort via `_try_spawn` and degrade gracefully. On `stop_all` the launcher kills whole **process groups** (`start_new_session=True` + `os.killpg` on POSIX, `taskkill /F /T` on Windows) so no `next-server` grandchildren leak.

**Env threaded into every child (`session_env`, `launcher.py :: start_all`)** includes: `DATA_FOLDER` (absolute, always writable), `SURREAL_URL/USER/PASSWORD/NAMESPACE/DATABASE`, `API_PORT`, `API_URL`/`INTERNAL_API_URL`/`NEXT_PUBLIC_API_URL`, `OPEN_NOTEBOOK_ENCRYPTION_KEY`, `OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL`, `OPEN_NOTEBOOK_LOCAL_N_CTX`, `MEMORY_*_URL`, and the launcher control-plane URL/token. `PORT` is deliberately **not** in the shared env (it would hijack uvicorn-based sidecars) — it is passed only to the Next.js child.

---

## 7. Boot sequence (how the pieces come up)

`desktop/app.py :: run()` threads a mutable `AppContext` dataclass through ordered phases:

| # | Phase (`_phase_*`) | What it does |
|---|---|---|
| 1 | `load_config` | Locate `~/.open-notebook-plus/config.toml`; set `_first_run`; set up `logs/` + rotating `launcher.log` + `ProgressBus` (`progress.jsonl`). |
| 2 | `wizard_if_first_run` | On first launch, run the blocking first-run wizard (`desktop/first_run/server.py`); then load `Config`. |
| 3 | `bootstrap_runtime` | Extract bundled `python-build-standalone` into `~/.open-notebook-plus/`; provision the venv from `desktop/requirements.lock` using bundled `uv` (`desktop/bootstrap.py`). Sets `ctx.venv_py`, `ctx.bin_dir`, `ctx.arch`. |
| 4 | `download_models` | Auto-download embedding + STT + TTS voice models into `model_dir` (`desktop/model_downloads.py`). Non-fatal. |
| 5 | `select_provider` | For `ollama`/`mlx` start/connect the provider and populate `extra_env`. (`llamacpp` is now a no-op here — the Supervisor owns the spawn.) |
| — | `detect_openchronicle` | Two-stage probe (TCP then MCP `initialize`) of the OpenChronicle daemon; sets `openchronicle_available`. Never raises. |
| — | `register_memory_commands` | Copy `desktop/memory/memory_commands.py` into the upstream `commands/` dir so the worker discovers the memory handlers. |
| 6 | `start_supervisor` | Resolve model paths (chat GGUF via a **timeout-bounded** dir scan, nomic embed, piper voices, whisper), build `Supervisor(...)`, call `start_all()`. Handles the `AlreadyRunning` singleton case with a native dialog. |
| 7 | `auto_register` | Register discovered local models/credentials with the API using the supervisor's dynamic ports; active health-probe each sidecar. Non-fatal. |
| 8 | `start_model_manager` | Start the aiohttp model-manager window server thread (`mm_port`). |
| — | `start_memory_dashboard` | Start the aiohttp memory-dashboard server thread; wire memory-retriever + OpenChronicle + upstream-API URLs. |
| 9 | `install_tray` | Install the system tray (Open Main / Models / Memory / Quit). |
| 10 | `open_window` | Open the pywebview main window at `frontend_url` — **blocks** until closed; teardown calls `sv.stop_all()`. |

Phases 7–10 are wrapped in `try/except BaseException` that calls `sv.stop_all()` so no child processes are orphaned if a late phase fails.

### The window handoff (`desktop/window.py :: open_window`)
The window opens on an **inline splash HTML** first (paints instantly, no network). A python-driven **handoff controller** (`_start_handoff_controller`) then:
1. Waits until `_frontend_server_ready(url)` passes `consecutive` times AND the splash has shown ≥ `min_splash_sec`.
2. Calls `window.load_url(url)`.
3. Waits for the `loaded` event to confirm a *real* Next.js app page via the JS sentinel `(!!window.__next_f) && !title.startsWith("404")` — this rejects WebKit's error page and Next's warm-up 404 (which returns HTTP 200).
4. On timeout, restores the splash and retries (budget ~40×6s) — the error page can never be the resting state.

Once confirmed, `_theme_injection_js()` injects all ~20 themes' shadcn CSS variables (keyed by `[data-theme]`), the voice-injection JS (with per-launch STT/TTS shim URLs), and the memory-injection JS (with `window.ONP_VERSION`, `window.ONP_MEMORY_URL`). WebKit storage is persisted (`private_mode=False`, `storage_path=~/.open-notebook-plus/webview_data`) so the wizard/intro cookies survive restarts.

`window.pywebview.api.relaunch()` (`_OnpJsApi`) powers the one-click "Repair & restart" DB-repair banner: it spawns a detached shell that SIGTERMs (then SIGKILLs) this process and `open`s the `.app` again.

---

## 8. Key architectural notes & gotchas (from CLAUDE.md)

- **Two real API layers:** routers (most business logic lives inline) + Pydantic models. Only four `*_service.py` files are actually imported: `chat_service`, `podcast_service`, `command_service`, `credentials_service` (per-resource services were deleted in v0.7.21).
- **Async-first:** every DB query, graph invocation, and AI call is `await`. Sync `surreal_commands.submit_command` inside `async def` must be wrapped in `asyncio.to_thread`.
- **Edge tables** `reference`, `artifact`, `refers_to` — `in`/`out` direction is easy to invert; delete cascades must be complete.
- **LangGraph state-shape variance:** accept both dict and Pydantic via `getattr` fallback.
- **SSE handlers** must check `is_disconnected()` and `reader.cancel()` before release.
- **Credentials** are individual Fernet-encrypted records (`open_notebook/domain/credential.py`); `OPEN_NOTEBOOK_ENCRYPTION_KEY` is required.
- **Error handling:** `open_notebook.exceptions` hierarchy + `classify_error()` map raw provider errors to typed exceptions → HTTP codes (404/400/401/429/422/502/500) via global FastAPI handlers.
