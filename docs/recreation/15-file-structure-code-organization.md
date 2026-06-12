# 15. File Structure & Code Organization

Exhaustive map of how **Open Notebook Plus** is laid out, what each module owns,
how modules depend on one another, and the two house conventions that hold it
together: **a `CLAUDE.md` in every module** and **version-stamped inline
comments** (`# v0.8.NN — ...`).

> **Version baseline**: app `v1.8.5` (`pyproject.toml`). Three-tier:
> FastAPI (`api/` @ 5055) + LangGraph/domain (`open_notebook/`) + SurrealDB
> (@ 8000), with a Next.js 16 frontend (`frontend/` @ 3000) and a native
> PyObjC/aiohttp desktop launcher (`desktop/`).

The tree below was produced with `find` / `ls` (excluding `node_modules`,
`.venv*`, `.build-venv`, `dist`, `build`, `__pycache__`).

---

## 15.1 Repository Root

```
open-notebook-Plus/
├── api/                     # FastAPI app: routers + the 4 real services + middleware
├── open_notebook/           # Backend core: domain, AI, graphs, database, utils, ...
├── frontend/                # Next.js 16 / React 19 UI (TanStack Query + Zustand)
├── desktop/                 # Native macOS/Windows launcher (PyObjC + aiohttp webview)
├── commands/                # surreal_commands async job handlers (embeddings, podcasts, ...)
├── tests/                   # 204 pytest files + tests/integration/ (live-SurrealDB)
├── prompts/                 # AI-Prompter / Jinja2 prompt templates
├── scripts/                 # ralph.sh, backup_restore.py, benchmark_models.py, export_docs.py, ...
├── docs/                    # User + recreation documentation (this file lives in docs/recreation/)
├── examples/                # Example configs / sample content
├── deploy/                  # Deployment assets
├── data/                    # Runtime data folder (sqlite-db/, uploads/, tiktoken-cache/) — gitignored
├── build/  dist/            # PyInstaller build + .dmg output — gitignored
│
├── pyproject.toml           # Python deps + version (1.8.5); uv.lock pins them
├── Makefile                 # 23KB task runner (build, test, docker, dmg, ...)
├── Dockerfile / Dockerfile.single   # multi-service + single-container images
├── docker-compose.yml       # SurrealDB + API + frontend stack
├── supervisord*.conf        # process supervision for the container images
├── run_api.py               # uvicorn entrypoint for the API
├── dev-init.sh              # local dev bootstrap
├── mypy.ini / .pre-commit-config.yaml / .ruff_cache   # type + lint config
├── CLAUDE.md                # root architectural guide + Standing Workflow
├── CHANGELOG.md / README.md / README.dev.md / README.upstream.md
├── CONFIGURATION.md / CONTRIBUTING.md / MAINTAINER_GUIDE.md / MEMORY.md
└── .env / .env.example      # env config (.env is gitignored; contains secrets)
```

Top-level docs of note: `README.upstream.md` preserves the original
`lfnovo/open-notebook` README; `README.md` is the Plus fork's. `MEMORY.md` is the
project's long-form engineering log.

---

## 15.2 `open_notebook/` — Backend Core

The heart of the application: domain models, AI provisioning, LangGraph
workflows, the SurrealDB layer, and cross-cutting utilities.

```
open_notebook/
├── CLAUDE.md                # backend architecture overview
├── __init__.py
├── config.py                # DATA_FOLDER, sqlite checkpoint path, uploads, tiktoken cache
├── exceptions.py            # OpenNotebookError hierarchy (Auth/Config/RateLimit/Network/...)
├── logging.py               # loguru configure_logging("api"/"worker")
│
├── ai/                      # Model lifecycle + provisioning + routing  (CLAUDE.md)
│   ├── models.py            #   Model / DefaultModels records + ModelManager factory
│   ├── provision.py         #   provision_langchain_model (105k-token upgrade) + auto-route wrapper
│   ├── router.py            #   pick_provider() pure local-vs-cloud router (ModelChoice)
│   ├── offline_gate.py      #   gate_language_model_id — offline → local substitution (v0.8.68)
│   ├── privacy_gate.py      #   fail-closed structured-secret detector (Phase 5.2a)
│   ├── privacy_classifier.py#   local PII classifier scaffolding (Phase 5.2b)
│   ├── key_provider.py      #   DB-credential → env-var provisioning for Esperanto
│   ├── connection_tester.py #   /credentials/.../test minimal-call validation (TEST_MODELS)
│   └── model_discovery.py   #   list a provider's available models
│
├── domain/                  # Pydantic data models + repository persistence  (CLAUDE.md)
│   ├── base.py              #   ObjectModel / RecordModel base classes (get/save/delete)
│   ├── notebook.py          #   Notebook, Source, Note, SourceInsight, ChatSession + vector_search
│   ├── credential.py        #   Credential record (Fernet-encrypted api_key)
│   ├── provider_config.py   #   legacy ProviderConfig (SecretStr api_key)
│   ├── content_settings.py  #   ContentSettings singleton (incl. offline_mode toggle)
│   ├── transformation.py    #   Transformation prompt records
│   └── gmail.py             #   Gmail integration model
│
├── graphs/                  # LangGraph state machines  (CLAUDE.md)
│   ├── chat.py              #   conversational agent (message history, provider threading)
│   ├── ask.py               #   retrieve + synthesize (SSE multi-stage)
│   ├── source.py            #   ingestion: extract → embed → save
│   ├── source_chat.py       #   chat scoped to a single source
│   ├── transformation.py    #   run a Transformation prompt over content
│   ├── agent_fsm.py         #   agent finite-state-machine helpers
│   ├── tools.py             #   tool bindings for the agent
│   └── prompt.py            #   shared prompt assembly
│
├── database/                # SurrealDB layer  (CLAUDE.md)
│   ├── repository.py        #   repo_query/create/update/delete/relate + pooled db_connection()
│   ├── async_migrate.py     #   AsyncMigrationManager (auto-discovers + runs migrations)
│   ├── migrate.py           #   sync wrapper (back-compat)
│   ├── dedup_edges.py       #   edge-table de-duplication maintenance
│   └── migrations/          #   1.surrealql .. 22.surrealql (+ N_down.surrealql rollbacks)
│
├── utils/                   # Cross-cutting helpers  (CLAUDE.md, README.md)
│   ├── embedding.py         #   generate_embeddings (batches of 50) + mean pooling
│   ├── chunking.py          #   content-type aware token chunking (CHUNK_SIZE=400)
│   ├── context_builder.py   #   token-budgeted LLM context assembly
│   ├── token_utils.py       #   token_count (o200k_base) + token_cost
│   ├── encryption.py        #   Fernet encrypt/decrypt + KDF + rotation (MultiFernet)
│   ├── memory_recall.py     #   mem0-style fact/preference/episode recall
│   ├── message_history.py   #   chat message history persistence
│   ├── sqlite_checkpoint.py #   LangGraph SQLite checkpoint helpers
│   ├── checkpoint_prune.py  #   prune old LangGraph checkpoints
│   ├── error_classifier.py  #   classify_error() raw-exception → typed exception
│   ├── text_utils.py        #   thinking-tag parsing, ASCII/printable cleaning
│   ├── crawler.py / graph_utils.py / version_utils.py
│
├── digest/                  # scheduler.py — Gmail digest scheduler (defers when offline)
├── health/                  # network.py (TTL net-state cache) + local_models.py health
├── local_models/            # downloader.py, gguf_metadata.py, inventory.py (GGUF management)
├── mcp/                      # client.py, registry.py, recommendations.py (MCP servers)
├── podcasts/                # models.py (PodcastEpisode) + migration.py (legacy→registry)
├── prompt_optimizer/        # runner.py + adapter.py (SkillOpt) + skillopt_prompts/, skillopt_base.yaml
└── tools/                   # web_search.py, add_web_source.py, opencode.py
```

Only four root-level `.py` files (`config.py`, `exceptions.py`, `logging.py`,
plus `__init__.py`) — everything else is a package, keeping responsibilities
namespaced.

---

## 15.3 `api/` — FastAPI Layer

Two real layers (per `api/CLAUDE.md`): **routers** (where most business logic
lives) and **models** (Pydantic schemas). Only four `*_service.py` files survive
(a v0.7.21 cleanup deleted the never-imported service indirection layer).

```
api/
├── CLAUDE.md
├── main.py                  # app init, CORS, PasswordAuthMiddleware, lifespan (migrations), router registration
├── models.py                # Pydantic request/response schemas (validation boundary)
├── auth.py                  # PasswordAuthMiddleware + constant-time _password_matches (v0.6.7)
├── rate_limit.py            # rate-limit helpers
├── metrics.py               # app metrics
│
├── chat_service.py          # invokes chat graph with messages + context
├── podcast_service.py       # outline + transcript orchestration; fire-and-forget job submit
├── command_service.py       # wraps surreal_commands submission + status polling
├── credentials_service.py   # encrypted credential CRUD + validate_url() SSRF guard
│
├── middleware/
│   ├── request_id.py        # per-request id propagation
│   ├── security_headers.py  # security response headers
│   └── metrics.py           # request metrics middleware
│
├── utils/
│   ├── iso.py               # ISO date helpers
│   └── session_locks.py     # per-session async locks
│
└── routers/                 # 30 routers — one file per resource
    ├── notebooks.py  sources.py  notes.py  insights.py  search.py
    ├── chat.py  source_chat.py  context.py            # chat + retrieval surfaces
    ├── podcasts.py  episode_profiles.py  speaker_profiles.py  studio.py
    ├── models.py  credentials.py  embedding.py  embedding_rebuild.py  local_models.py
    ├── transformations.py  commands.py  settings.py  config.py  languages.py
    ├── mcp.py        # MCP registry CRUD (record-id hardening, v0.8.68)
    ├── system.py     # /system/network-status + health
    ├── gmail.py  filesystem.py  exports.py
    ├── onp.py  launcher_prefs.py                       # desktop-launcher config bridge
    └── auth.py
```

`main.py` registers every router and exposes `/health` (back-compat), `/livez`,
`/readyz`. The lifespan handler runs `AsyncMigrationManager` then the podcast
profile data-migration, and starts the digest scheduler; on shutdown it drains
the DB pool.

---

## 15.4 `frontend/` — Next.js 16 / React 19

Three layers: **pages** (App Router), **components** (feature UI), **lib** (data
+ state). Multiple `CLAUDE.md` files document the lib sub-modules.

```
frontend/
├── package.json             # next ^16.2.3, react ^19.2.3, @tanstack/react-query ^5.83.0
├── src/
│   ├── CLAUDE.md            # frontend architecture overview
│   ├── proxy.ts            # Next 16 proxy (renamed from middleware.ts) — first-run wizard redirect
│   ├── app/                # App Router routes
│   │   ├── (auth)/         #   login (route group, no URL segment)
│   │   ├── (dashboard)/    #   protected: notebooks, sources, search, models, podcasts, settings
│   │   └── config/         #   runtime config endpoint
│   ├── components/
│   │   ├── layout/         #   AppShell, AppSidebar
│   │   ├── providers/      #   ThemeProvider, QueryProvider, ModalProvider, I18nProvider
│   │   ├── chat/           #   ChatColumn, ChatMessageProviderBadge, PrivacyBadge, CitationPill
│   │   ├── notebooks/  sources/  source/  search/  podcasts/  settings/  onp/
│   │   ├── common/         #   CommandPalette, ErrorBoundary, ContextToggle, ModelSelector
│   │   ├── errors/  auth/
│   │   └── ui/             #   Radix UI primitives (CLAUDE.md)
│   ├── lib/
│   │   ├── api/            #   client.ts (axios, auth interceptor), query-client.ts, 1 file per resource (CLAUDE.md)
│   │   ├── hooks/          #   36 TanStack Query + SSE hooks (useNotebookChat, useAsk, ...) (CLAUDE.md)
│   │   ├── stores/         #   Zustand auth/modal stores w/ persist (CLAUDE.md)
│   │   ├── types/          #   shared TS request/response types
│   │   ├── locales/        #   en-US, pt-BR, zh-CN, zh-TW, ja-JP + i18n.ts (CLAUDE.md)
│   │   └── utils/          #   error-handler.ts (getApiErrorMessage), helpers
│   └── test/               # vitest setup
```

Provider nesting (`app/layout.tsx`): `ErrorBoundary → ThemeProvider →
QueryProvider → I18nProvider → ConnectionGuard → Toaster`.

---

## 15.5 `desktop/` — Native Launcher

The desktop app runs natively (PyObjC + aiohttp webview), never in Docker. It
spawns SurrealDB, the API, and the Next.js server as child processes and renders
the UI in a native window.

```
desktop/
├── CHANGELOG.md             # the canonical "Unreleased" changelog (Standing Workflow target)
├── __main__.py / app.py     # entrypoint + app object
├── launcher.py / launcher_control.py / launcher_prefs.py   # process orchestration + prefs
├── bootstrap.py             # dependency/venv bootstrap on first launch
├── config.py                # config.toml load/save with 0600/0700 perms (v0.6.8)
├── window.py / aiohttp_window.py / window_state.py         # native webview window
├── splash.py / tray.py / progress.py                       # UX chrome
├── paths.py / ports.py / singleton.py                      # path resolution, port mgmt, single-instance
├── db_repair.py             # SurrealDB repair helpers
├── model_downloads.py       # GGUF download UI flow
├── next_rewrites_patcher.py # patches Next standalone output for desktop
├── auto_register/           # registers the llama.cpp sidecar as openai_compatible
├── first_run/               # first-run wizard assets
├── model_manager/  providers/  dl_scripts/                 # local-model management
├── memory/  memory_dashboard/                              # memory-layer UI
├── desktop_shims/  resources/  bin/                        # shims, icons, bundled binaries
└── tests/                   # desktop-specific tests
```

---

## 15.6 `commands/`, `tests/`, `migrations/`, `scripts/`

### `commands/` — async job handlers (surreal_commands)

```
commands/
├── CLAUDE.md
├── embedding_commands.py        # background embedding / rebuild jobs
├── source_commands.py           # source ingestion jobs
├── podcast_commands.py          # podcast generation job
├── podcast_staged.py            # staged generation + cancel + outline-review (v0.8.68)
├── prompt_optimizer_commands.py # SkillOpt training job
└── example_commands.py          # reference template
```

These are fire-and-forget jobs submitted via `surreal_commands.submit_command`
(the sync primitive that **must** be wrapped in `asyncio.to_thread` from async
code — a recurring gotcha called out in root `CLAUDE.md`).

### `tests/` — 204 test files + integration

```
tests/
├── test_domain.py  test_models_api.py  test_graphs.py
├── test_utils.py  test_chunking.py  test_embedding.py     # + ~200 more
└── integration/
    ├── conftest.py
    ├── test_memory_recall.py
    └── test_notebook_lifecycle.py    # gated on SURREAL_INTEGRATION=1 (live SurrealDB)
```

Run with `uv run pytest tests/`. Integration tests requiring a live DB are
marked `integration_surreal` and skipped unless `SURREAL_INTEGRATION=1`.

### `open_notebook/database/migrations/` — SurrealQL schema

```
migrations/
├── 1.surrealql ... 22.surrealql      # forward migrations (auto-discovered, contiguous 1..N)
└── 1_down.surrealql ... 22_down.surrealql   # optional rollbacks
```

Highlights: `1` defines `fn::text_search`/`fn::vector_search`; `5` core content
tables; `15` memory-layer tables (HNSW 768); `21` HNSW indexes + KNN
`fn::vector_search`; `22` staged-podcast fields. `AsyncMigrationManager`
auto-discovers files and enforces contiguous numbering.

### `scripts/` — operational tooling

```
scripts/
├── ralph.sh                 # autonomous dev loop (.ralph/)
├── backup_restore.py        # DB backup/restore
├── benchmark_models.py      # model latency benchmarking
├── export_docs.py           # docs export
├── repair_desktop_db.sh / wait-for-api.sh / verify-chat-platform.sh
└── create-signing-identity.sh   # macOS code-signing
```

---

## 15.7 The `CLAUDE.md`-per-Module Convention

Every significant module carries its own `CLAUDE.md` — a living architectural
spec read by both humans and AI assistants. Files present:

```
CLAUDE.md                                   # root: architecture + Standing Workflow
open_notebook/CLAUDE.md                     # backend overview
open_notebook/ai/CLAUDE.md                  # ModelManager, provisioning, key_provider
open_notebook/domain/CLAUDE.md              # data models, repository pattern
open_notebook/graphs/CLAUDE.md              # LangGraph workflow design
open_notebook/database/CLAUDE.md            # SurrealDB ops, migrations, pooling
open_notebook/utils/CLAUDE.md               # context/chunking/embedding/encryption
open_notebook/podcasts/CLAUDE.md            # podcast pipeline
api/CLAUDE.md                               # FastAPI structure, services, error handling
commands/CLAUDE.md                          # job-handler patterns
frontend/src/CLAUDE.md                      # frontend architecture
frontend/src/lib/api/CLAUDE.md              # axios client, query-client
frontend/src/lib/hooks/CLAUDE.md            # TanStack Query + SSE hooks
frontend/src/lib/stores/CLAUDE.md           # Zustand state
frontend/src/lib/locales/CLAUDE.md          # i18n
frontend/src/components/ui/CLAUDE.md        # Radix UI primitives
```

Each documents: Purpose, Component Catalog, Common Patterns, Key Dependencies,
"Important Quirks & Gotchas," and "How to Extend." The root `CLAUDE.md` also
defines the **Standing Workflow** (audit → fix → improve → report) and points to
the per-module files via a Component References map. Convention when adding a
module: drop a sibling `CLAUDE.md` mirroring this shape.

---

## 15.8 Naming Conventions

### Version-stamped inline comments (`# v0.8.NN — ...`)

The dominant convention: when code is changed to fix a bug or harden behavior,
the change is annotated with the **release version** that introduced it, a dash,
and an explanation of what was broken and why the new code is correct. There are
**~1,118** such comment lines across the backend/api/desktop; the most prolific
tags:

```
  90  # v0.7.108
  65  # v0.8.68
  65  # v0.8.66
  38  # v0.7.181
  30  # v0.7.182
  26  # v0.7.183
  20  # v0.8.1
```

Representative examples seen elsewhere in these docs:

- `# v0.8.65g — MUST be BaseException, not Exception ...`
  (`database/repository.py` — pooled-connection cancellation fix)
- `# v0.8.66 (audit S-5) — log the detail ... but do NOT embed str(e) ...`
  (`utils/encryption.py` — secret-leak prevention)
- `# v0.7.24 — no caching. Previously this was a process-lifetime singleton ...`
  (`utils/encryption.py` — rotation correctness)

Some are tied to audit findings (`(audit S-5)`, `(audit A-6/A-7)`,
`(audit F-2)`), giving a stable cross-reference between code and review history.

### Other conventions

- **Modules / files**: `snake_case.py` (`offline_gate.py`, `query-client.ts` on
  the TS side uses kebab-case per Next conventions).
- **Migrations**: integer-numbered `N.surrealql` + `N_down.surrealql`,
  contiguous from 1.
- **Stored DB functions**: `fn::<name>` (`fn::vector_search`, `fn::text_search`).
- **Singleton DB records**: `open_notebook:default_models`,
  `open_notebook:content_settings`.
- **Env vars**: `OPEN_NOTEBOOK_*` (app-wide) and `ONP_*` (newer Plus-specific
  knobs, e.g. `ONP_ENCRYPTION_KDF`, `ONP_NETWORK_STATE_TTL_SEC`,
  `ONP_PRIVACY_GATE`).
- **Frontend query keys**: hierarchical arrays via `QUERY_KEYS`
  (`['notebooks', id]`).
- **Services**: `*_service.py` (only the four imported ones survive).

---

## 15.9 Module Dependency Relationships

High-level dependency direction (arrows point from dependent to dependency):

```
frontend/  ──HTTP REST──▶  api/  ──▶  open_notebook/graphs/  ──▶  open_notebook/ai/
                            │                 │                        │
                            │                 ├──▶ open_notebook/domain/ ──▶ database/repository.py ──▶ SurrealDB
                            │                 └──▶ open_notebook/utils/ (context_builder, embedding, token_utils)
                            │
                            ├──▶ commands/ (surreal_commands jobs) ──▶ domain/ + utils/
                            └──▶ open_notebook/health/, digest/, mcp/, tools/

desktop/  spawns  ▶  SurrealDB + api/ (uvicorn) + frontend (Next server)  and renders the UI
```

Layering rules enforced in practice:

- **`domain/` must not import `utils/`** — `context_builder` (in `utils/`)
  imports from `domain.notebook`; the reverse would create a cycle (called out
  in `utils/CLAUDE.md`).
- **`ai/` uses lazy imports** to avoid the
  `utils → embedding → models → key_provider → provider_config → utils` cycle
  (the lazy `model_manager` import inside `embedding.generate_embeddings`).
- **`api/routers/*` mostly bypass services** and call `domain/` + `graphs/`
  directly; the four `*_service.py` files exist only where orchestration is too
  heavy to inline.
- **`graphs/` is the orchestration tier** — every workflow provisions models via
  `ai/provision.provision_langchain_model`, which is where the 105k-token
  upgrade, the offline gate, and the privacy/auto-route hooks all converge.

---

## 15.10 Where Each Responsibility Lives (Quick Index)

| Responsibility | Location |
|---|---|
| HTTP endpoints / validation | `api/routers/*`, `api/models.py` |
| Auth (dev password middleware) | `api/auth.py` |
| Heavy orchestration | `api/{chat,podcast,command,credentials}_service.py` |
| LLM provisioning / routing | `open_notebook/ai/{provision,router,offline_gate,privacy_gate}.py` |
| Model registry + credentials | `open_notebook/ai/models.py`, `open_notebook/domain/credential.py` |
| Workflows (chat/ask/source/...) | `open_notebook/graphs/*` |
| Data models + persistence | `open_notebook/domain/*` ↔ `open_notebook/database/repository.py` |
| Schema / migrations / vector fns | `open_notebook/database/migrations/*.surrealql` |
| Embeddings / chunking / tokens | `open_notebook/utils/{embedding,chunking,token_utils,context_builder}.py` |
| Encryption / secrets | `open_notebook/utils/encryption.py`, `desktop/config.py` |
| Network state / offline | `open_notebook/health/network.py`, `digest/scheduler.py` |
| Memory layer (mem0-style) | `open_notebook/utils/memory_recall.py` + migration 15 tables |
| Podcasts | `open_notebook/podcasts/*`, `commands/podcast_*.py`, `api/podcast_service.py` |
| Prompt optimization (SkillOpt) | `open_notebook/prompt_optimizer/*`, `commands/prompt_optimizer_commands.py` |
| Async jobs | `commands/*` (surreal_commands) |
| UI / state / data fetching | `frontend/src/{app,components,lib}/*` |
| Native app shell | `desktop/*` |
| Tests | `tests/*` (+ `tests/integration/`, `desktop/tests/`) |
| Ops tooling | `scripts/*`, `Makefile`, `Dockerfile*`, `docker-compose.yml` |
