# 02 — Environment Setup & Dependencies

> How to stand up a dev environment for **Open Notebook Plus**, the exact dependency sets, and how to build the packaged desktop app.
> All version constraints are copied verbatim from `pyproject.toml`, `frontend/package.json`, and `desktop/requirements.txt`.

---

## 1. Prerequisites (dev machine)

| Tool | Version / notes |
|---|---|
| **Python** | `>=3.11,<3.13` (see `pyproject.toml` `requires-python`). Dev + packaged runtime standardize on **3.12**. The desktop *build* venv uses `python3.12` (`BUILD_PYTHON ?= python3.12` in the Makefile); the packaged app ships its own `python-build-standalone` 3.12. |
| **uv** | Astral's `uv` package/venv manager. Backend deps are managed via `uv` (`uv run`, `uv pip compile`, `uv.lock`). A `uv` binary is also bundled for the packaged app. |
| **Node.js + npm** | For `frontend/` (Next.js 16). `npm ci` / `npm run dev` / `npm run build`. A Node runtime is bundled into `desktop/bin/` for the packaged app. |
| **SurrealDB** | The graph DB. In dev it runs via Docker (`make database` → `docker compose up -d surrealdb`, port **8000**). In the packaged app the bundled `surreal-<arch>` binary is spawned on a dynamic port. |
| **Docker + docker buildx** | Only for the *server/Docker* release track and dev SurrealDB. The desktop app never runs in Docker. |
| **macOS codesign identity** *(macOS packaging only)* | Optional but recommended. Ad-hoc signing (`-`) gives the app a new identity each rebuild → macOS resets TCC (Files & Folders) permissions each time (the iCloud/Desktop "scandir wedge"). A **stable** identity fixes this: run `bash scripts/create-signing-identity.sh` once, then build with `ONP_CODESIGN_IDENTITY="Open Notebook Plus Local"`. |
| **hdiutil** *(macOS)* | Used by `desktop/build/post_build_mac.sh` to wrap the `.app` into a `.dmg`. |

---

## 2. Backend dependencies (exact — `pyproject.toml`)

Runtime `dependencies`:

```toml
requires-python = ">=3.11,<3.13"
dependencies = [
    "fastapi>=0.136.3",
    "uvicorn>=0.24.0",
    "pydantic>=2.9.2",
    "loguru>=0.7.2",
    "langchain>=1.2.0",
    "langgraph>=1.0.10",              # bumped to remediate CVE-2026-28277
    "tiktoken>=0.12.0",
    "langgraph-checkpoint-sqlite>=3.0.1",
    "langchain-community>=0.4.1",
    "langchain-openai>=1.1.14",
    "langchain-anthropic>=1.3.0",
    "langchain-ollama>=1.0.1",
    "langchain-google-genai>=4.1.2",
    "langchain-groq>=1.1.1",
    "langchain_mistralai>=1.1.1",
    "langchain_deepseek>=1.0.0",
    "tomli>=2.0.2",
    "python-dotenv>=1.2.2",          # CVE-2026-28684
    "httpx[socks]>=0.27.0",
    "content-core>=1.14.1,<2",
    "ai-prompter>=0.4,<1",
    "esperanto>=2.20.0,<3",
    "surrealdb>=1.0.4",
    "podcast-creator>=0.12.0,<1",
    "surreal-commands>=1.3.1,<2",
    "numpy>=2.4.1",
    "pycountry>=26.2.16",
    "babel>=2.18.0",
    "prometheus-client>=0.20.0",     # /metrics endpoint
    "mcp>=1.0.0",                    # MCP client (Phase 2 chat tools)
    "huggingface-hub>=1.3.0",        # managed local-model snapshot installs
    # Explicit pins for transitive deps with known CVEs:
    "langchain-core>=1.3.3",        # CVE-2026-44843
    "langsmith>=0.8.0",             # CVE-2026-45134
    "lxml>=6.1.0",                  # CVE-2026-41066
    "urllib3>=2.7.0",              # CVE-2026-44431 + 44432
    "python-multipart>=0.0.27",     # CVE-2026-42561
    "starlette>=1.2.1",             # CVE-2026-48710
]
```

> **Known blocked upgrade:** pillow cannot go to `>=12` because `podcast-creator 0.12.0` pins `pillow<12.0` (6 pillow CVEs remain open; low impact — pillow only sees content-core-extracted images).

Dev tooling (two groups — legacy `optional-dependencies.dev` and PEP 735 `dependency-groups.dev`):

```toml
[project.optional-dependencies]
dev = [ "ipykernel>=6.29.5", "ruff>=0.5.5", "mypy>=1.11.1",
        "types-requests>=2.32.0.20241016", "ipywidgets>=8.1.5",
        "pre-commit>=4.0.1", "pytest>=9.0.3" ]

[dependency-groups]
dev = [ "pre-commit>=4.1.0", "pytest-asyncio>=1.2.0",
        "ruff>=0.14.13", "types-requests>=2.32.4.20250913" ]
```

Tooling config: `isort` profile black / line 88; `ruff` line 88, selects `E,F,I,UP006,UP007`; `pytest` `asyncio_mode="auto"`, `testpaths=["desktop/tests","tests"]`, marker `integration_surreal` (skipped unless `SURREAL_INTEGRATION=1`).

---

## 3. Frontend dependencies (exact — `frontend/package.json`)

**Scripts**
```json
"dev":            "next dev",
"build":          "next build",
"build:analyze":  "ANALYZE=true next build",
"start":          "node start-server.js",
"lint":           "eslint src/",
"test":           "vitest run --pool=forks --maxWorkers=1",
"test:watch":     "vitest",
"test:ui":        "vitest --ui"
```

**Dependencies** (selected — full list in `package.json`):
`next@^16.2.3`, `react@^19.2.3`, `react-dom@^19.2.3`, `zustand@^5.0.6`,
`@tanstack/react-query@^5.83.0`, `@tanstack/react-virtual@^3.13.24`,
`axios@^1.15.0`, `zod@^4.0.5`, `react-hook-form@^7.60.0`, `@hookform/resolvers@^5.1.1`,
`i18next@^25.7.3`, `react-i18next@^16.5.0`, `i18next-browser-languagedetector@^8.2.0`,
`@xyflow/react@^12.11.1`, `@uiw/react-md-editor@^4.0.8`, `react-pdf@^10.4.1`,
`react-markdown@^10.1.0`, `remark-gfm@^4.0.1`, `remark-math@^6.0.0`, `rehype-katex@^7.0.1`,
`framer-motion@^12.42.0`, `sonner@^2.0.6`, `cmdk@^1.1.1`, `lucide-react@^0.525.0`,
`next-themes@^0.4.6`, `date-fns@^4.1.0`, `use-debounce@^10.0.6`,
`class-variance-authority@^0.7.1`, `clsx@^2.1.1`, `tailwind-merge@^3.3.1`,
`react-resizable-panels@^2.1.9`, `@tailwindcss/typography@^0.5.16`, and the full
`@radix-ui/react-*` primitive set (accordion, alert-dialog, checkbox, collapsible,
dialog, dropdown-menu, label, popover, progress, radio-group, scroll-area, select,
separator, slot, tabs, tooltip).

**devDependencies:**
`typescript@^5`, `@types/node@^20`, `@types/react@^19`, `@types/react-dom@^19`,
`eslint@^9`, `eslint-config-next@^16.2.6`, `@eslint/eslintrc@^3`,
`tailwindcss@^4`, `@tailwindcss/postcss@^4`, `tw-animate-css@^1.3.5`,
`vitest@^4.1.8`, `@vitest/ui@^4.1.8`, `@vitejs/plugin-react@^4.3.4`,
`@testing-library/react@^16.2.0`, `@testing-library/jest-dom@^6.6.3`, `jsdom@^26.0.0`,
`@next/bundle-analyzer@^16.2.6`.

**overrides:** `"postcss": "^8.5.10"`.

---

## 4. Desktop-wrapper dependencies (exact — `desktop/requirements.txt`)

These are pinned *separately* and installed on top of the upstream `pyproject.toml` (CI installs both; `desktop/requirements.lock` is the compiled union — see build section).

```
pywebview==5.4
pyinstaller>=6.13.0,<7
aiohttp>=3.11.18,<4                 # CVE-2025-37960
llama-cpp-python[server]>=0.3.16,<0.4   # CVE-2024-42479; [server] extra REQUIRED
mlx-lm>=0.26,<0.27; sys_platform == "darwin" and platform_machine == "arm64"
faster-whisper>=1.1.0,<2            # STT
piper-tts>=1.2.0,<2                 # TTS
mem0ai>=0.1.0,<2                    # in-process memory layer
mcp>=1.0,<2
fastmcp>=3.0,<4                     # OpenChronicle bridge
httpx==0.28.1
tomli==2.2.1; python_version < "3.11"
pytest==8.3.4
pytest-asyncio==0.24.0
skillopt>=0.1.0,<0.2               # prompt optimizer (microsoft/SkillOpt, MIT)
```

> The `[server]` extra on `llama-cpp-python` is mandatory: it pulls in `starlette-context`, `sse-starlette`, `pydantic-settings`, `PyYAML` needed by `python -m llama_cpp.server`. Without it the local chat/embed sidecars die at import.

---

## 5. Running in development

### 5.1 One-time
```bash
# Backend deps (uv reads pyproject.toml + uv.lock)
uv sync                      # or: uv run <cmd> auto-provisions

# Frontend deps
cd frontend && npm ci && cd ..

# Environment file (never commit secrets)
cp .env.example .env   # if present; set OPEN_NOTEBOOK_ENCRYPTION_KEY, SURREAL_* etc.
```

Required backend env (dev): `OPEN_NOTEBOOK_ENCRYPTION_KEY` (Fernet key for credential storage), `SURREAL_URL` (default `ws://localhost:8000/rpc`), `SURREAL_USER`, `SURREAL_PASSWORD`, `SURREAL_NAMESPACE=open_notebook`, `SURREAL_DATABASE=open_notebook`. See `CONFIGURATION.md`.

### 5.2 Make targets (from the root `Makefile`)

| Target | Effect |
|---|---|
| `make database` | `docker compose up -d surrealdb` (SurrealDB on :8000). |
| `make api` | `uv run --env-file .env run_api.py` (FastAPI on :5055). |
| `make worker` / `make worker-start` | `uv run --env-file .env surreal-commands-worker --import-modules commands`. |
| `make worker-stop` / `make worker-restart` | Stop / restart the worker. |
| `make frontend` / `make run` | `cd frontend && npm run dev` (Next.js on :3000). |
| `make start-all` | Boots SurrealDB (polls `/health` up to 30s) → API → worker → frontend, in order. **Start API before UI.** |
| `make stop-all` | `pkill` all services + `docker compose down`. |
| `make status` | Prints running/not-running for DB / API / worker / frontend. |
| `make lint` | `uv run python -m mypy .` |
| `make ruff` | `ruff check . --fix` |
| `make test` | `uv run pytest tests/ -v --ignore=tests/integration` (hermetic; no external deps). |
| `make test-integration` | `SURREAL_INTEGRATION=1 uv run --env-file .env pytest tests/integration/ -m integration_surreal` (needs live SurrealDB; uses a throwaway namespace). |
| `make backup` / `make restore BUNDLE=… [FORCE=1]` / `make verify-backup BUNDLE=…` | Data-dir snapshot / restore / integrity check (`scripts/backup_restore.py`). |
| `make benchmark-models` | Live model benchmark harness (needs DB+API+worker up). |
| `make export-docs` | `uv run python scripts/export_docs.py`. |

Manual equivalents:
```bash
uv run --env-file .env python run_api.py                              # API
uv run --env-file .env surreal-commands-worker --import-modules commands   # worker
uv run uvicorn api.main:app --host 0.0.0.0 --port 5055                # API (raw)
cd frontend && npm run dev                                            # frontend
```

Interactive API docs: `http://localhost:5055/docs`. Frontend: `http://localhost:3000`.
Desktop-launcher dev run: `python -m desktop` (uses `sys.executable`/repo paths when unfrozen).

---

## 6. Local model setup (GGUF + voices)

- **Model directory:** `~/Desktop/AI_Models` on macOS, `%USERPROFILE%\Desktop\AI_Models` on Windows (`desktop/config.py :: default_model_dir()`). This is the **parent** of the model subfolders — do *not* point it at the `GGUF/` folder itself.
- **Layout the app expects (`_phase_start_supervisor`):**
  - `<model_dir>/GGUF/*.gguf` — chat models (Hermes-3 / Qwen2.5 / Llama-3.2 …). Chat model is auto-selected by a capability-aware, RAM-ceiling-bounded scan (`ONP_CHAT_RAM_GB_CEILING`, default ~4 GB), run in a timeout-bounded thread (`ONP_MODEL_SCAN_TIMEOUT`, default 20s) so a stalled/iCloud dir can't wedge boot.
  - `<model_dir>/GGUF/nomic-embed-text-v1.5.f16.gguf` — embeddings (enables vector search).
  - `<model_dir>/TTS/en_US-amy-medium.onnx` (→ voice "alex"), `<model_dir>/TTS/en_US-ryan-high.onnx` (→ voice "sam") — piper voices.
  - Whisper STT: a local faster-whisper CTranslate2 dir if fully present, else falls back to the HF model name `base.en`.
  - `<model_dir>/MLX/…` — MLX repos (Apple-Silicon only).
- Embedding/STT/TTS models are **auto-downloaded** on first launch by `desktop/model_downloads.py` (phase 4). Chat GGUFs are downloaded via the in-app Models dialog or dropped in manually.
- Local chat sidecar runs with `--n_gpu_layers -1` (full Metal offload) on macOS by default and `0` (CPU) elsewhere (override via env; `desktop/launcher.py :: _n_gpu_layers`).
- Provider is chosen in `config.toml` (`provider` ∈ `ollama | llamacpp | mlx | none`). Config changes require a **full quit + relaunch** to take effect.

**`config.toml`** (`~/.open-notebook-plus/config.toml`, owner-only `0600`) fields (`desktop/config.py`): `model_dir`, `provider`, `default_model`, `surreal_user`, `surreal_password` (random per install), `theme` (default `light-blue`), `openchronicle_choice` (default `skip`), `encryption_key` (random Fernet key, auto-generated). **Contains secrets — never copy its values into docs.**

---

## 7. Building the packaged desktop app (macOS)

Mirrors `.github/workflows/build-desktop.yml`. All from the root `Makefile`.

**One-shot:**
```bash
make build-mac
# → dist/Open Notebook Plus.app  and  dist/Open-Notebook-Plus-mac-<arch>.dmg
```
With a stable signing identity:
```bash
bash scripts/create-signing-identity.sh          # once
make build-mac ONP_CODESIGN_IDENTITY="Open Notebook Plus Local"
```

**Stages (each runnable individually):**

| Stage | Target | What it does |
|---|---|---|
| 0 | `build-mac-test` | Runs desktop unit tests **and** the backend suite as a precondition (fails the build on any failure — no piping to `tail`). |
| 0.5 | `build-mac-lock` | `uv pip compile pyproject.toml desktop/requirements.txt --python-version 3.12 -o desktop/requirements.lock`. Regenerates the union lockfile so no dep silently drops from the bundle. |
| 1 | `build-mac-venv` | Create `.build-venv` with `python3.12`; `pip install -r desktop/requirements.txt` + `pip install -e .`. |
| 2 | `build-mac-frontend` | `npm ci` (if needed) + `npm run build` → Next.js **standalone** output. |
| 3 | `build-mac-runtimes` | `python desktop/build/fetch_runtimes.py` → downloads `surreal`, Node, `uv`, `python-build-standalone` into `desktop/bin/` (idempotent). |
| 4 | `build-mac-pyinstaller` | `pyinstaller desktop/build/pyinstaller.spec --noconfirm` → `dist/Open Notebook Plus.app`; then **re-seal**: `codesign --force --deep --sign "$ONP_CODESIGN_IDENTITY"` + verify with `spctl`/`codesign -v`. (The re-seal is mandatory — PyInstaller's multi-pass writes break macOS's auto ad-hoc seal, and a broken Gatekeeper seal makes the app die silently at launch.) |
| 5 | `build-mac-dmg` | `bash desktop/build/post_build_mac.sh` → `.dmg` via `hdiutil` (unsigned; first launch needs right-click→Open or `xattr -dr com.apple.quarantine`). |

Convenience: `make build-mac-install` (quits any running instance, kills stragglers, copies `.app` to `/Applications`, strips quarantine). Cleanup: `make build-mac-clean` (keeps fetched runtimes) / `make build-mac-distclean` (also wipes `desktop/bin/`).

**Build prereqs summary:** `python3.12` on PATH, Node/npm, network access for `fetch_runtimes.py` (~500 MB) and HF model downloads, macOS with `codesign`/`spctl`/`hdiutil`, and (optionally) a stable codesign identity in the Keychain.

### Packaged-app runtime data locations
- `~/.open-notebook-plus/` — root for `config.toml`, `logs/`, `venv/`, `surreal_data/`, `data/` (`DATA_FOLDER`), `webview_data/`.
- `~/onp-backups/` — automatic DB exports (daily, keep newest 7; `ONP_AUTO_EXPORT_HOURS`).
- `~/Desktop/AI_Models/` — models (see §6).

---

## 8. Server / Docker track (separate from the desktop app)

The upstream/server image uses `pyproject.toml` `version = 1.8.5`. Relevant Make targets: `make docker-build-local`, `make docker-push`, `make docker-release`, and `docker compose -f docker-compose.yml up --build` (aliased by `make dev`/`make full`). This track is only for the self-hosted server deployment; the desktop app does not use it.
