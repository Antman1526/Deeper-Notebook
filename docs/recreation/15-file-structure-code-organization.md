# 15 — File Structure & Code Organization

> 514 Python files (~179k LOC) · 693 TS/TSX files (~125k LOC) · 427 test files.

---

## 1. Top-level layout

```
Deeper-Notebook/
├── api/                    FastAPI application (47 router modules, 279 routes)
├── deeper_notebook/        Business logic — 25 subsystems
├── desktop/                PyWebView shell, launcher, bootstrap, providers, shims
├── frontend/               Next.js 16 application
├── commands/               surreal_commands background job definitions
├── open_notebook/          Upstream compatibility shim package
├── tests/                  Backend suite (4,767 tests)
├── scripts/                rebrand_audit.py, backup_restore.py, create-signing-identity.sh
├── prompts/                Jinja templates (ai-prompter)
├── brand/                  deeper-notebook-mark.svg (canonical mark)
├── docs/                   verification receipts, plans, configuration reference
├── deploy/                 deployment assets
├── examples/               usage examples
├── pyproject.toml          Project deps, ruff/pytest config (version 1.8.5 = server track)
├── uv.lock                 Dev environment lock
├── Makefile                All build/test/deploy targets
├── Dockerfile[.single]     Server images
└── .env.example            Documented settings with defaults and ranges
```

## 2. `api/` — HTTP layer only

```
api/
├── main.py                 App assembly, lifespan, exception handlers
├── auth.py                 check_api_password dependency
├── models.py               Shared response models
├── command_service.py      surreal_commands wrapper (submit/list/cancel)
├── runtime_snapshot.py     Bounded runtime projection
├── routers/                46 modules, one per surface
├── schemas/                Per-feature strict Pydantic schemas
└── utils/                  iso.py (Safari-safe datetimes), helpers
```

**Rule:** routers translate HTTP ↔ domain. Business logic lives in `deeper_notebook/`. A
router that grows algorithms is a refactor signal.

## 3. `deeper_notebook/` — the business core

```
deeper_notebook/
├── domain/            ObjectModel base + Notebook, Source, Note, Credential, …
├── database/          repository.py (repo_query), async_migrate.py, migrations/ (92)
├── graphs/            LangGraph: chat, ask, source, source_chat, transformation,
│                      tools, prompt, agent_fsm
├── ai/                Provider resolution, offline_gate, model_discovery, key_provider
├── tools/             Model-callable tools: web_search, scholarly_search,
│                      add_web_source, web_evidence, opencode
├── source_visuals/    authority, extractors, media, queue, repository, storage,
│                      service, cleanup, contracts
├── knowledge_engine/  Document/block/relation projection
├── vault/             Markdown vault sync, parsers, security
├── overlay/           Daily-note overlay spaces
├── study/             FSRS scheduling, plans, Anki, assistant
├── podcasts/          Episode generation
├── studio/            Evidence Studio workflows
├── video/             Video overview composition
├── research/          discovery, safe_fetch, run orchestration
├── capture/           Filesystem capture inbox (watchdog)
├── analysis/          Claim extraction, verdicts
├── evaluation/        Evaluation runs
├── health/            local_models.py, network.py
├── security/          outbound_url.py, mcp_transport.py
├── mcp/               MCP client + recommendations
├── local_models/      Role routing, planner
├── prompt_optimizer/  SkillOpt integration
├── workspace/         Named workspaces
├── digest/            Digest generation
├── utils/             memory_recall, crawler, version_utils
├── environment.py     151 registered settings, alias precedence
├── feature_flags.py   6 backend flags
├── identity.py        Product identity constants
└── exceptions.py      Typed exception hierarchy
```

## 4. `desktop/` — the native shell

```
desktop/
├── __init__.py            __version__ = "0.8.95"   ← desktop track
├── __main__.py            Entry point
├── app.py                 16 startup phases
├── launcher.py            Supervisor: 9+ sidecars, dynamic ports, process groups
├── bootstrap.py           Runtime extraction + venv provisioning (stamped)
├── window.py              PyWebView window, theme injection, security settings
├── aiohttp_window.py      Alternate window transport
├── launcher_control.py    Local control server
├── launcher_prefs.py      launcher.env read/write
├── data_root.py           Data-root resolution + conflict detection
├── db_repair.py           Recovery UI
├── window_state.py        Screen-aware geometry persistence
├── splash.py  tray.py     Splash + menubar
├── providers/             mlx.py, llamacpp.py — spawn/stop/list_models
├── auto_register/         Credential/model registration per launch
├── desktop_shims/         memory_shim, openchronicle_shim (FastAPI micro-services)
├── memory/                surreal_store.py — mem0 vector store on SurrealDB
├── first_run/             Wizard + injected JS
├── build/                 pyinstaller.spec, fetch_runtimes.py, runtimes.toml,
│                          post_build_mac.sh, package_smoke.py, release_manifest.py
├── resources/             icon.icns, icon.ico, icon.png, make_icon.py
├── bin/                   Fetched runtimes (gitignored)
└── tests/                 832 desktop tests
```

## 5. `frontend/`

```
frontend/
├── src/app/               App Router: (auth)/ and (dashboard)/ groups
├── src/components/
│   ├── ui/                Radix-based primitives
│   ├── layout/            AppShell, AppSidebar
│   ├── deeper-notebook/   Product surfaces
│   │   ├── shell/         InstrumentDock, CommandBar, ContextLens,
│   │   │                  AdaptiveNavigator, FocusModeControl, LuminousAppShell
│   │   ├── workspace/     WorkspaceAppShell, WorkspaceHome, VisualCard,
│   │   │                  StatePanel, workspace.css
│   │   ├── source-gallery/ SourceCover, SourceGallery, RecentSourceStrip, EvidencePeek
│   │   └── runtime/       RuntimeStatusPanel, BackupProvenancePanel
│   ├── chat/  sources/  notebooks/  study/  vault/  podcasts/  capture/
│   ├── search/  settings/  research/  local-models/  overlay/  evaluation/
│   └── providers/  errors/  guided-tips/  intro/  common/
├── src/lib/
│   ├── api/               axios clients, query-client
│   ├── hooks/             use-sources, use-mcp-servers, use-updates, …
│   ├── stores/            display-preferences-store (zustand+persist)
│   ├── types/             api.ts, source-visuals.ts (zod schemas)
│   └── visual-system/     route-manifest.ts (drives e2e matrices)
├── e2e/                   Playwright specs + fixtures
├── package.json           54 deps, 22 devDeps
├── playwright.config.ts   3 projects, workers: 1, port 3117
└── next.config.ts         standalone output, /api rewrites
```

## 6. Naming conventions

| Kind | Convention | Example |
|---|---|---|
| Python module | `snake_case` | `web_search.py` |
| Python private | `_leading_underscore` | `_provider_chain()` |
| Router | noun, plural | `sources.py` |
| Repository | `<domain>_repository.py` | `assistant_repository.py` |
| React component | `PascalCase.tsx` | `SourceCover.tsx` |
| Hook | `use-kebab-case.ts` | `use-mcp-servers.ts` |
| Store | `<domain>-store.ts` | `display-preferences-store.ts` |
| CSS class | `dn-` prefix, BEM-ish | `dn-source-cover__fallback` |
| Data attribute | `data-dn-*` | `data-dn-visual-system="v2"` |
| Test (py) | `test_<feature>.py`, versioned for audits | `test_v0_8_82_keyless_web_search.py` |
| Test (ts) | `<Component>.test.tsx` | `SourceCover.test.tsx` |
| Migration | `<n>.surrealql` + `<n>_down.surrealql` | `46.surrealql` |

## 7. The version-comment convention

Non-obvious code carries a version marker plus the **failure it prevents**:

```python
# v0.7.198 — Wait for the chat server to actually bind its port BEFORE spawning
# the memory retriever. llama-cpp typically takes 10-30 s to mmap a multi-GB
# GGUF; without this gate, mem0.Memory's startup validation hit a closed port
# and the memory child exited rc=1 silently (production-mode DEVNULL).
```

This is the single most valuable convention in the codebase — it turns archaeology into
reading. Preserve it. A comment that explains *what* the code does is redundant; one that
explains *why it must* is load-bearing.

## 8. Module dependency direction

```
desktop/  ──▶ api/  ──▶ deeper_notebook/  ──▶ database/  ──▶ SurrealDB
   │                          │
   └──────── shims ───────────┘   (desktop_shims run as separate processes)

frontend/  ──HTTP──▶  api/
```

Rules:
- `deeper_notebook/` must **not** import from `api/` or `desktop/`.
- `api/` may import `deeper_notebook/`; never `desktop/`.
- `domain/` must not import the chat graph (layering) — this is why notebook delete
  cascades chat sessions but leaves LangGraph checkpoint cleanup to the router.
- Lazy imports inside functions are used deliberately to keep import time low and to make
  pure helpers testable without heavy optional deps (`import webview` inside `open_window`).

## 9. Where to add things

| Task | Location |
|---|---|
| New API surface | `api/routers/<name>.py` + register in `main.py` |
| New business rule | `deeper_notebook/<subsystem>/` |
| New model-callable tool | `deeper_notebook/tools/` + bind in `graphs/chat.py` |
| New table | new numbered migration + `_down` |
| New setting | register in `environment.py`, accessor near consumer, `.env.example` |
| New UI surface | `frontend/src/app/(dashboard)/<route>/page.tsx` |
| New sidecar | `_spawn_*` in `launcher.py` + health probe + credential registration |

## 10. Generated / gitignored

```
.venv/  .build-venv/  node_modules/  frontend/.next/  dist/  build/
desktop/bin/  __pycache__/  .pytest_cache/  .ruff_cache/
~/.deeper-notebook/                 ← all user data, venv, logs, runtime
```

**`~/.deeper-notebook/` is the user's data root.** Never write app state into the bundle;
never delete this directory as part of any build or install step.

---

*End of the 15-document set. See [PROJECT-DEEP-DIVE.md](./PROJECT-DEEP-DIVE.md) for the
condensed architectural review and [TECHNOLOGY-AUDIT.md](./TECHNOLOGY-AUDIT.md) for the full
technology inventory.*
