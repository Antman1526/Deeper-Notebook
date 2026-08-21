# 01 — Project Overview & Architecture

> **Recreation target:** Deeper Notebook v0.8.114 (desktop app track).
> Upstream server/Docker track is versioned separately at 1.8.5 in `pyproject.toml`.
> **Source of truth for this document:** the working tree at commit `58ff44b4`.
> Regenerated 2026-08-21 (refreshed for v0.8.114: final local package, installed
> smoke proof, and release-readiness gates). ExamLab, Debate mode,
> Cornell Notes, and the auto-route fallback fix). Supersedes the 2026-08-09 packet.

---

## 1. What this product is

Deeper Notebook is a **local-first, source-grounded research and personal knowledge
workspace** that ships as a **native macOS desktop application**. It is a hard fork of
`lfnovo/open-notebook`, diverged far enough that it maintains its own identity, its own
version track, and its own compatibility/rebrand machinery.

The defining product constraint, from which nearly every architectural decision follows:

> **Everything can run on the user's machine with no cloud account.** Inference,
> embeddings, speech-to-text, text-to-speech, the database, and the web server are all
> local processes. Cloud providers are optional accelerants, never prerequisites.

The application lets a user:

- Import **sources** (PDFs, URLs, audio, video, Office docs, plain text) into **notebooks**
- Chat with a model that is **grounded in those sources**, with citations
- Run **transformations** (summarise, extract claims, generate insights) over sources
- Generate **podcasts** (multi-speaker audio) and **video overviews** from notebook content
- Study via an **FSRS-scheduled spaced-repetition** system with Anki import/export
- Maintain a **Markdown vault** (Obsidian/Logseq-compatible) with bidirectional sync
- Search across everything (full-text + vector), and reach the public web through tools

## 2. The three-tier runtime

```
┌──────────────────────────────────────────────────────────────────────┐
│  PyWebView shell  (desktop/window.py)                                │
│  Native macOS window; loads http://127.0.0.1:<frontend_port>         │
│  NOT a browser — no arbitrary navigation. JS bridge exposes only     │
│  window.pywebview.api.relaunch                                       │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ renders
┌───────────────────────────▼──────────────────────────────────────────┐
│  Next.js 16.2.12 frontend (frontend/)   React 19.2.3, App Router     │
│  Runs as a standalone Node server on a dynamic port.                 │
│  Rewrites /api/* → FastAPI. TanStack Query for server state,         │
│  Zustand for client state.                                           │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ HTTP (localhost only)
┌───────────────────────────▼──────────────────────────────────────────┐
│  FastAPI backend (api/)   279 routes across 47 router modules        │
│  Business logic in deeper_notebook/. LangGraph orchestrates the      │
│  chat/ask/transformation graphs.                                     │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ WebSocket RPC
┌───────────────────────────▼──────────────────────────────────────────┐
│  SurrealDB 2.x (bundled binary)  ~75 tables, 92 forward migrations   │
│  Document + graph + vector store in one engine.                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Why SurrealDB.** The data model needs three things simultaneously: document storage
(sources, notes), graph edges (`reference`, `artifact`, `refers_to`, `note_link`), and
vector similarity (embeddings for RAG). SurrealDB provides all three in a single embedded
process with no external services. The cost is a smaller ecosystem and a query language
(SurrealQL) with fewer safety rails than SQL — see doc 14 for how injection risk is managed.

## 3. Process topology at runtime

The launcher (`desktop/launcher.py`) supervises up to **9 child processes**, each on a
dynamically allocated free port (never hardcoded — port collisions across relaunches were
a recurring production bug):

| Process | Spawn method | Purpose |
|---|---|---|
| SurrealDB | `_spawn_surreal` | Database engine (bundled binary) |
| FastAPI (uvicorn) | `_spawn_api` | Backend API |
| Next.js | `_spawn_next` | Frontend server (standalone build) |
| llama.cpp chat | `_spawn_llamacpp_chat` | Local GGUF chat model, OpenAI-compatible |
| llama.cpp embed | `_spawn_llamacpp_embed` | Local embeddings (nomic-embed-text) |
| Whisper | `_spawn_whisper` | Speech-to-text shim |
| Piper | `_spawn_piper` | Text-to-speech shim |
| Memory retriever | `_spawn_memory_retriever` | mem0-backed memory shim |
| OpenChronicle bridge | `_spawn_openchronicle_bridge` | Optional MCP bridge |
| Worker | `_spawn_worker` | `surreal_commands` background job worker |

All children are spawned with `start_new_session=True` so `stop_all()` can kill the whole
process **group** — a bare `terminate()` orphaned Next.js grandchildren that survived app
close and held ports.

**MLX** is a tenth optional runtime, spawned by `MlxProvider` (not the supervisor) for
Apple-Silicon-optimised inference.

## 4. Startup sequence

`desktop/app.py` runs **16 named phases** in strict order. This ordering encodes hard
dependencies discovered through production failures:

```
_phase_detect_data_root_recovery   → conflicting data roots
_phase_detect_app_recovery         → prior bundle replacement
_phase_open_data_root_recovery     → isolated repair UI
_phase_load_config                 → ~/.deeper-notebook/config.toml
_phase_wizard_if_first_run         → first-run setup
_phase_bootstrap_runtime           → extract Python, provision venv  ← slow, one-time
_phase_download_models             → optional managed model pulls
_phase_select_provider             → llamacpp | mlx | none
_phase_detect_openchronicle
_phase_register_memory_commands
_phase_start_supervisor            → all sidecars; chat LLM before memory retriever
_phase_auto_register               → credentials/models into the DB
_phase_start_model_manager
_phase_start_memory_dashboard
_phase_install_tray
_phase_open_window                 → blocks until the user closes it
```

Two orderings are load-bearing:

1. **chat LLM before memory retriever** — mem0 validates its LLM endpoint at construction;
   a closed port made the memory child exit rc=1 silently.
2. **voice/embed registration before auto-assign** — models registered after assignment
   never reached the default slots.

## 5. Bootstrap: the two-venv model

The frozen PyInstaller launcher carries only `pywebview`, `aiohttp`, `httpx`. The heavy
stack (FastAPI, LangChain, SurrealDB driver, mem0, MLX) lives in a **user venv** at
`~/.deeper-notebook/venv`, provisioned on first launch by a **bundled `uv`** against a
**bundled portable Python** (python-build-standalone 20260814 / CPython 3.12.14).

Two invalidation stamps keep this honest (added v0.8.83 after a runtime bump silently
failed to propagate):

```python
# desktop/bootstrap.py
# Extraction is keyed to the tarball that produced it.
stamp_path = runtime_dir / ".source-tarball.sha256"
tarball_hash = hashlib.sha256(tarball.read_bytes()).hexdigest()


# The venv marker is keyed to interpreter identity + lock hash, not lock alone.
def _provision_key(standalone_python: Path, lock_path: Path) -> str:
    return f"{_interpreter_stamp(standalone_python)} {_lock_hash(lock_path)}"
```

`_interpreter_stamp` returns `"<python version> <OpenSSL version>"`. OpenSSL is included
deliberately: Wikimedia's edge rejects the OpenSSL 3.0 TLS fingerprint, which is exactly
the class of defect a runtime bump must be able to deliver.

## 6. Feature flags

Six backend flags (`deeper_notebook/feature_flags.py`) plus build-time frontend flags.

| Flag | Default | Governs |
|---|---|---|
| `DEEPER_NOTEBOOK_VISUAL_REFRESH` | on | Visual refresh surfaces |
| `DEEPER_NOTEBOOK_EVIDENCE_STUDIO` | on | Evidence Studio |
| `DEEPER_NOTEBOOK_MODEL_FLEET` | on | Model fleet management |
| `DEEPER_NOTEBOOK_RESEARCH_RUNS` | **off** | Research run orchestration |
| `DEEPER_NOTEBOOK_STUDY_WORKBENCH` | on | Study workbench |
| `DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED` | **off** | Source Visual Gallery (backend) |

**Critical packaging property:** frontend flags (`NEXT_PUBLIC_DN_*`) are **inlined by
`next build`** and cannot be changed at runtime in a packaged app. Only the backend flag
is a live kill switch. This asymmetry caused a real defect — see doc 07 §Capability
Sentinel.

## 7. Repository layout (top level)

```
api/              FastAPI app: 47 router modules, schemas, services
deeper_notebook/  Business logic: 25 subsystems, domain models, graphs, DB
desktop/          PyWebView shell, launcher, bootstrap, providers, shims
frontend/         Next.js 16 app (693 TS/TSX files)
commands/         surreal_commands background job definitions
tests/            Backend suite (4,906 tests)
scripts/          rebrand_audit.py, backup_restore.py, signing identity
prompts/          Jinja prompt templates (ai-prompter)
brand/            deeper-notebook-mark.svg (canonical mark)
docs/             verification receipts, plans, configuration reference
open_notebook/    Upstream compatibility shim package
```

## 8. Architectural invariants

These are enforced by tests and must survive any refactor:

1. **No sync I/O in `async def`.** Every network call uses `httpx.AsyncClient`. A
   sync call inside an async handler blocks the event loop and freezes the UI.
2. **Local-first fail-soft.** Any optional subsystem failing (web search, MLX, memory)
   degrades to reduced function; it never aborts a chat turn or the launch.
3. **Ports are dynamic, never hardcoded.** Credentials store base URLs that are
   *refreshed every launch* by `auto_register`.
4. **Product identity is audited.** `scripts/rebrand_audit.py --check` classifies every
   legacy-name occurrence; unexpected active identity fails the build gate.
5. **Sidecar stderr is captured.** `stderr=DEVNULL` has hidden fatal errors for hours;
   the supervisor drains stderr to per-child `.tail` files.
6. **Feature rollback must be provable.** Flags ship default-off with a tested
   rollback matrix.

## 9. Where the complexity actually lives

Ranked by conceptual difficulty, for anyone recreating this:

1. **`desktop/launcher.py` + `bootstrap.py`** — process supervision, port allocation,
   two-venv provisioning, stamp invalidation. The hardest-won code in the repo.
2. **`deeper_notebook/source_visuals/`** — bounded extraction, cache lifecycle, queue
   claims with fencing, revision authority.
3. **`deeper_notebook/graphs/chat.py`** — the tool loop, MCP resolution, fail-soft
   binding.
4. **`deeper_notebook/vault/`** — Markdown parsing, bidirectional sync, trust records.
5. **`scripts/rebrand_audit.py`** — a self-validating governance registry (2,896 lines).

---

*Continues in [02 — Environment Setup & Dependencies](./02-environment-setup-dependencies.md).*
