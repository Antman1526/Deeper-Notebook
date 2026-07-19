# AI Review Brief 1 - Product, Architecture, And Code Walkthrough

## Project Overview

Open Notebook Plus is a personal, local-first research workspace built on the
open-notebook server. A notebook owns sources, notes, insights, source chat,
podcasts, transformations, and Evidence Studio artifacts. It competes with
NotebookLM by preserving source-grounded workflows while adding local
inference, an editable multimodal artifact pipeline, MCP tools, local audio
generation, a personal memory layer, and native desktop packaging.

The product has a strict separation between user data and the app bundle:

```text
desktop app bundle: launcher code, frontend, runtime binaries, static assets
user data folder: database, logs, virtualenv, rewritten frontend runtime,
                  downloads, persistent settings, checkpoints, exports
model roots: user-selected directories, normally ~/Desktop/AI_Models
```

That boundary is not cosmetic. The installed macOS bundle is signed and must
not be mutated at runtime. The `next_rewrites_patcher` copies Next.js into the
user data directory before rewriting its API proxy manifests; the launcher
sets `PYTHONDONTWRITEBYTECODE=1` so children do not refresh `.pyc` files in
the bundle.

## Major Components

| Component | Primary files | Responsibility |
| --- | --- | --- |
| Next.js client | `frontend/src/app`, `frontend/src/components`, `frontend/src/stores` | Research UI, routing, streaming presentation, persisted workspace state. |
| FastAPI service | `api/main.py`, `api/routers/*` | HTTP contract, request middleware, startup migrations, background-service lifecycle. |
| Domain and graphs | `open_notebook/domain/*`, `open_notebook/graphs/*` | SurrealDB persistence, LangGraph ingestion/chat/ask workflows, citations, model selection. |
| Job worker | `commands/*` | Async source processing, embeddings, podcasts, transformations, Evidence Studio work. |
| Desktop host | `desktop/app.py`, `desktop/launcher.py` | Launch phases, model/provider selection, sidecar supervision, user-data paths, native window. |
| Local provider adapters | `desktop/providers/*` | Start/stop Ollama, llama.cpp, or MLX behind a common OpenAI-compatible contract. |

## Representative Pattern: Desktop Startup

`desktop/app.py` isolates boot into named phases and passes an `AppContext`
forward. This avoids a large implicit global startup state and makes each phase
testable in isolation.

```python
# desktop/app.py
@dataclasses.dataclass
class AppContext:
    cfg: "Config | None" = None
    arch: str = ""
    bin_dir: "Path | None" = None
    extra_env: dict[str, str] = dataclasses.field(default_factory=dict)
    model_provider_runtime: "ModelProvider | None" = None
    sv: "Supervisor | None" = None

# The run sequence delegates to phase functions in dependency order:
# config -> bootstrap -> model selection -> supervisor -> registration -> UI.
```

The desktop `Supervisor` owns dynamic port allocation and starts dependent
processes in a fixed order: SurrealDB, API, command worker, Next.js, then
optional embedding, voice, chat, and memory sidecars. Its exported
`session_env` is the single environment passed to child processes. Keeping
that one construction point matters because it carries API URLs, database
credentials, model endpoints, and `PYTHONDONTWRITEBYTECODE` consistently.

## Representative Pattern: Provider Interchangeability

The desktop provider protocol keeps the rest of the system independent of the
local inference runtime:

```python
# desktop/providers/__init__.py
class ModelProvider(Protocol):
    name: str
    def is_available(self) -> bool: ...
    def list_models(self) -> list[str]: ...
    def start(self, model: str) -> ProviderEnv: ...
    def stop(self) -> None: ...
```

`MlxProvider.start()` launches `mlx_lm.server`; `LlamaCppProvider.start()`
launches the llama.cpp OpenAI-compatible server; Ollama returns its existing
base URL. All feed the same `OPENAI_COMPATIBLE_BASE_URL` contract into FastAPI,
Esperanto, and the memory shim. This design makes MLX a real fallback rather
than a special UI-only integration.

## Representative Pattern: Source-Grounded Work

The backend starts at routers and delegates to domain/graph code rather than
embedding model calls in handlers. A source upload becomes a command, then the
worker extracts text, stores a source record, chunks/embeds it, and writes
vector records. Chat and Ask retrieve context through the repository layer and
render citations from retrieved source metadata.

The main trade-off is breadth. The application has many user-facing routes and
many product features, so the most valuable refactors are not new abstraction
layers everywhere. They are boundary improvements: smaller chat and notebook
modules, explicit request/response schemas, and contract tests around the
desktop provider and sidecar interfaces.
