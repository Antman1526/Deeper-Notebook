# Current Reconstruction Snapshot - 2026-07-19

This document is the dated companion to the numbered reconstruction set in
this directory. It records the source and release state that was verified on
2026-07-19. Where an older numbered document conflicts with this snapshot,
this snapshot wins. It deliberately contains no credentials, local database
contents, or personal notebook data.

## Source Identity

| Field | Value |
| --- | --- |
| Repository | `Antman1526/open-notebook-Plus` |
| Working branch | `desktop-app` |
| Verified commit | `808ef6cbd8850f540b76c7221972156b584f7205` |
| Desktop version | `0.8.97` (`desktop/__init__.py`) |
| Server/Docker package version | `1.8.5` (`pyproject.toml`) |
| Desktop distribution | Native PyInstaller one-directory app wrapped in a macOS DMG |
| Primary local model roots | `~/Desktop/AI_Models` and the user-selected path in `~/.open-notebook-plus/config.toml` |

The two version tracks are intentional. `pyproject.toml` versions the
upstream-compatible server/container package. `desktop/__init__.py` versions
the native application shell, its bundle metadata, API version endpoint, and
in-app update notifier. Do not collapse them into one release number.

## Current Architecture

The application has two deployment modes that share the same FastAPI domain
and Next.js UI:

1. **Server/development mode** runs FastAPI, Next.js, and SurrealDB from the
   repository or Compose configuration.
2. **Desktop mode** starts a small PyInstaller launcher. The launcher creates
   a per-user virtual environment at `~/.open-notebook-plus/venv`, then
   supervises SurrealDB, FastAPI, the Next standalone server, a job worker,
   optional local model sidecars, and a PyWebView window.

The durable source of truth is SurrealDB. LangGraph SQLite checkpoints are a
separate, intentionally narrow persistence layer for conversational graph
state. The desktop bundle is immutable at runtime: user data, logs, frontend
rewrite copies, virtualenv packages, model downloads, and database files must
remain under `~/.open-notebook-plus/` or the configured model folder.

```text
PyWebView / Next.js UI
        |
        | REST, SSE, NDJSON
        v
FastAPI routers + LangGraph workflows
        |                   |
        |                   +--> Esperanto / local OpenAI-compatible providers
        v
SurrealDB <---- surreal_commands worker ---- ingestion, embeddings, podcasts,
   |                                      transformations, Evidence Studio
   +--> HNSW vector indexes and graph edges
```

## July 19 Desktop Reliability Corrections

The following fixes are in the verified commit and are important when
recreating the desktop product:

| Problem | Implementation | Why it matters |
| --- | --- | --- |
| Sidebar labels flashed outside a narrow rail on first render | `frontend/src/components/layout/AppSidebar.tsx` suppresses the width transition until after the responsive desktop state is established. | The first visual frame is stable instead of rendering labels before the rail expands. |
| A signed app mutated its own frontend when Next rewrite manifests were patched | `desktop/next_rewrites_patcher.py` detects paths inside `.app` and copies the frontend to `~/.open-notebook-plus/frontend-runtime` before patching. | macOS code signatures remain valid after first launch. |
| Python child processes refreshed `.pyc` files inside the signed bundle | `desktop/launcher.py` exports `PYTHONDONTWRITEBYTECODE=1` in the child process environment. | Runtime imports cannot invalidate the bundle seal. |
| A slow or unavailable MLX model folder could block application launch | `desktop/providers/mlx.py` performs discovery in a daemon thread with a bounded scan timeout. | The UI can open in a degraded state instead of hanging indefinitely. |
| MLX-only launch still recursively inspected GGUF files during auto-registration | `desktop/auto_register/__init__.py` skips GGUF discovery unless a live llama.cpp chat port exists. | A large, synced, or partially downloaded model library cannot delay the main window when it cannot be served anyway. |

The intended degraded behavior is explicit: when no usable chat provider is
available, the application opens and indicates the missing capability. It does
not pretend a chat model is ready or leave the user on a blank page.

## Local Model Contract

The model provider abstraction lives in `desktop/providers/`. All active
local chat backends must present an OpenAI-compatible API to the rest of the
application:

```python
# desktop/providers/__init__.py
class ModelProvider(Protocol):
    name: str
    def is_available(self) -> bool: ...
    def list_models(self) -> list[str]: ...
    def start(self, model: str) -> ProviderEnv: ...
    def stop(self) -> None: ...
```

For Apple Silicon MLX, the launcher runs `python -m mlx_lm.server` against a
complete repository below `MLX/`. When no chat GGUF is present, the MLX
endpoint becomes both `OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL` and
`MEMORY_CHAT_LLM_URL`; the stable model name exposed to the application is
`default_model`. The embedding GGUF remains independent and is served by the
llama.cpp embedding sidecar.

## Verified Release Gate

The current macOS release was built and checked with the following gates:

```bash
python3 -m pytest desktop/tests -q
make build-mac-pyinstaller build-mac-dmg BUILD_PYTHON=/opt/homebrew/bin/python3.12
codesign --verify --deep --strict "dist/Open Notebook Plus.app"
hdiutil verify "/Users/Antman/Downloads/Open-Notebook-Plus-mac-arm64.dmg"
```

`456` desktop tests passed in the release verification. The packaged app was
installed in `/Applications`, started to the `ready` progress event, rendered
through its live Next server, and still passed strict code-signature validation
after launch. The distribution is ad-hoc signed for personal use, not Apple
notarized; Gatekeeper may require the normal right-click/Open first-launch
flow on another Mac.

## Documentation Map

The numbered documents remain the reconstruction contract:

| Topic | Document |
| --- | --- |
| Architecture and system boundaries | `01-project-overview-architecture.md` |
| Setup and exact dependency constraints | `02-environment-setup-dependencies.md` |
| SurrealDB schema and domain models | `03-database-schema-data-models.md` |
| FastAPI endpoint contract | `04-backend-api-specifications.md` |
| Next.js component and state architecture | `05-frontend-architecture-components.md` |
| Authentication and access control | `06-authentication-authorization.md` |
| Graphs, jobs, routing, and algorithms | `07-business-logic-core-algorithms.md` |
| External integrations | `08-integration-points-external-services.md` |
| Configuration and flags | `09-configuration-environment-variables.md` |
| Test strategy | `10-testing-strategy-test-cases.md` |
| Build and deployment | `11-build-deployment-pipeline.md` |
| Errors, logs, and debugging | `12-error-handling-logging.md` |
| Performance and caching | `13-performance-optimization-caching.md` |
| Security controls | `14-security-implementation.md` |
| File and module organization | `15-file-structure-code-organization.md` |

`PROJECT-DEEP-DIVE.md` and `AI-REVIEW-01` through `AI-REVIEW-03` are the
condensed review inputs. `TECHNOLOGY-AUDIT.md` is the exhaustive dependency
inventory. Use the files together: no single document is intended to replace
the implementation source.

## Known Limits Worth Reviewing

- Desktop startup still performs bounded health, database, and optional
  provider work before the primary window becomes interactive. It is now
  observable and bounded, but startup can be longer on a cold local model
  environment.
- Local directory discovery necessarily uses filesystem APIs that can stall on
  removable, cloud-synced, or permission-gated volumes. The desktop provider
  layer uses bounded daemon scans; future discovery APIs should retain that
  property.
- The upstream-compatible server side and the personal desktop shell evolve
  on separate version tracks. Merges from upstream need a deliberate
  compatibility pass for launcher imports, desktop paths, and the data-only
  PyInstaller payload.
- The app deliberately supports cloud providers, but sensitive-source safety
  depends on correct privacy-gate configuration and explicit user consent.

## Reconstruction Procedure

1. Read documents 01, 02, 03, 04, 05, 07, 09, 11, and 15 in that order.
2. Recreate the server mode first with a disposable SurrealDB and fake
   OpenAI-compatible provider.
3. Verify API schemas and frontend route contracts before introducing real
   model credentials or local GPU/Metal runtimes.
4. Build desktop mode only after the server is stable. Treat the `.app` as
   read-only and route every mutable file to the user data directory.
5. Prove a packaged app with signature checks, a launch-to-ready check, and a
   real browser/PyWebView render check. Do not equate a successful build with
   a successful desktop release.
