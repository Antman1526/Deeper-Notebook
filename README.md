# Open Notebook Plus

A desktop-app fork of [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook) focused on **local-first AI research notebooks** with a closed-loop memory layer, end-to-end source ingestion + chat + podcast generation, and **70+ production-hardening fixes** on top of upstream.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![Python 3.11+ / 3.12](https://img.shields.io/badge/Python-3.11%20|%203.12-blue)
![Node 22](https://img.shields.io/badge/Node-22-green)
![Next.js 16](https://img.shields.io/badge/Next.js-16-black)
![FastAPI 0.104+](https://img.shields.io/badge/FastAPI-0.104%2B-009688)
![SurrealDB](https://img.shields.io/badge/SurrealDB-1.x-ff5722)

---

## What it does

Upload PDFs, audio, video, web pages, or text. Take notes. Chat with AI grounded in your sources. Run multi-step "Ask" synthesis across your library. Generate multi-speaker podcasts. **Memory** — facts and preferences automatically extracted from each chat persist across sessions. Everything runs locally if you want it to.

## What's different from upstream

- **Native desktop app** — Mac `.dmg` (Windows on the roadmap). No Docker, no terminal.
- **Bundled SurrealDB + Node.js runtime** — single .app, no separate installs.
- **Local-model-first** — bundled `llama-cpp-python` + Ollama auto-detect. Cloud APIs are opt-in.
- **Closed-loop memory** — per-turn facts written to mem0/SurrealDB, recalled in the system prompt of every future chat. Auto-switches between recency and semantic search at ~30 rows.
- **Production hardening (v0.7.49 → v0.7.119)** — 70+ fixes across streaming cancellation, SSE disconnect handling, connection-pool race correctness, delete cascades, event-loop unblocking, encryption rotation, local-LLM resilience, **end-to-end timeout coverage** on every async LLM/embed/DB call, **XSS hardening** in HTML exports, **`/healthz/deep`** per-subsystem probe.

## Three-tier architecture

```
+--------------------------------------------------------+
|  Frontend  Next.js 16 + React 19 + TypeScript :3000    |
|  Zustand state, TanStack Query 5, Shadcn/ui + Tailwind |
+-----------------------+--------------------------------+
                        |  HTTP REST + NDJSON + SSE streams
+-----------------------v--------------------------------+
|  API       FastAPI 0.104 + Python 3.12 :5055           |
|  LangGraph 1.0 workflows, Esperanto 14-provider model  |
|  layer, surreal_commands job queue, Pydantic v2        |
+-----------------------+--------------------------------+
                        |  SurrealQL (AsyncSurreal pool)
+-----------------------v--------------------------------+
|  Database  SurrealDB 1.x :8000                         |
|  Graph + vector + JSON + KV in one engine              |
|  HNSW indexes; native vector::similarity::cosine       |
+--------------------------------------------------------+

Desktop bundle additionally spawns:
  llama-cpp-python embed server (nomic-embed-text-v1.5)
  llama-cpp-python chat server  (Hermes-3 / Qwen2.5-Instruct)
  Whisper STT, Piper TTS, mem0 memory_shim, surreal_commands worker
```

## Install

### macOS (desktop app)

1. Download the `.dmg` from [Releases](https://github.com/Antman1526/open-notebook-Plus/releases)
2. Drag the app to **Applications**
3. **Right-click → Open** the first time (unsigned build; macOS Gatekeeper)

### Self-host (Docker Compose)

```bash
git clone https://github.com/Antman1526/open-notebook-Plus
cd open-notebook-Plus
cp .env.template .env                    # fill in passwords + encryption key
docker compose --profile multi up -d
# UI: http://localhost:3000, API: http://localhost:5055
```

### Local development

```bash
git clone https://github.com/Antman1526/open-notebook-Plus
cd open-notebook-Plus

# Backend
uv sync                                  # creates .venv via uv
cp .env.template .env                    # set SURREAL_*, OPEN_NOTEBOOK_PASSWORD, ENCRYPTION_KEY

# Frontend
cd frontend && pnpm install && cd ..

# Run (3 terminals)
make surreal                              # terminal 1: SurrealDB
make api                                  # terminal 2: FastAPI :5055
make frontend                             # terminal 3: Next.js :3000
```

Run the test suite:

```bash
uv run pytest tests/ -q                       # 430 backend tests
cd frontend && pnpm test --run                # 35 frontend tests
uv run pytest desktop/tests/test_launcher.py  # 14 launcher tests
```

## First run

1. Open the app — the main UI launches at `http://localhost:3000`
2. Enter the password set in `OPEN_NOTEBOOK_PASSWORD` (if you set one)
3. Create a notebook, upload a source, chat about it
4. Visit Settings → Models to configure cloud providers (or use the bundled local models)

## Adding more local models

- Drop any `.gguf` file into `~/Desktop/AI_Models/GGUF/` — it appears in the picker on next launch.
- `ollama pull <name>` — Ollama-installed models show up under the Ollama section.

## Configuration

All env vars documented in [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) and in the dedicated [doc 09](https://github.com/Antman1526/open-notebook-Plus/blob/desktop-app/desktop/CHANGELOG.md). Critical minimum:

```bash
SURREAL_URL=ws://localhost:8000/rpc
SURREAL_USER=root
SURREAL_PASSWORD=root                            # CHANGE in production
SURREAL_NAMESPACE=open_notebook
SURREAL_DATABASE=production
OPEN_NOTEBOOK_PASSWORD=open-notebook-change-me   # CHANGE
OPEN_NOTEBOOK_ENCRYPTION_KEY=any-passphrase      # required to store credentials
# OR rotation form:
# OPEN_NOTEBOOK_ENCRYPTION_KEYS=new-key,old-key
```

## Memory feature

The full memory loop is on by default in the desktop build:

```
Turn N completes
  → /chat/stream fires memory_extract_turn (fire-and-forget)
  → worker invokes Hermes-3 to parse facts/preferences
  → mem0 SurrealMemoryStore writes memory_fact / memory_preference

Turn N+1 starts
  → chat_graph calls recall_memory(query=last_user_message)
  → orchestrator picks recency (<30 rows) or semantic (vector::similarity::cosine)
  → renders into "# WHAT YOU REMEMBER ABOUT THE USER" section of system prompt

User deletes session
  → DELETE /chat/sessions/{id} fires memory_summarize_session BEFORE delete
  → writer produces one memory_episode record from the transcript
```

Configure via `ONP_MEMORY_RECALL_MODE = recent | semantic | auto`.

## Building from source

```bash
make build-mac-test                              # ~30 min first build
open "dist/Open Notebook Plus.app"
```

For a signed + notarized macOS build:

```bash
make build-mac
```

## Documentation

| Doc | Where |
|---|---|
| User documentation | [`docs/`](docs/) |
| Backend architecture | [`open_notebook/CLAUDE.md`](open_notebook/CLAUDE.md) |
| Frontend architecture | [`frontend/src/CLAUDE.md`](frontend/src/CLAUDE.md) |
| API structure | [`api/CLAUDE.md`](api/CLAUDE.md) |
| Domain models | [`open_notebook/domain/CLAUDE.md`](open_notebook/domain/CLAUDE.md) |
| LangGraph workflows | [`open_notebook/graphs/CLAUDE.md`](open_notebook/graphs/CLAUDE.md) |
| AI / Esperanto integration | [`open_notebook/ai/CLAUDE.md`](open_notebook/ai/CLAUDE.md) |
| Database layer | [`open_notebook/database/CLAUDE.md`](open_notebook/database/CLAUDE.md) |
| Release notes | [`desktop/CHANGELOG.md`](desktop/CHANGELOG.md) |
| Standing AI-agent workflow | [`CLAUDE.md`](CLAUDE.md) |

## Hardening Summary (v0.7.49 → v0.7.114)

70+ fix commits across the hardening run. v0.7.49–v0.7.87 covered the
original reliability sweep; v0.7.88+ added structured outputs,
filesystem I/O, and end-to-end timeout coverage.

**v0.7.88 → v0.7.114 highlights:**

- **Studio multi-page notebooks** (v0.7.89) — uploads produce an
  overview + N pages with inline AI suggestions per page, instead of
  one blob. Outline-pass + per-page generation with sequential
  (default) or parallel (`ONP_STUDIO_NOTEBOOK_PARALLEL_PAGES=true`)
  execution.
- **Studio `mode="both"`** (v0.7.88) — single upload generates BOTH
  notebook AND podcast in one shot. Either half can fail independently.
- **Filesystem export + import** (v0.7.90, v0.7.94, v0.7.96, v0.7.111)
  — notebooks save out as folder / zip / single-file (markdown OR
  HTML, with print CSS) and reload back via import endpoint with
  dry-run preview. `/api/fs/{home,list,mkdir}` endpoints back the
  directory picker UI. Frontend Export UI ships in v0.7.105.
- **End-to-end timeout coverage** (v0.7.93, v0.7.95, v0.7.99, v0.7.100,
  v0.7.101, v0.7.102, v0.7.110, v0.7.113, v0.7.114) — every async
  LLM/embed/DB call on a user-facing path is wrapped with
  `asyncio.wait_for`. Timeout returns either 504 with actionable
  detail OR graceful fallback (e.g. memory recall → recency
  fallback). Thirteen env knobs let operators tune per provider.
- **`HTTPException` clobber fix** (v0.7.109) — 25 functions across 13
  router files were silently rewrapping typed 400/404/504/etc as
  generic 500. 89 `except HTTPException: raise` guards added — typed
  errors now reach the client.
- **Bulk operations** (v0.7.106, v0.7.110) — bulk source vectorize
  endpoint (capped at 500/call) for recovering from import-time
  vectorize failures or after switching embedding models.
- **Deep healthcheck** (v0.7.112) — `/healthz/deep` probes DB,
  migrations, embedding model, chat model, command registry
  independently. Returns `healthy` / `degraded` / `not_ready` with
  actionable per-subsystem messages.
- **Import vectorize bug** (v0.7.104) — imported sources weren't
  getting embeddings (`Source.save()` doesn't auto-embed). Real
  regression-class bug that broke "import then chat-with-sources".
- **Loguru `%s` format fix** (v0.7.91) — 18 occurrences across 8
  files were logging literal `%s` since v0.7.0.

**v0.7.49 → v0.7.87 (earlier sweep):**

- **Streaming hooks** — UTF-8 cross-read buffering, per-send UUID temp IDs, AbortController + reader.cancel(), exact-id error filtering (chat, source-chat, ask)
- **SSE endpoints** — `is_disconnected()` per tick, dict-vs-Pydantic state-shape dual-path guards (4 endpoints)
- **Event-loop unblocking** — 14 sync `submit_command` sites wrapped in `asyncio.to_thread`
- **Connection pool** — warm-up timeout, `_pool_total` lock discipline on both acquire/release, graceful shutdown drain
- **Delete cascades** — Notebook → chat_session, Source → reference + embeddings + insights, Note → artifact + note_embedding, Model → default_models references
- **Memory feature** — wired write (extract + summarize) + recall (recency + semantic) end-to-end. Was dead code before v0.7.68.
- **Local-LLM resilience** — per-message char cap, classifier rules for "model still loading", launcher warnings for missing GGUF
- **Edge-table query correctness** — inverted idempotency check fixed (v0.7.60); retry endpoint dead-query fixed (v0.7.60); legacy duplicate cleanup (v0.7.85)
- **Frontend lifecycle** — all setTimeout/setInterval sites tracked with refs + unmount cleanup; insight-poll AbortSignal
- **Encryption rotation parity** — both `OPEN_NOTEBOOK_ENCRYPTION_KEY` and `OPEN_NOTEBOOK_ENCRYPTION_KEYS` accepted
- **Commands router** — three stub implementations replaced with real impls (v0.7.87)

See [`desktop/CHANGELOG.md`](desktop/CHANGELOG.md) for the full per-version log.

## API surface (post-v0.7.114)

| Endpoint | Method | What it does |
|---|---|---|
| `/api/studio/generate` | POST | Upload + generate notebook / podcast / both (multi-page, multi-file) |
| `/api/notebooks/{id}/export` | POST | Export notebook as `folder` / `zip` / `html_folder` / `html_zip` / `combined_md` / `combined_html` (with optional compression) |
| `/api/notes/{id}/export` | POST | Export a single note as `.md` |
| `/api/notebooks/import` | POST | Reverse of export — folder / zip / single-md → new or existing notebook |
| `/api/notebooks/import/preview` | POST | Dry-run import: show planned imports without committing |
| `/api/notebooks/{id}/vectorize_sources` | POST | Bulk re-embed sources after import-time failure or embedding-model swap |
| `/api/fs/home` | GET | User home + Desktop / Documents / Downloads / default-exports paths |
| `/api/fs/list` | GET | Directory listing (dirs first, capped at 500, hidden excluded by default) |
| `/api/fs/mkdir` | POST | Idempotent `mkdir -p` with path safety |
| `/healthz/deep` | GET | Per-subsystem probe (DB, migrations, embedding model, chat model, worker) — auth-exempt |

## Configurable timeouts + caps (`ONP_*` env vars)

| Env var | Default | What it bounds |
|---|---:|---|
| `ONP_STUDIO_OUTLINE_TIMEOUT_SEC` | 90 | Studio outline LLM call |
| `ONP_STUDIO_PAGE_TIMEOUT_SEC` | 180 | Studio per-page LLM call |
| `ONP_STUDIO_EXTRACT_TIMEOUT_SEC` | 60 | content_core file extraction per file |
| `ONP_STUDIO_NOTEBOOK_PARALLEL_PAGES` | false | Run page LLM calls concurrently (cloud opt-in) |
| `ONP_STUDIO_NOTEBOOK_PAGES_MAX` | 6 | Hard cap on multi-page count |
| `ONP_STUDIO_NOTEBOOK_MULTIPAGE` | true | Kill switch back to single-note |
| `ONP_NOTE_TITLE_TIMEOUT_SEC` | 60 | Auto-title LLM call on `POST /notes` |
| `ONP_TRANSFORMATION_TIMEOUT_SEC` | 180 | Per-transformation LLM call |
| `ONP_CHAT_TIMEOUT_SEC` | 300 | Non-streaming `/chat/execute` |
| `ONP_CONNECTION_TEST_TIMEOUT_SEC` | 30 | "Test connection" button in Settings |
| `ONP_DISCOVER_MODELS_TIMEOUT_SEC` | 30 | Provider model-discovery (paginated list) |
| `ONP_SEARCH_TIMEOUT_SEC` | 60 | `/search` text + vector queries |
| `ONP_BULK_VECTORIZE_MAX_SOURCES` | 500 | Per-request cap on bulk vectorize |
| `ONP_MEMORY_RECALL_EMBED_TIMEOUT_SEC` | 5 | Chat-hot-path semantic recall embed |
| `ONP_MEMORY_RECALL_QUERY_TIMEOUT_SEC` | 5 | Chat-hot-path memory SurrealQL queries |

## Testing

| Suite | Count | Runtime |
|---|---:|---:|
| Backend (pytest) | **534** | ~25 s |
| Frontend (vitest) | **58** | ~30 s |
| Desktop launcher | **14** | ~7 s |

All pass at HEAD. ruff is clean across `api/`, `open_notebook/`, `commands/`, `desktop/`, `tests/`.

## Contributing

PRs welcome. Standing workflow for AI agents is documented in [`CLAUDE.md`](CLAUDE.md): on every prompt, audit relevant code for bugs first, fix what you find, apply judgment-bound improvements, report bugs/fixes/improvements/deferred items.

For human contributors: ruff + pytest must pass locally before pushing. CHANGELOG entry expected for non-trivial changes.

## Credits

Forked from [`lfnovo/open-notebook`](https://github.com/lfnovo/open-notebook) (MIT). Upstream README preserved at [`README.upstream.md`](README.upstream.md). All "Plus" wrapper / hardening code lives in `desktop/`, `api/`, `open_notebook/`, `commands/`, and the v0.7.x CHANGELOG entries.

## License

MIT — see [LICENSE](LICENSE).
