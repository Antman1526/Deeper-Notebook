# Deeper Notebook

**Think further with every source.** Deeper Notebook is a privacy-first, fully-local-capable research notebook where you can upload multimodal sources, generate grounded notes and insights, chat with citations, search across your library, and produce podcasts and Course Packs with your choice of local or cloud AI. It is a substantially extended fork of [`lfnovo/open-notebook`](https://github.com/lfnovo/open-notebook), adding a native desktop launcher, bundled AI sidecars, offline/online smart switching, staged podcast generation, a SkillOpt prompt optimizer, closed-loop memory, a fail-closed cloud-privacy gate, Evidence Studio, and a downstream-friendly update strategy.

The product uses the approved **Notebook Spark** visual identity with the
teal-to-cyan **Research Core** colorway.

![Deeper Notebook desktop icon](desktop/resources/icon.png)

> **Current reconstruction snapshot:** this checkout contains the complete
> backend, frontend, native desktop wrapper, local-model sidecars, Obsidian /
> Logseq-compatible knowledge engine, research evidence receipts, podcast
> studio, and the 15-document rebuild packet. The current desktop build is
> `0.8.95`; the Python package track is `1.8.5`. Build and install receipts are
> generated locally and are never treated as a substitute for a signed public
> release.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![Python 3.12](https://img.shields.io/badge/Python-3.11%20|%203.12-blue)
![Next.js 16](https://img.shields.io/badge/Next.js-16-black)
![React 19](https://img.shields.io/badge/React-19-149eca)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136.3%2B-009688)
![LangGraph](https://img.shields.io/badge/LangGraph-1.0-ff6f00)
![SurrealDB v2](https://img.shields.io/badge/SurrealDB-v2-ff5722)
![Tests](https://img.shields.io/badge/tests-2033%20backend%20%2B%20477%20frontend-success)

> GitHub: **https://github.com/Antman1526/Deeper-Notebook** — a downstream fork of [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook).

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
- [Migrating from Open Notebook Plus](#migrating-from-open-notebook-plus)
- [Running tests](#running-tests)
- [Reconstruction documentation](#reconstruction-documentation)
- [Project structure](#project-structure)
- [Privacy & local-first stance](#privacy--local-first-stance)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## What it is

Deeper Notebook is a desktop application for **source-grounded AI research**. You organize your work into *notebooks*; into each notebook you drop *sources* (documents, audio, video, web URLs, pasted text). The app extracts and chunks the content, embeds it into a vector store, and from then on every interaction — chat answers, generated notes, "Ask" syntheses, podcast scripts — is grounded in *your* sources, with interactive citation pills that link each claim back to the document it came from.

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
- **Evidence Studio** turns a selected notebook, upload batch, link set, or mixed source bundle into reusable artifacts: reports, study guides, Course Packs, briefings, FAQs, timelines, flashcards, quizzes, data tables, mind maps, editable slide decks, rendered infographics, podcast outlines, and research runs.
- **Validated artifact documents:** newly generated text artifacts are model-independent, versioned Pydantic documents rather than unverified free-form Markdown. Provider-native structured output is preferred; local and other plain-chat models receive the exact JSON Schema and get at most one bounded repair attempt when their first response is invalid. The server deterministically renders the validated document to Markdown for the current viewers and exports.
- **Backward-compatible storage:** each new `output_payload` stores `schema_version`, the typed `document`, canonical `markdown`, the legacy `content` alias, and a compact validation receipt. Existing `{content: markdown}` artifacts continue to open, revise, export, and retain study progress without a migration. Structured PATCH edits are revalidated and re-rendered server-side so stale client Markdown cannot disagree with the document.
- **Visual deliverables:** completed slide decks save an editable 16:9 `.pptx` plus a deterministic multipage `.pdf`; completed infographics save a `.png` plus a one-page `.pdf` in portrait, landscape, or square orientation. The PPTX keeps titles, bullets, speaker notes, visual direction, and citation markers as editable content. Visual files appear beside Markdown and JSON in the artifact viewer and are refreshed after a valid structured edit.
- **Local Video Overview:** pair a completed Evidence Studio slide deck with a completed, timestamped Audio Overview to make a captioned 1920x1080 `.mp4`. The app re-renders the reviewed slide document locally, composes it with bundled FFmpeg, verifies the result before promotion, saves `.mp4` and `.vtt` beneath the app data folder, and streams them only through path-contained API routes. It never sends slides, narration, or captions to a hosted video service.
- **Local, failure-isolated exports:** artifacts save beneath `~/BrainPulseKnowledge/deeper-notebook-imports/evidence-studio/` by default, or `DEEPER_NOTEBOOK_ARTIFACT_EXPORT_DIR` when set. The old export-path variable remains accepted during migration. Rendering uses local Python libraries only, with no hosted office or image service.
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
- **Self-healing database:** detects SurrealDB live-query corruption after an unclean shutdown and runs a backup-first auto-repair on the next launch. A **"Repair & restart"** button relaunches the app through the desktop bridge so the boot-time repair runs without a manual quit-and-reopen.

### NotebookLM-parity research UX (v0.8.x)
A focused improvement cycle (benchmarked against Google NotebookLM and local-first rivals) added, verified, and shipped the following — each behind automated gates (backend pytest + `tsc` + `npm run build`), several confirmed live in the packaged app:

- **Citation jump-to-highlight** — clicking a `[source]` citation opens the source reading pane and scrolls to and highlights the exact grounding passage (on-demand token-containment offset matching via `deeper_notebook/utils/citation_offsets.py`; `POST /sources/{id}/locate-passage`), turning citations from "reference" into "verify in one click."
- **Inline PDF rendering** — PDF sources render inline (react-pdf 10) with a **locally-bundled, offline pdfjs worker** (no CDN) and a graceful fall-back to extracted text.
- **Interactive mind map** — a React Flow (`@xyflow/react`) radial graph of the notebook hub + its sources and notes, grounded in the existing `reference`/`artifact` edges (no schema change; `GET /notebooks/{id}/graph`); clicking a source node opens it.
- **Discover sources** — an opt-in, privacy-preserving web-search-to-source dialog in the Sources panel: type a topic → review candidate URLs → add chosen results as link sources. Search only reaches the network when a provider key (`SERPER`/`TAVILY`/`SEARXNG`) is configured; otherwise the dialog shows a setup hint.
- **Resizable 3-pane workspace** — draggable `sources │ notes │ chat` panes with widths remembered across sessions (shadcn `resizable` on `react-resizable-panels@2`), preserving the per-column collapse toggles.
- **Podcast depth** — a per-episode **Length** selector (short / medium / long → segment-count override) in the Generate dialog, alongside the existing focus/instructions field.
- **Opt-in source enrichment on ingest** — Settings → Sources toggles (both default OFF) to **auto-summarize** a source (a Summary insight + one-line card preview) and **extract key topics** (parsed into the source's `topics` tags) when it's added, each reusing the existing transform→insight pipeline.
- **Per-source chat filtering + context transparency** — the off/insights/full source toggles already scope the chat context; the chat bar now shows **"Using X of Y sources"** with a popover listing the in-context sources.
- **First-run onboarding** — a one-click **"Explore a sample notebook"** seeds an example notebook + source so first use shows value instead of a blank screen; corpus-grounded **suggested questions** greet an empty chat.
- **Source-grounding guardrail** — chat/ask prompts instruct the model to answer only from the provided sources (or say so plainly), and the Ask workflow declares CLARIFY rather than emit an ungrounded synthesis.
- **Accessibility & theming** — ARIA labels on icon-only controls, Radix-managed dialog focus-trap/restore, 17 WCAG-AA/AAA themes with theme-aware aurora visuals, list virtualization, and rAF-batched streaming for a smoother WKWebView experience.

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

Deeper Notebook is a **three-tier application** (frontend / API / database) plus, in the desktop build, a **launcher** that supervises a set of **local AI sidecar processes**.

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

**API (`api/` + `deeper_notebook/`)** — A FastAPI app exposing REST routers for notebooks, sources, notes, chat, ask/search, podcasts, transformations, models, credentials, MCP, Gmail digests, and system/health. Conversational and ingestion logic is orchestrated by **LangGraph** state machines. Evidence Studio uses strict Pydantic document schemas, a provider-neutral structured-generation adapter, deterministic Markdown and visual renderers, and a backward-compatible payload envelope under `deeper_notebook/studio/`; `python-pptx` writes editable decks and Pillow writes self-contained slide/infographic PDF and PNG files. Long-running work is dispatched to an async **surreal_commands** job queue and polled through the commands API.

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

**5. Generate an Evidence Studio artifact**
```
Selected ready sources → citation-marked context + artifact schema
  → provider-native structured output, or JSON Schema fallback
  → validate response → [one bounded repair when invalid] → fail closed
  → deterministic Markdown renderer
  → save v1 document + Markdown/content alias + validation receipt
  → write Markdown/JSON and artifact-specific sidecar exports
      slide_deck: editable PPTX + multipage PDF
      infographic: PNG + one-page PDF
  → valid structured edits retain a revision and refresh every export
```

---

## Installation

### Desktop app (macOS `.dmg`)

The recommended way to run Deeper Notebook is the native app—no Docker, no terminal, with all AI sidecars bundled.

1. Download `Deeper-Notebook-mac-<arch>.dmg` from [Releases](https://github.com/Antman1526/Deeper-Notebook/releases).
2. Drag **Deeper Notebook** into **Applications**.
3. The build is unsigned, so the first launch needs **Right-click → Open** to clear macOS Gatekeeper.
4. On first run the app boots its bundled SurrealDB + Node runtime, downloads the local model files it needs, and opens on a welcome splash before handing off to the main UI.

> **Windows:** desktop builds are produced on a Windows host because PyInstaller is not a cross-compiler. Releases provide `Deeper-Notebook-windows-x64.zip` with `Deeper Notebook.exe`, plus `Deeper-Notebook-Setup-x64.exe`.

### From source (development)

Requirements: **Python 3.12**, [`uv`](https://github.com/astral-sh/uv), **Node 22+** with `npm`, and **SurrealDB v2**.

```bash
git clone https://github.com/Antman1526/Deeper-Notebook.git
cd Deeper-Notebook

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

Then open **http://localhost:3000**, enter your `DEEPER_NOTEBOOK_PASSWORD` if you set one, create a notebook, upload a source, and start chatting.

> A self-host **Docker Compose** path also exists (`docker compose up -d`), exposing the legacy UI on `:8502`, the API on `:5055`, and metrics on `:5055/metrics`.

To build the macOS desktop app from source:

```bash
make build-mac      # test → lockfile → build venv → Next.js build →
                    # fetch runtimes → PyInstaller → hdiutil dmg
                    # Outputs: dist/Deeper Notebook.app
                    #          dist/Deeper-Notebook-mac-<arch>.dmg
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
DEEPER_NOTEBOOK_PASSWORD=           # UI password gate
DEEPER_NOTEBOOK_ENCRYPTION_KEY=     # encrypts stored provider credentials
# DEEPER_NOTEBOOK_ENCRYPTION_KEYS=  # comma-separated new,old for key rotation
# DN_ENCRYPTION_KDF=pbkdf2           # optional short canonical alias

# --- Data location ---
DATA_FOLDER=./data

# --- Optional: web search (opt-in by key presence) ---
SERPER_API_KEY=
TAVILY_API_KEY=
SEARXNG_BASE_URL=

# --- Optional: smart routing, privacy, memory, FSM (all default-off) ---
DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT=  # per-turn local/cloud routing
DN_PRIVACY_GATE=                 # keep secrets/PII on-device
DN_AGENT_FSM=                    # agent clarify/complete state machine
DN_MEMORY_RECALL_MODE=           # recent | semantic | auto
DN_MEMORY_KEEP_PER_TABLE=        # memory retention ceiling
DN_MEMORY_BATCH_TURNS=
DN_MEMORY_CONFIDENCE_FLOOR=

# --- Optional: offline / network behavior ---
DN_NET_PROBE_HOSTS=
DN_NETWORK_STATE_TTL_SEC=

# --- Optional: observability & maintenance ---
DN_SLOW_QUERY_LOG_MS=500
DN_CHECKPOINT_KEEP_PER_THREAD=50
DN_CHECKPOINT_PRUNE_INTERVAL_HOURS=24

# --- Optional: podcast & prompt optimizer ---
DN_PODCAST_MAX_CONTENT_TOKENS=100000
DN_PROMPT_OPT_TIMEOUT_SEC=1800

# --- Optional: desktop auto-export ---
DN_AUTO_EXPORT_HOURS=24
DN_AUTO_EXPORT_KEEP=7
```

> **Never commit real secrets.** `.env` is gitignored; credentials entered in-app are stored encrypted in SurrealDB.

---

## Migrating from Open Notebook Plus

Existing installations remain supported while Deeper Notebook becomes the
canonical identity:

| Setting | Canonical | Legacy compatibility |
|---|---|---|
| Long environment prefix | `DEEPER_NOTEBOOK_*` | `OPEN_NOTEBOOK_*` |
| Short environment prefix | `DN_*` | `ONP_*` |
| macOS/Linux data directory | `~/.deeper-notebook/` | `~/.open-notebook-plus/` |
| Windows data directory | `%USERPROFILE%\.deeper-notebook` | `%USERPROFILE%\.open-notebook-plus` |

Canonical variables win when both canonical and legacy names are set:
`DEEPER_NOTEBOOK_*` → `DN_*` → `OPEN_NOTEBOOK_*` → `ONP_*`. Legacy variables
remain readable and produce a deprecation notice that identifies only the
variable name, never its value.

Fresh profiles use the canonical data directory. A legacy-only profile is
migrated only through the guarded receipt-and-validation flow. If both
directories exist with different state, the app enters recovery mode and does
not merge or write either directory automatically. Keep the legacy directory
until the migration receipt and before/after hashes have been verified.

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

Current suites include backend, desktop-launcher, and frontend Vitest coverage, plus opt-in SurrealDB integration tests. Desktop packaging runs the launcher suite, all non-integration backend files through a bounded cross-platform batch runner, and frontend lint/build before packaging. CI runs them in [`.github/workflows/test.yml`](.github/workflows/test.yml); the release runner is [`desktop/build/run_backend_tests.py`](desktop/build/run_backend_tests.py).

---

## Reconstruction documentation

The full rebuild packet lives in [`docs/recreation/`](docs/recreation/). It is written for another AI or a senior engineer to recreate the project from scratch without guessing — real code snippets, exact versions, config specs, and step-by-step instructions:

- **`01`–`15`** — (1) project overview & architecture, (2) environment setup & dependencies, (3) database schema & data models, (4) backend API specifications, (5) frontend architecture & components, (6) authentication & authorization, (7) business logic & core algorithms, (8) integration points & external services, (9) configuration & environment variables, (10) testing strategy & test cases, (11) build & deployment pipeline, (12) error handling & logging, (13) performance optimization & caching, (14) security implementation, (15) file structure & code organization.
- [`PROJECT-DEEP-DIVE.md`](docs/recreation/PROJECT-DEEP-DIVE.md) — a dense AI-review brief: key code walkthrough, data flow, pain points, design trade-offs, and an **"Areas for Review"** prompt for an AI reviewer.
- [`TECHNOLOGY-AUDIT.md`](docs/recreation/TECHNOLOGY-AUDIT.md) — an exhaustive technology inventory with each tool's specific role in this repo.

These files can also be loaded into Deeper Notebook as source material.

For current checkout metadata, the document-to-source map, sanitized artifact
inventory, and explicit uncertainty notes, see
[`docs/recreation/README.md`](docs/recreation/README.md).

---

## Project structure

```
Deeper-Notebook/
├── api/                      # FastAPI app
│   ├── main.py               # app factory, middleware, router registration
│   └── routers/              # notebooks, sources, notes, chat, search,
│                             #   podcasts, transformations, models,
│                             #   credentials, mcp, gmail, system, ...
├── deeper_notebook/          # canonical backend core
├── open_notebook/            # deprecated import-compatibility shim
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
│   ├── studio/               # typed artifact schemas, payload envelope,
│   │                         #   structured generation, renderers, exports
│   │   └── exporters/        #   PPTX/PDF/PNG visual artifact writers
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
└── desktop/CHANGELOG.md      # historical downstream release record
```

---

## Privacy & local-first stance

Deeper Notebook is built so you can use a NotebookLM-class research tool **without sending your data to anyone**:

- **Your data stays on your drive.** Notebooks, sources, embeddings, chat history, and extracted memory live in *your* SurrealDB, behind *your* password and encryption key.
- **Fully local AI is a first-class path, not a fallback.** Bundled llama.cpp chat + embedding sidecars, a Whisper STT sidecar, and a Piper TTS sidecar mean ingestion, chat, search, memory, and even podcast audio can run with zero network calls. Cloud providers are opt-in.
- **Fail-closed privacy gate.** With `DN_PRIVACY_GATE` enabled, turns that contain detected secrets or PII are kept **on the local model** (or blocked) instead of being sent to a cloud provider, surfaced by an interactive "On-device" review badge with an explicit **"Re-ask allowing cloud"** consent action.
- **Offline by choice or by circumstance.** Flip the Offline-mode toggle and the app runs fully local even when online; lose connectivity and cloud turns transparently fall back to local models instead of hanging.
- **Encrypted credentials.** Cloud API keys are stored encrypted (Fernet, with an optional PBKDF2-HMAC-SHA256 KDF and key rotation), never in plaintext.

---

## Contributing

Contributions are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines and [`CLAUDE.md`](CLAUDE.md) for the architectural conventions this codebase follows. Component-level guidance lives in the nested `CLAUDE.md` files under `frontend/`, `api/`, and `deeper_notebook/`.

Before opening a PR, run `make test` and the frontend Vitest suite and add tests for any behavior change. Deeper Notebook issues go to the [downstream issue tracker](https://github.com/Antman1526/Deeper-Notebook/issues); upstream issues go to [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook/issues).

---

## License

Released under the **MIT License** — see [`LICENSE`](LICENSE). Same license as upstream.

---

## Acknowledgements

Deeper Notebook is a downstream fork of [`lfnovo/open-notebook`](https://github.com/lfnovo/open-notebook); all upstream credit goes to [@lfnovo](https://github.com/lfnovo). The downstream native desktop, local-AI, privacy, memory, and research-workspace extensions are maintained by [@Antman1526](https://github.com/Antman1526). The prompt optimizer builds on Microsoft **SkillOpt** (MIT).
