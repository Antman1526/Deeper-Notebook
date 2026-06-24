# Open Notebook Plus

**A privacy-first, fully-local-capable alternative to Google NotebookLM.** Open Notebook Plus is a native desktop research notebook where you upload multi-modal sources (PDFs, audio, video, web pages, and raw text), generate AI notes and insights, chat with your sources, run semantic and multi-step "Ask" search across your whole library, and produce professional multi-speaker podcasts and instructor-ready Course Packs — all powered by **your** choice of AI provider, whether a cloud API or a fully-local llama.cpp / Ollama / MLX model so that no data ever leaves your machine. It is a substantially extended fork of [`lfnovo/open-notebook`](https://github.com/lfnovo/open-notebook) that adds a native desktop launcher with bundled AI sidecars, offline/online smart-switching, staged podcast generation with outline review, a SkillOpt prompt optimizer, a closed-loop memory layer, a fail-closed cloud-privacy gate, Evidence Studio artifact generation, and a downstream-friendly update strategy on top of upstream.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![Python 3.12](https://img.shields.io/badge/Python-3.11%20|%203.12-blue)
![Next.js 16](https://img.shields.io/badge/Next.js-16-black)
![React 19](https://img.shields.io/badge/React-19-149eca)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136.3%2B-009688)
![LangGraph](https://img.shields.io/badge/LangGraph-1.0-ff6f00)
![SurrealDB v2](https://img.shields.io/badge/SurrealDB-v2-ff5722)
![Tests](https://img.shields.io/badge/tests-1712%20backend%20%2B%20195%20frontend-success)

> GitHub: **https://github.com/Antman1526/open-notebook-Plus** — a downstream fork of [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook).

---

## Table of Contents

- [What it is](#what-it-is)
- [Key features](#key-features)
- [Screenshots](#screenshots)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [How it works (data flow)](#how-it-works-data-flow)
- [Installation](#installation)
  - [Desktop app (macOS `.dmg`)](#desktop-app-macos-dmg)
  - [From source (development)](#from-source-development)
- [Configuration](#configuration)
- [Running tests](#running-tests)
- [Reconstruction documentation](#reconstruction-documentation)
- [Project structure](#project-structure)
- [Privacy & local-first stance](#privacy--local-first-stance)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## What it is

Open Notebook Plus is a desktop application for **source-grounded AI research**. You organize your work into *notebooks*; into each notebook you drop *sources* (documents, audio, video, web URLs, pasted text). The app extracts and chunks the content, embeds it into a vector store, and from then on every interaction — chat answers, generated notes, "Ask" syntheses, podcast scripts — is grounded in *your* sources, with interactive citation pills that link each claim back to the document it came from.

The defining difference from NotebookLM is **ownership and locality**: your notebooks, sources, embeddings, chat history, and extracted memory live in a SurrealDB database on your own drive, behind a password you set, and the app can run **entirely offline** against a local GGUF chat model, a local embedding model, local speech-to-text, and local text-to-speech. Cloud providers (OpenAI, Anthropic, Google, Groq, Mistral, DeepSeek, xAI, Ollama, and more) are fully supported but strictly **opt-in**.

---

## Key features

### Multi-modal source ingestion
- **Upload anything:** PDFs, Word/Office docs, plain text and Markdown, audio and video files, and web URLs. File extraction is handled by the `content-core` library (50+ file types); audio/video are transcribed via a local Whisper (faster-whisper / CTranslate2) sidecar.
- **Web ingestion with JS rendering:** URLs are fetched and cleaned. An optional local **Crawl4AI / Playwright** engine renders dynamic JavaScript pages and evades basic anti-bot blocks, with automatic graceful fallback to standard HTTP extractors when the optional engine or its browser binaries aren't installed.
- **Automatic embedding:** ingested content is chunked and embedded into SurrealDB so it is immediately searchable and chat-able. A local `nomic-embed-text-v1.5` embedding sidecar covers this with zero network calls.

### AI notes, insights & transformations
- Generate AI notes and structured **insights** from any source. **Transformations** are reusable, named prompt templates (summaries, key-point extraction, topic lists, custom analyses) that you run over sources to produce new notes.
- **Prompt optimizer (SkillOpt, MIT):** every transformation card has an **Optimize** action that *trains* the prompt against real sources from a notebook of your choice. Each round runs the prompt over example sources, an LLM judge scores the outputs against your plain-English criteria, the optimizer proposes bounded edits, and only edits that improve a held-out validation split are kept. The result is shown side-by-side and applied only when you click **Apply**. It runs against any OpenAI-compatible endpoint, so the local llama.cpp sidecar (or Ollama) can fill both the target and judge roles with zero data leaving the machine.

### Evidence Studio and Course Packs
- **Evidence Studio** turns a selected notebook, upload batch, link set, or mixed source bundle into reusable artifacts: reports, study guides, Course Packs, briefings, FAQs, timelines, flashcards, quizzes, data tables, mind maps, slide-deck outlines, infographic briefs, podcast outlines, and research runs.
- **Course Pack** is the richer successor to the old "training guide" label. It treats videos and audio as lesson segments, PDFs and docs as readings/reference modules, and links as external resources. The generated markdown includes audience, learning outcomes, prerequisite knowledge, source-readiness notes, module roadmap, timed lessons, hands-on exercises, facilitator notes, learner handouts, knowledge checks, final assessment, follow-up resources, and citation markers.
- **Workflow approval gates** track context building, privacy review, model routing, and artifact generation. If selected sources are still processing, generation fails with a structured `sources_not_ready` response instead of producing thin material.

### Chat grounded in your sources
- Converse with an AI that answers from your notebook's sources, with **interactive citation pills** linking every grounded claim back to the originating document.
- **MCP tool support:** plug in any Model Context Protocol server (web search, fetch, custom tools) per conversation; the chat graph wires them into the LLM's tool surface automatically.
- **Native web search:** a built-in `web_search` chat tool, opt-in by key presence (`SERPER_API_KEY` / `TAVILY_API_KEY` / `SEARXNG_BASE_URL`), with a multi-provider failover chain and a toggleable picker row. Includes a ship-it-yourself private localhost SearXNG (`deploy/searxng-private/`).
- **Closed-loop memory:** facts, preferences, and episode summaries are automatically extracted from each chat and recalled into the system prompt of future chats, so the assistant remembers what you told it across sessions — with bounded retention, batched extraction, a confidence floor, and prompt-injection sanitization.

### Ask & semantic search across the library
- **Ask** runs a multi-step retrieve-then-synthesize workflow across your entire notebook: it pulls the most relevant sources, then has the LLM synthesize a cited answer — declining to answer when the sources don't support a grounded response.
- Semantic vector search is accelerated by **SurrealDB HNSW indexes** on source-embedding, insight, and note tables, taking similarity queries from brute-force `O(N)` scans to sub-millisecond indexed lookups via `vector::similarity::cosine`.

### Professional multi-speaker podcasts
- Turn a notebook's sources into a polished, multi-speaker audio podcast (the NotebookLM "Audio Overview" feature, but with more control).
- **Staged generation with progress, cancel, and outline review:** generation streams through named stages (outline → transcript → audio → combining) with a live per-stage progress indicator and a **Cancel** button. An optional **"Review outline before generating audio"** step pauses after the outline so you can edit segment titles, descriptions, and short/medium/long sizing, then **Approve & generate audio** to resume — a step NotebookLM doesn't offer.
- **Reliability:** per-episode instructions are stored and replayed on retry; completed episodes can be regenerated; BCP-47 language selection is honored; content token budgets are enforced at submit so oversized selections fail fast instead of hanging mid-job. TTS can run fully local via a **Piper** sidecar.

### Offline / online smart switching
- A network-state service probes connectivity (with caching and passive flips from real cloud-call results). When the machine is **offline** — or when you flip the **Offline-mode toggle** in Settings → Network — any turn routed to a cloud model is transparently substituted with the best local model instead of hanging for minutes on an unreachable endpoint. An amber "Offline — answering with `<model>`" badge appears in the app shell, and each affected message gets an "Answered with `<model>` (offline)" pill.
- **Smart routing (opt-in):** per-turn local-vs-cloud routing picks the best provider for each turn based on context size and sidecar health, so you don't switch manually.

### Local-AI-first, multi-provider
- Bundled `llama-cpp-python` chat + embedding servers, Ollama auto-detection, Apple-Silicon MLX server support, and a **GGUF Manager** for downloading models from HuggingFace and hot-swapping them at runtime.
- Drop any `.gguf` file into `~/Desktop/AI_Models/GGUF/` and it appears in the picker on next launch; place complete MLX repos under `~/Desktop/AI_Models/MLX/`; `ollama pull <name>` makes Ollama models available too.
- Cloud providers are available through the **Esperanto** unified model layer (14+ providers) and are entirely opt-in via encrypted credentials you add in Settings.

### Production-grade operations
- **Closed observability:** every response carries an `X-Request-ID`, every log line is request-correlated, and a Prometheus `/metrics` endpoint exposes request latency, DB query latency, slow-query counts, memory-recall fall-through reasons, checkpoint-prune cycles, and privacy-gate / tool-loop counters.
- **Backup & restore** with atomic writes, an embedded SHA-256 manifest, and versioned bundle format; the desktop app also auto-exports the database on an interval.
- **Self-healing database:** detects SurrealDB live-query corruption after an unclean shutdown and runs a backup-first auto-repair on the next launch.

---

## Screenshots

> _Screenshots coming soon._ Add images under `docs/assets/` and reference them here, e.g.:
>
> ```markdown
> ![Notebook view](docs/assets/notebook.png)
> ![Source chat with citations](docs/assets/chat-citations.png)
> ![Podcast outline review](docs/assets/podcast-outline.png)
> ```

---

## Architecture

Open Notebook Plus is a **three-tier application** (frontend / API / database) plus, in the desktop build, a **launcher** that supervises a set of **local AI sidecar processes**.

```
+-----------------------------------------------------------------------+
|  Frontend   Next.js 16 + React 19 + TypeScript            :3000       |
|  Zustand state · TanStack Query 5 · Shadcn/ui + Tailwind · i18n (10)  |
+----------------------------+------------------------------------------+
                             |  HTTP REST + NDJSON + SSE streams
+----------------------------v------------------------------------------+
|  API        FastAPI 0.104 + Python 3.12                   :5055       |
|  LangGraph 1.0 workflows (source / chat / ask / transformation)      |
|  Esperanto multi-provider model layer · surreal_commands job queue   |
|  Pydantic v2 · request-ID middleware · Prometheus /metrics           |
+----------------------------+------------------------------------------+
                             |  SurrealQL (AsyncSurreal connection pool)
+----------------------------v------------------------------------------+
|  Database   SurrealDB v2                                  :8000       |
|  Graph + document + vector + KV in one engine                        |
|  HNSW vector indexes · native vector::similarity::cosine             |
+-----------------------------------------------------------------------+

Desktop launcher (desktop/launcher.py) additionally supervises:
  • llama-cpp-python embed server   (nomic-embed-text-v1.5)
  • llama-cpp-python chat server     (Hermes-3 / Qwen2.5-Instruct GGUF)
  • Whisper STT sidecar              (faster-whisper / CTranslate2)
  • Piper TTS sidecar                (local podcast / voice synthesis)
  • mem0 memory shim                 (closed-loop memory store)
  • surreal_commands worker          (async jobs: podcasts, embeddings,
                                       prompt optimization, ingestion)
  • a bundled SurrealDB + Node.js runtime (single .app, no separate installs)
```

**Frontend (`frontend/`)** — A Next.js 16 / React 19 app. State is held in Zustand stores; server state is fetched and cached with TanStack Query; UI is built from Shadcn/ui (Radix primitives) + Tailwind CSS. It talks to the API over REST for CRUD and over SSE / NDJSON streams for chat, ask, and job progress. Fully internationalized across 10 locales.

**API (`api/` + `open_notebook/`)** — A FastAPI app exposing REST routers for notebooks, sources, notes, chat, ask/search, podcasts, transformations, models, credentials, MCP, Gmail digests, and system/health. Conversational and ingestion logic is orchestrated by **LangGraph** state machines. Long-running work (podcast generation, embedding rebuilds, prompt optimization, source ingestion) is dispatched to an async **surreal_commands** job queue and polled via the commands API.

**Database (SurrealDB v2)** — A single engine providing graph relationships, document storage, vector search, and key-value storage. Domain records (Notebook, Source, Note, ChatSession, PodcastEpisode, Credential, memory tables) and their edges (`reference`, `artifact`, `refers_to`) all live here. Schema migrations run automatically on API startup via `AsyncMigrationManager`.

**Desktop launcher & AI sidecars (`desktop/`)** — A pywebview-based native shell that boots SurrealDB, the API, and the Next.js server, supervises the local-AI sidecars listed above, manages ports and health, shows a welcome splash with a status-verified handoff to the app, and ships data-protection features (auto-export, self-healing DB repair, remembered window size).

---

## Tech stack

| Layer | Technology | Version |
|---|---|---|
| Frontend framework | Next.js | 16 |
| UI library | React | 19 |
| Language (frontend) | TypeScript | 5 |
| State management | Zustand | 5 |
| Data fetching | TanStack Query (React Query) | 5 |
| UI components | Shadcn/ui (Radix UI) + Tailwind CSS | Radix 1.x / Tailwind 4 |
| Markdown/editor | `@uiw/react-md-editor`, `react-markdown`, `remark-gfm` | — |
| i18n | i18next / react-i18next | 25 / 16 |
| API framework | FastAPI | 0.136.3+ |
| Language (backend) | Python | 3.11–3.12 (3.12 runtime) |
| Workflow engine | LangGraph | 1.0.10+ |
| LLM glue | LangChain + provider packages | 1.x |
| Multi-provider model layer | Esperanto | 2.20+ |
| Validation | Pydantic | v2 |
| Job queue | surreal-commands | 1.3+ |
| Logging | Loguru | — |
| Database | SurrealDB | v2 |
| DB driver | `surrealdb` (AsyncSurreal) | 1.x |
| Content extraction | content-core | 1.14+ |
| Prompt templating | ai-prompter (Jinja2) | 0.4+ |
| Podcast generation | podcast-creator | 0.12+ |
| Local LLM runtime | llama-cpp-python / MLX / Ollama | llama-cpp-python 0.3.x / mlx-lm 0.26.x |
| Local embeddings | nomic-embed-text-v1.5 (GGUF) | — |
| Local STT | faster-whisper (CTranslate2) | — |
| Local TTS | Piper | — |
| Memory | mem0 + SurrealDB memory store | — |
| Web search | Serper / Tavily / SearXNG | — |
| Web crawl (optional) | Crawl4AI + Playwright | — |
| Prompt optimizer (optional) | Microsoft SkillOpt | 0.1.0 |
| Metrics | prometheus-client | 0.20+ |
| MCP | `mcp` client | 1.0+ |
| Desktop shell | pywebview + PyInstaller | — |
| Package managers | `uv` (Python), `npm` (JS) | — |

---

## How it works (data flow)

**1. Ingest a source**
```
Upload file / URL / text
  → API source router dispatches a source-ingestion job (surreal_commands)
  → LangGraph source graph: extract (content-core / Crawl4AI / Whisper)
                            → chunk → embed (local or cloud embedder)
                            → save Source + embeddings to SurrealDB
  → frontend polls job status; source appears in the notebook when ready
```

**2. Chat with your sources**
```
User message → /chat/stream (SSE)
  → chat LangGraph: recall_memory() injects "what you remember about the user"
                  → smart router / offline gate picks local vs cloud model
                  → privacy gate keeps secrets/PII on-device (fail-closed)
                  → retrieve relevant source chunks (HNSW vector search)
                  → LLM answers, may call MCP / web_search tools
  → tokens stream back with citation pills
  → after the turn: fire-and-forget memory extraction writes facts/preferences
```

**3. Ask across the library**
```
Question → ask LangGraph: retrieve top-k relevant sources across the notebook
                        → synthesize a cited answer (declines if ungrounded)
```

**4. Generate a podcast**
```
Select sources + episode/speaker profiles → /podcasts (job)
  → staged podcast graph: outline → [optional outline review/edit] →
                          transcript → audio (TTS) → combine → playable MP3
  → per-stage progress written to the episode; Cancel polled every ~5s
```

---

## Installation

### Desktop app (macOS `.dmg`)

The recommended way to run Open Notebook Plus — no Docker, no terminal, with all AI sidecars bundled.

1. Download the latest `.dmg` from [Releases](https://github.com/Antman1526/open-notebook-Plus/releases).
2. Drag **Open Notebook Plus** into **Applications**.
3. The build is unsigned, so the first launch needs **Right-click → Open** to clear macOS Gatekeeper.
4. On first run the app boots its bundled SurrealDB + Node runtime, downloads the local model files it needs, and opens on a welcome splash before handing off to the main UI.

> **Windows:** desktop builds are produced on a Windows host through GitHub Actions because PyInstaller is not a cross-compiler. The workflow packages `dist/Open-Notebook-Plus-windows-x64.zip`, containing `Open Notebook Plus.exe` and its bundled runtime folder. See [`.github/workflows/build-windows.yml`](.github/workflows/build-windows.yml) and [`desktop/build/post_build_windows.ps1`](desktop/build/post_build_windows.ps1).

### From source (development)

Requirements: **Python 3.12**, [`uv`](https://github.com/astral-sh/uv), **Node 22+** with `npm`, and **SurrealDB v2**.

```bash
git clone https://github.com/Antman1526/open-notebook-Plus
cd open-notebook-Plus

# --- Backend ---
uv sync                          # creates .venv and installs Python deps
cp .env.example .env             # then fill in the values below

# --- Frontend ---
cd frontend && npm ci
cd ..
```

Run the three tiers (three terminals):

```bash
make database                    # terminal 1: SurrealDB (via docker-compose)
make api                         # terminal 2: FastAPI on :5055
make frontend                    # terminal 3: Next.js on :3000
```

Then open **http://localhost:3000**, enter your `OPEN_NOTEBOOK_PASSWORD` if you set one, create a notebook, upload a source, and start chatting.

> A self-host **Docker Compose** path also exists (`docker compose up -d`), exposing the legacy UI on `:8502`, the API on `:5055`, and metrics on `:5055/metrics`.

To build the macOS desktop app from source:

```bash
make build-mac      # test → lockfile → build venv → Next.js build →
                    # fetch runtimes → PyInstaller → hdiutil dmg
                    # Output: dist/Open Notebook Plus.app (+ .dmg, ~175 MB)
```

---

## Configuration

Configuration is supplied through **environment variables** (a `.env` file in development, copied from `.env.example`) and through an optional **`config.toml`** for non-secret application settings. Application data — the SurrealDB store, uploads, SQLite checkpoints, and the tiktoken cache — lives under the directory named by `DATA_FOLDER` (default `./data` in dev; a per-user app-data directory in the desktop build).

**Local models** are read from the model root `~/Desktop/AI_Models` on macOS by default. GGUF files live under `~/Desktop/AI_Models/GGUF/`; complete MLX repositories live under `~/Desktop/AI_Models/MLX/`; Ollama models are auto-detected from the running Ollama service. Encrypted cloud-provider credentials are added in-app under **Settings → Models** rather than via env vars.

The full reference lives in [`docs/5-CONFIGURATION/`](docs/5-CONFIGURATION/index.md). The minimum set (names only — never commit real secret values):

```bash
# --- SurrealDB ---
SURREAL_URL=ws://localhost:8000/rpc
SURREAL_USER=
SURREAL_PASSWORD=                 # change for any non-local deployment
SURREAL_NAMESPACE=open_notebook
SURREAL_DATABASE=production

# --- App auth & secret storage (required) ---
OPEN_NOTEBOOK_PASSWORD=           # UI password gate
OPEN_NOTEBOOK_ENCRYPTION_KEY=     # encrypts stored provider credentials
# OPEN_NOTEBOOK_ENCRYPTION_KEYS=  # comma-separated new,old for key rotation
# ONP_ENCRYPTION_KDF=pbkdf2       # optional: PBKDF2-HMAC-SHA256, 600k iter

# --- Data location ---
DATA_FOLDER=./data

# --- Optional: web search (opt-in by key presence) ---
SERPER_API_KEY=
TAVILY_API_KEY=
SEARXNG_BASE_URL=

# --- Optional: smart routing, privacy, memory, FSM (all default-off) ---
OPEN_NOTEBOOK_AUTO_ROUTE_CHAT=    # per-turn local/cloud routing
ONP_PRIVACY_GATE=                 # keep secrets/PII on-device
ONP_AGENT_FSM=                    # agent clarify/complete state machine
ONP_MEMORY_RECALL_MODE=           # recent | semantic | auto
ONP_MEMORY_KEEP_PER_TABLE=        # memory retention ceiling
ONP_MEMORY_BATCH_TURNS=
ONP_MEMORY_CONFIDENCE_FLOOR=

# --- Optional: offline / network behavior ---
ONP_NET_PROBE_HOSTS=
ONP_NETWORK_STATE_TTL_SEC=

# --- Optional: observability & maintenance ---
ONP_SLOW_QUERY_LOG_MS=500
ONP_CHECKPOINT_KEEP_PER_THREAD=50
ONP_CHECKPOINT_PRUNE_INTERVAL_HOURS=24

# --- Optional: podcast & prompt optimizer ---
ONP_PODCAST_MAX_CONTENT_TOKENS=100000
ONP_PROMPT_OPT_TIMEOUT_SEC=1800

# --- Optional: desktop auto-export ---
ONP_AUTO_EXPORT_HOURS=24
ONP_AUTO_EXPORT_KEEP=7
```

> **Never commit real secrets.** `.env` is gitignored; credentials entered in-app are stored encrypted in SurrealDB.

---

## Running tests

```bash
# Backend — hermetic unit/graph tests (no live services needed)
make test                         # or: uv run pytest tests/ --ignore=tests/integration

# Backend — SurrealDB integration tests (requires `make database` first)
make test-integration

# Frontend — Vitest
cd frontend && npm test
```

Current suites: **1712 backend tests + 195 frontend Vitest tests**, plus SurrealDB integration tests. CI runs them in [`.github/workflows/test.yml`](.github/workflows/test.yml). Desktop launcher behavior is covered separately under `desktop/tests/`.

---

## Reconstruction documentation

The full rebuild packet lives in [`docs/recreation/`](docs/recreation/). It is written for another AI or senior engineer to recreate the project without guessing:

- [`00-reconstruction-manifest.md`](docs/recreation/00-reconstruction-manifest.md) — index, scope, source-of-truth map, build artifacts, and verification gates.
- `01` through `15` — architecture, environment, data model, API, frontend, auth, business logic, integrations, config, tests, build/deploy, logging, performance, security, and file organization.
- [`project-deep-dive-for-ai-review.md`](docs/recreation/project-deep-dive-for-ai-review.md) — dense AI-review brief with real code snippets, known trade-offs, and Areas for Review.
- [`technology-inventory.md`](docs/recreation/technology-inventory.md) — exhaustive technology audit with each tool's specific role in this repo.

These files are mirrored into `/Users/Antman/Desktop/OpenNotebook` during local documentation exports so they can be loaded into Open Notebook Plus itself as source material.

---

## Project structure

```
open-notebook-Plus/
├── api/                      # FastAPI app
│   ├── main.py               # app factory, middleware, router registration
│   └── routers/              # notebooks, sources, notes, chat, search,
│                             #   podcasts, transformations, models,
│                             #   credentials, mcp, gmail, system, ...
├── open_notebook/            # backend core
│   ├── graphs/               # LangGraph workflows:
│   │   ├── source.py         #   ingestion: extract → embed → save
│   │   ├── chat.py           #   conversational agent + memory recall
│   │   ├── source_chat.py    #   per-source chat
│   │   ├── ask.py            #   retrieve-then-synthesize search
│   │   ├── transformation.py #   run prompt templates over sources
│   │   ├── agent_fsm.py      #   clarify/complete reliability FSM
│   │   └── tools.py          #   tool-loop wiring (MCP, web_search)
│   ├── domain/               # Pydantic domain models + repository layer
│   ├── database/             # SurrealDB pool, migrations, repo helpers
│   │   └── migrations/       # auto-applied .surrealql schema migrations
│   ├── ai/                   # Esperanto model layer, offline gate
│   ├── health/               # network-state + local-model health probes
│   ├── tools/                # web_search, add_web_source, opencode_run
│   ├── prompt_optimizer/     # SkillOpt adapter + runner + vendored prompts
│   ├── podcasts/             # podcast domain logic
│   ├── mcp/                  # MCP client integration
│   ├── digest/               # Gmail digest scheduling
│   └── config.py             # DATA_FOLDER, paths, app config
├── commands/                 # surreal_commands job handlers
│   ├── source_commands.py    #   ingestion jobs
│   ├── podcast_commands.py / podcast_staged.py   # podcast jobs
│   ├── embedding_commands.py
│   └── prompt_optimizer_commands.py
├── desktop/                  # native desktop launcher
│   ├── launcher.py           # supervises SurrealDB, API, Next.js, sidecars
│   ├── providers/            # llamacpp.py, ollama.py sidecar managers
│   ├── window.py / splash.py # pywebview shell + welcome splash handoff
│   ├── db_repair.py          # self-healing DB corruption repair
│   ├── build/                # PyInstaller spec, runtime fetchers, dmg
│   └── tests/                # launcher/desktop tests
├── frontend/                 # Next.js 16 + React 19 app
│   └── src/app/              # (auth) and (dashboard) route groups
├── deploy/searxng-private/   # ship-your-own localhost SearXNG
├── docs/                     # user & configuration documentation
├── prompts/                  # default prompt templates
├── tests/                    # backend test suite (+ tests/integration/)
├── pyproject.toml            # Python deps (managed by uv)
├── Makefile                  # database / api / frontend / test / build-mac
└── desktop/CHANGELOG.md      # Plus-fork release history
```

---

## Privacy & local-first stance

Open Notebook Plus is built so you can use a NotebookLM-class research tool **without sending your data to anyone**:

- **Your data stays on your drive.** Notebooks, sources, embeddings, chat history, and extracted memory live in *your* SurrealDB, behind *your* password and encryption key.
- **Fully local AI is a first-class path, not a fallback.** Bundled llama.cpp chat + embedding sidecars, a Whisper STT sidecar, and a Piper TTS sidecar mean ingestion, chat, search, memory, and even podcast audio can run with zero network calls. Cloud providers are opt-in.
- **Fail-closed privacy gate.** With `ONP_PRIVACY_GATE` enabled, turns that contain detected secrets or PII are kept **on the local model** (or blocked) instead of being sent to a cloud provider, surfaced by an interactive "On-device" review badge with an explicit **"Re-ask allowing cloud"** consent action.
- **Offline by choice or by circumstance.** Flip the Offline-mode toggle and the app runs fully local even when online; lose connectivity and cloud turns transparently fall back to local models instead of hanging.
- **Encrypted credentials.** Cloud API keys are stored encrypted (Fernet, with an optional PBKDF2-HMAC-SHA256 KDF and key rotation), never in plaintext.

---

## Contributing

Contributions are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines and [`CLAUDE.md`](CLAUDE.md) for the architectural conventions this codebase follows (async-first patterns, edge-table query direction, fire-and-forget command submission, SSE disconnect handling, delete cascades, and the per-commit changelog + inline-comment versioning convention). Component-level guidance lives in the nested `CLAUDE.md` files under `frontend/`, `api/`, and `open_notebook/`.

Before opening a PR, run `make test` and the frontend Vitest suite and add tests for any behavior change. Plus-fork issues go to the [Plus issue tracker](https://github.com/Antman1526/open-notebook-Plus/issues); upstream issues go to [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook/issues).

---

## License

Released under the **MIT License** — see [`LICENSE`](LICENSE). Same license as upstream.

---

## Acknowledgements

Open Notebook Plus is a downstream fork of [`lfnovo/open-notebook`](https://github.com/lfnovo/open-notebook); all upstream credit goes to [@lfnovo](https://github.com/lfnovo). The Plus delta — the native desktop launcher, local-AI sidecars, offline switching, staged podcasts, SkillOpt prompt optimizer, closed-loop memory, privacy gate, and the production-hardening run — is maintained by [@Antman1526](https://github.com/Antman1526). The prompt optimizer builds on Microsoft **SkillOpt** (MIT).
