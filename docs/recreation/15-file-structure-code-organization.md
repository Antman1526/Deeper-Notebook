# 15 — File Structure & Code Organization

> The complete annotated directory tree for **Open Notebook Plus**, naming conventions, module-dependency relationships, and where each concern lives.
> Paths are relative to the repo root `/Users/Antman/Desktop/OpenNotebook/open-notebook-Plus/` unless noted.

---

## 1. Top-level layout

```
open-notebook-Plus/
├── api/                  FastAPI backend: routers + 4 real services + schemas + middleware
├── open_notebook/        Backend core: domain models, LangGraph graphs, DB, AI, utils
├── commands/             surreal-commands async job handlers (podcasts, embeddings, insights…)
├── desktop/              Desktop wrapper: launcher/supervisor, pywebview window, build, sidecars
├── frontend/             Next.js 16 / React 19 UI (src/ App Router, components, hooks, stores)
├── prompts/              Jinja2 prompt templates (ask, chat, podcast, source_chat)
├── migrations/           (upstream) top-level SurrealQL migration mirror; canonical set lives under open_notebook/database/migrations/
├── tests/                Backend + integration test suite (pytest)
├── scripts/              Ops scripts: ralph.sh, backup_restore.py, benchmark_models.py, repair_desktop_db.sh, create-signing-identity.sh, export_docs.py
├── docs/                 User + deployment documentation (mkdocs)
├── deploy/               Deployment assets
├── examples/             Example content / notebooks
├── data/, surreal_data/, output/, build/, dist/   Runtime + build artifacts (gitignored)
├── run_api.py            Dev entry point: `uv run --env-file .env run_api.py` → uvicorn api.main:app
├── pyproject.toml        Backend deps + tool config (version 1.8.5 = server/Docker track)
├── uv.lock               Backend lockfile
├── Makefile              All dev + macOS build targets
├── Dockerfile / Dockerfile.single / docker-compose.yml   Server/Docker track
├── supervisord.conf / supervisord.single.conf            Server process config
├── CLAUDE.md             Root architecture guide (authoritative)
├── CONFIGURATION.md, CONTRIBUTING.md, MAINTAINER_GUIDE.md, SECURITY.md
├── README.md / README.dev.md / README.upstream.md
└── CHANGELOG.md          (desktop changelog is desktop/CHANGELOG.md)
```

**Two version tracks:** `pyproject.toml version = "1.8.5"` = upstream/Docker image; `desktop/__init__.py __version__ = "0.8.5"` = desktop app (window, `/api/version`, macOS `CFBundleShortVersionString`). They intentionally version different artifacts.

---

## 2. `api/` — FastAPI backend

```
api/
├── main.py                  App init: load_dotenv → CORS → auth/rate-limit/metrics/request-id/
│                            security-headers middleware → lifespan (configure_logging,
│                            AsyncMigrationManager, podcast profile migration, digest scheduler,
│                            DB pool drain) → global exception handlers → include_router(...)
│                            Exposes /health (back-compat), /livez, /readyz.
├── models.py                Pydantic request/response schemas (ChatRequest, NoteResponse, …)
├── auth.py                  PasswordAuthMiddleware (Authorization: Bearer <password>)
├── rate_limit.py            RateLimitMiddleware
├── metrics.py               Prometheus metric definitions
│
├── chat_service.py          Invoke chat graph with messages + context      ┐
├── podcast_service.py       Orchestrate outline + transcript generation     │ the ONLY 4
├── command_service.py       Wrap surreal_commands submit + status polling   │ real services
├── credentials_service.py   Encrypted credential CRUD + connection testing  ┘ (rest deleted v0.7.21)
│
├── routers/                 One module per resource; MOST business logic lives here inline
│   ├── notebooks.py notes.py sources.py source_chat.py chat.py search.py
│   ├── podcasts.py episode_profiles.py speaker_profiles.py studio.py
│   ├── credentials.py models.py local_models.py embedding.py embedding_rebuild.py
│   ├── transformations.py insights.py context.py commands.py
│   ├── config.py settings.py languages.py exports.py filesystem.py
│   ├── auth.py system.py updates.py launcher_prefs.py onp.py mcp.py gmail.py
├── schemas/                 __init__.py, studio.py (extra request/response schemas)
├── middleware/              metrics.py, request_id.py, security_headers.py
└── utils/                   iso.py (ISO datetime helper), session_locks.py
```

**Router-registration** (`main.py`): every router in `api/routers/` is imported and `include_router`-ed. Adding an endpoint = new `routers/*.py` + register in `main.py` + schema in `models.py`.

**Error handling:** global FastAPI exception handlers map `open_notebook.exceptions` types → HTTP codes (NotFound 404, InvalidInput 400, Auth 401, RateLimit 429, Configuration 422, Network/ExternalService 502, base 500).

---

## 3. `open_notebook/` — backend core (75 `.py` modules)

```
open_notebook/
├── config.py            DATA_FOLDER / UPLOADS_FOLDER / LANGGRAPH_CHECKPOINT_FILE paths (DATA_FOLDER env)
├── exceptions.py        OpenNotebookError hierarchy (DatabaseOperationError, NotFoundError,
│                        InvalidInputError, ConfigurationError, AuthenticationError,
│                        RateLimitError, ExternalServiceError, NetworkError, …)
├── logging.py           Central loguru config (rotated file sinks in ~/.open-notebook-plus/logs)
├── feature_flags.py     Experimental feature toggles
│
├── domain/              DATA MODELS (async SurrealDB persistence)
│   ├── base.py          ObjectModel (mutable, auto-id: save/delete/relate/get/get_all) +
│   │                    RecordModel (singleton config, fixed id)
│   ├── notebook.py      Notebook, Source, Note, ChatSession, SourceInsight, SourceEmbedding,
│   │                    Asset, StudioArtifact, StudioWorkflowRun; text_search(), vector_search()
│   ├── credential.py    Credential (Fernet-encrypted API keys, SecretStr, to_esperanto_config)
│   ├── transformation.py Transformation + DefaultPrompts singleton
│   ├── content_settings.py ContentSettings singleton (engines, embedding strategy, deletion)
│   ├── gmail.py         GmailIntegration (digest schedule)
│   └── provider_config.py  LEGACY ProviderConfig (migration-only; superseded by Credential)
│
├── graphs/              LANGGRAPH WORKFLOWS (StateGraph state machines)
│   ├── chat.py          Conversational agent + history + notebook context; SQLite checkpoints
│   ├── source_chat.py   Chat scoped to one source (ContextBuilder injects insights/content)
│   ├── ask.py           RAG: generate search terms → vector/text search → synthesize; per-node timeout
│   ├── source.py        Ingestion pipeline: extract (content-core) → save → transform
│   ├── transformation.py Single-node LLM transform (Jinja2 template)
│   ├── prompt.py        Generic prompt→model→parse chain
│   ├── agent_fsm.py     Agent finite-state machine (tool-loop orchestration)
│   └── tools.py         LLM tool helpers (e.g. get_current_timestamp)
│
├── ai/                  AI PROVISIONING & ROUTING
│   ├── models.py        Model (LLM/embed/STT/TTS record + credential link) + DefaultModels singleton + ModelManager
│   ├── provision.py     provision_langchain_model() factory (smart selection, fallback, override)
│   ├── router.py        Pure local-vs-cloud routing (size, health, context headroom)
│   ├── key_provider.py  API-key resolution: DB (decrypted) first, env fallback → Esperanto
│   ├── connection_tester.py  Minimal-call credential validation (TEST_MODELS)
│   ├── model_discovery.py    Discover available models per provider
│   ├── privacy_gate.py / privacy_classifier.py  Fail-closed PII/secret filter before cloud routing
│   └── offline_gate.py  Block cloud selection when offline / privacy-preferred
│
├── database/            SURREALDB LAYER
│   ├── repository.py    Async CRUD + pool: repo_create/update/query/delete/relate; RecordID parsing
│   ├── async_migrate.py AsyncMigrationManager (loads N.surrealql, tracks version, runs on startup)
│   ├── migrate.py       Sync wrapper for back-compat
│   ├── dedup_edges.py   Edge-table dedup cleanup
│   └── migrations/      1.surrealql … 25.surrealql + matching N_down.surrealql (50 files)
│                        11-12 credential system · 13 model↔credential link · 14 podcast registry
│                        · 15 flexible credential config · 16-25 refinements/indexes/studio
│
├── utils/               CROSS-CUTTING HELPERS
│   ├── context_builder.py  Assemble LLM context (token budgeting, priority)
│   ├── embedding.py     generate_embedding/embeddings (chunk + batch + mean-pool)
│   ├── chunking.py      Content-type detection + smart splitters (HTML/MD/plain)
│   ├── token_utils.py   tiktoken counting (o200k_base)
│   ├── text_utils.py    Cleaning + parse/clean thinking-content
│   ├── encryption.py    Fernet encrypt_value/decrypt_value (Docker secrets, legacy fallback)
│   ├── error_classifier.py classify_error() raw provider err → typed exception
│   ├── citation_offsets.py  Map citations back to source positions
│   ├── memory_recall.py memory recall from chat history
│   ├── message_history.py   store/retrieve chat messages
│   ├── graph_utils.py   LangGraph state/edge helpers
│   ├── checkpoint_prune.py + sqlite_checkpoint.py  LangGraph SQLite checkpoint mgmt
│   ├── crawler.py       crawl4ai URL scraping (lazy-loaded)
│   └── version_utils.py version compare / GitHub check
│
├── local_models/        Local GGUF lifecycle: manifest, inventory, role_routing, downloader,
│                        gguf_metadata, benchmarks, snapshot_installer
├── mcp/                 client.py (streamable-http wrapper), registry.py, recommendations.py
├── health/             local_models.py (sidecar probes), network.py (connectivity)
├── digest/             scheduler.py (Gmail digest background scheduler, 5-min wake)
├── podcasts/           models.py (Podcast, Episode, Outline, Transcript, SpeakerInfo), migration.py
├── prompt_optimizer/   adapter.py, runner.py, skillopt_prompts/ (SkillOpt integration)
├── studio/             artifact_generation.py (Evidence Studio CSV/JSON/ZIP export)
└── tools/              add_web_source.py, web_search.py, opencode.py
```

Per-subsystem `CLAUDE.md` guides exist at: `open_notebook/`, `open_notebook/ai/`, `open_notebook/domain/`, `open_notebook/graphs/`, `open_notebook/database/`, `open_notebook/utils/`, `open_notebook/podcasts/`.

### Domain persistence base classes
- **`ObjectModel`** — mutable records (Notebook, Source, Note, …); polymorphic `get(id)` resolves subclass from the `table:id` prefix; auto-embedding via ModelManager; `relate(rel, target)` for edges `reference`/`artifact`/`refers_to`.
- **`RecordModel`** — singleton config (ContentSettings, DefaultPrompts, DefaultModels); fixed record id; `__new__` returns existing instance (call `clear_instance()` in tests).

---

## 4. `commands/` — async job handlers

```
commands/
├── __init__.py                    imports all command modules for worker discovery
├── source_commands.py             process_source_command, run_transformation_command
├── embedding_commands.py          embed_note/insight/source_command, create_insight_command,
│                                  rebuild_embeddings_command
├── podcast_commands.py            generate_podcast_command
├── podcast_staged.py              staged podcast generation helpers
├── prompt_optimizer_commands.py   prompt-optimization jobs
├── studio_commands.py             Evidence Studio artifact jobs
└── example_commands.py            test fixtures (process_text, analyze_data)
```

`desktop/memory/memory_commands.py` is copied into this dir at boot (`_phase_register_memory_commands`) so the worker discovers the memory handlers.

**Conventions:** every command is `@command("name", app="open_notebook", retry={...})`; Pydantic `CommandInput`/`CommandOutput`; retry uses `stop_on: [ValueError]` (blocklist — retries everything except validation errors). Domain models submit these fire-and-forget via `submit_command()`.

---

## 5. `desktop/` — desktop wrapper

```
desktop/
├── __init__.py            __version__ = "0.8.5" (desktop app version)
├── __main__.py            `python -m desktop` entry
├── app.py                 run(): ordered boot phases over an AppContext (see doc 01 §7)
├── launcher.py            Supervisor: spawns/monitors surreal, api, worker, next, sidecars;
│                          find_free_ports(9); session_env; process-group teardown; DB repair;
│                          periodic export; control-plane callbacks (restart/hot-swap)
├── window.py              open_window(): pywebview splash→app handoff controller, theme +
│                          voice + memory JS injection, persistent storage, _OnpJsApi.relaunch
├── window_state.py        save/load/clamp remembered window size
├── splash.py              build_splash_html() inline welcome splash
├── config.py              Config dataclass + config.toml load/save (0600); default_model_dir()
├── paths.py               user_home() etc.
├── ports.py               find_free_port(s) with SO_REUSEADDR + de-dup re-probe
├── progress.py            ProgressBus (progress.jsonl) for splash/status
├── bootstrap.py           extract_python_runtime + ensure_venv (uv install from requirements.lock)
├── model_downloads.py     auto-download embedding/STT/TTS models; FASTER_WHISPER_* constants
├── singleton.py           PID-file lock + orphan reaper (AlreadyRunning)
├── db_repair.py           needs_repair / auto_repair / looks_like_lq_corruption (backup-first)
├── next_rewrites_patcher.py  patch Next.js standalone rewrites → dynamic api_port
├── launcher_control.py    ControlServer (in-launcher HTTP control plane)
├── launcher_prefs.py      file-backed launcher.env preference layer
├── aiohttp_window.py      start_aiohttp_server_thread (model-manager / memory-dashboard windows)
├── tray.py                install_tray (Open Main / Models / Memory / Quit)
├── requirements.txt       desktop-only pinned deps (pywebview, pyinstaller, llama-cpp-python[server]…)
├── requirements.lock      compiled union of pyproject + requirements.txt (built by make build-mac-lock)
│
├── auto_register/         Register discovered local models/creds with the API (assigner.py:
│                          pick_chat_llm_file, capability-aware selection)
├── providers/             ollama.py, llamacpp.py, mlx.py (ModelProvider protocol: is_available/start)
├── first_run/             server.py (wizard), static/ (voice_injection.js, memory_injection.js)
├── model_manager/         server.py (build_app) — models window backend
├── memory_dashboard/      server.py (build_app) — memory dashboard backend
├── memory/                mem0 integration + memory_commands.py template + tests/
├── desktop_shims/         openchronicle_shim.py + whisper/piper/memory shim entry points
├── dl_scripts/            model download helper scripts
├── build/                 fetch_runtimes.py, pyinstaller.spec, post_build_mac.sh
├── bin/                   BUNDLED RUNTIMES (fetched): surreal-<arch>, node, uv, python-<arch>.tar.gz
├── resources/             icons, plists, splash assets
├── CHANGELOG.md           desktop-app changelog (source of truth for __version__)
└── tests/                 desktop pytest suite (test_launcher, test_window, test_bootstrap, …)
```

---

## 6. `frontend/` — Next.js 16 / React 19

```
frontend/
├── next.config.ts          Next config (rewrites /api/* → API, standalone output, bundle analyzer)
├── tsconfig.json           TS compiler + path aliases
├── tailwind.config.ts      Tailwind v4 theme/plugins
├── components.json         shadcn/ui registry (aliases)
├── vitest.config.ts        Vitest config
├── eslint.config.mjs       ESLint 9 flat config (eslint-config-next)
├── postcss.config.mjs      PostCSS (Tailwind)
├── start-server.js / start-server-utils.js   standalone server bootstrap (npm start)
├── package.json / package-lock.json
└── src/
    ├── app/                        NEXT.JS APP ROUTER
    │   ├── (auth)/login/           login page
    │   ├── (dashboard)/            protected route group:
    │   │   ├── notebooks/ notebooks/[id]/     notebook list + detail/chat
    │   │   ├── sources/ sources/[id]/         source list + detail
    │   │   ├── search/ podcasts/ studio/ transformations/ advanced/
    │   │   ├── setup-wizard/                   first-launch wizard
    │   │   └── settings/                       hub +
    │   │       ├── api-keys/ (credentials) launcher-prefs/ local-models/ mcp/
    │   ├── api/                    Next.js route handlers (SSE proxy):
    │   │   ├── search/ask/                     ask streaming
    │   │   └── sources/[sourceId]/chat/…       chat message streaming
    │   └── config/                 runtime config route (reads API_URL env)
    │
    ├── components/
    │   ├── ui/                shadcn/Radix primitives (Button, Dialog, Input, Select, …)
    │   ├── layout/            AppShell, AppSidebar, navigation
    │   ├── providers/         ThemeProvider, QueryProvider, ModalProvider, I18nProvider, ConnectionGuard
    │   ├── common/            CommandPalette, ErrorBoundary, ModelSelector, ContextToggle, Toaster
    │   ├── auth/ errors/ intro/ onp/
    │   └── chat/ notebooks/ sources/ source/ search/ podcasts/ podcasts/forms/ settings/
    │
    └── lib/
        ├── api/              Axios CLIENT + resource modules
        │   ├── client.ts     Axios instance + auth interceptor + configurable timeout (10 min;
        │   │                  NEXT_PUBLIC_API_TIMEOUT_MS); auto FormData Content-Type handling
        │   ├── query-client.ts  TanStack Query client
        │   └── sources.ts notebooks.ts chat.ts search.ts podcasts.ts credentials.ts
        │       models.ts notes.ts embeddings.ts settings.ts
        ├── hooks/            40+ React Query + custom hooks
        │   ├── use-sources.ts use-notebooks.ts use-credentials.ts use-models.ts use-auth.ts
        │   ├── useNotebookChat.ts useSourceChat.ts use-ask.ts (SSE streaming)
        │   └── use-translation.ts (i18n wrapper + language switching)
        ├── stores/           Zustand: auth-store (30s check cache + persist), navigation-store,
        │                     theme-store, notebook-view-store, notebook-columns-store, sidebar-store
        ├── locales/          i18next: index.ts, i18n.ts, i18n-events.ts + 14 language folders
        │                     (en-US, pt-BR, zh-CN, zh-TW, ja-JP, ru-RU, de-DE, es-ES, fr-FR,
        │                      it-IT, ca-ES, pl-PL, tr-TR, bn-IN)
        ├── types/            api.ts (request/response shapes)
        └── utils/            error-handler.ts (getApiErrorMessage), citations.ts,
                              source-context.ts, source-references.tsx, date-locale.ts
```

`CLAUDE.md` guides: `frontend/src/`, `frontend/src/lib/api/`, `frontend/src/lib/stores/`, `frontend/src/lib/hooks/`, `frontend/src/lib/locales/`.

**Frontend 3-layer split:** `app/` (routes) → `components/` (UI) → `lib/` (data + state + i18n). Data flows: component → `hooks/use-*` → `lib/api/*` (axios) → API. Server state lives in TanStack Query; UI/auth state in Zustand.

---

## 7. `prompts/` — Jinja2 templates

```
prompts/
├── ask/     entry.jinja, query_process.jinja, final_answer.jinja
├── chat/    system.jinja
├── podcast/ outline.jinja, transcript.jinja
└── source_chat/ system.jinja
```
Rendered via **ai-prompter** (Jinja2). Graphs reference these by path. Transformation prompts additionally come from the `Transformation` domain model / `DefaultPrompts`.

---

## 8. `tests/` and `desktop/tests/`

- **`tests/`** — backend + integration. Two flavors:
  - Feature/regression tests named by version (`test_v0_7_*`, `test_v0_8_*`) — one file per release fixing specific bugs.
  - Subsystem tests: `test_domain.py`, `test_graphs.py`, `test_models_api.py`, `test_embedding.py`, `test_chunking.py`, `test_credentials_*`, `test_chat_*`, `test_podcast_*`, `test_memory_*`, `test_search_api.py`, `test_notebook_delete_cascade.py`, `test_encryption_*`, health/router tests, etc.
  - `tests/integration/` — SurrealDB-backed (`integration_surreal` marker, skipped unless `SURREAL_INTEGRATION=1`).
- **`desktop/tests/`** — launcher/window/bootstrap/provider tests (`test_launcher*.py`, `test_window*.py`, `test_bootstrap.py`, `test_ollama_provider.py`, `test_mlx_provider.py`, `test_auto_register*.py`, `test_db_repair.py`, `test_v0_8_68_*`, …).

`pytest` config (`pyproject.toml`): `asyncio_mode="auto"`, `testpaths=["desktop/tests","tests"]`.

---

## 9. Naming conventions

- **Version-tagged code comments & tests:** fixes carry `# v0.7.NN — …` / `# v0.8.NN — …` inline comments naming what was broken; regression tests are `tests/test_v0_7_NN_*.py`. The desktop `__version__` must equal the newest `## vX.Y.Z` header in `desktop/CHANGELOG.md` (enforced by a test).
- **Backend Python:** snake_case files/functions; `PascalCase` domain/Pydantic classes; commands `<verb>_<noun>_command`; env vars `OPEN_NOTEBOOK_*` / `ONP_*` / `SURREAL_*` / `MEMORY_*`.
- **API:** `routers/<resource>.py`, `<resource>_service.py` (only 4 exist), schemas in `models.py`.
- **Frontend:** hooks `use-<thing>.ts` (a few legacy camelCase like `useNotebookChat.ts`); Zustand stores `<name>-store.ts`; api resource modules `<resource>.ts`; components `PascalCase.tsx`; shadcn primitives in `components/ui/`.
- **Migrations:** `N.surrealql` + `N_down.surrealql` (monotonic integer version).
- **Prompts:** `<graph>/<step>.jinja`.

---

## 10. Module-dependency relationships (who imports whom)

```
frontend (app → components → lib/api axios) ──HTTP──▶ api/routers/*
api/routers/* ──▶ api/*_service.py (4)                    ──▶ open_notebook.graphs.*
             └──▶ open_notebook.domain.*  (models)        ──▶ open_notebook.database.repository
open_notebook.graphs.* ──▶ open_notebook.ai.provision ──▶ open_notebook.ai.key_provider
                                                       └──▶ esperanto (LLM/embed/TTS clients)
open_notebook.graphs.* ──▶ prompts/*.jinja (via ai-prompter)
open_notebook.domain.* ──▶ commands/* (submit_command, fire-and-forget) ──▶ surreal-commands worker
commands/* ──▶ open_notebook.utils.{chunking,embedding} + open_notebook.database.repository
api/main.py ──▶ open_notebook.database.async_migrate.AsyncMigrationManager ──▶ migrations/*.surrealql
desktop.app ──▶ desktop.launcher.Supervisor ──▶ (surreal | uvicorn api.main:app | worker | next | sidecars)
desktop.launcher ──▶ desktop.{ports,config,singleton,db_repair,next_rewrites_patcher,launcher_control}
desktop.app ──▶ desktop.{bootstrap,model_downloads,auto_register,providers,first_run,tray,window}
```

**Import direction rules:** `api/` and `commands/` depend on `open_notebook/` (never the reverse). `desktop/` depends on nothing in `api/`/`open_notebook/` at import time except through the venv it provisions and the subprocesses it spawns (it runs the API as `uvicorn api.main:app` in a child process with `cwd=upstream_root`). The frontend depends on the API only over HTTP.

---

## 11. Where each concern lives (quick index)

| Concern | Location |
|---|---|
| HTTP endpoints | `api/routers/*.py` |
| Request/response schemas | `api/models.py`, `api/schemas/` |
| Auth / rate-limit / metrics / headers | `api/auth.py`, `api/rate_limit.py`, `api/middleware/` |
| Data models & persistence | `open_notebook/domain/`, base classes `domain/base.py` |
| DB access + migrations | `open_notebook/database/` (+ `migrations/`) |
| AI provider selection / keys | `open_notebook/ai/` |
| LLM workflows | `open_notebook/graphs/` + `prompts/` |
| Async jobs | `commands/` (executed by surreal-commands worker) |
| Embeddings / chunking / tokens | `open_notebook/utils/` |
| Podcasts | `open_notebook/podcasts/` + `commands/podcast_commands.py` |
| Local model lifecycle | `open_notebook/local_models/` + `desktop/model_downloads.py` + `desktop/providers/` |
| Memory | `desktop/memory/` + `open_notebook/utils/memory_recall.py` |
| Desktop boot / process supervision | `desktop/app.py`, `desktop/launcher.py` |
| Native window / theming | `desktop/window.py` |
| Packaging / build | `desktop/build/`, `Makefile` (`build-mac*`) |
| Frontend routes | `frontend/src/app/` |
| Frontend UI | `frontend/src/components/` |
| Frontend data/state/i18n | `frontend/src/lib/` |
| Config (desktop) | `~/.open-notebook-plus/config.toml` (via `desktop/config.py`) |
| Config (backend paths) | `open_notebook/config.py` |
| Tests | `tests/`, `tests/integration/`, `desktop/tests/` |
