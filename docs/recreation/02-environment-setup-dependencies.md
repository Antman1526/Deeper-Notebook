# 02 — Environment Setup & Dependencies

> Recreation documentation for **Open Notebook Plus**. This document covers the
> full dev environment, exact dependency lists, SurrealDB setup, model
> conventions, build tooling, and install/run procedures. Companion docs:
> [`01-project-overview-architecture.md`](./01-project-overview-architecture.md),
> [`03-database-schema-data-models.md`](./03-database-schema-data-models.md).
>
> **Secrets policy:** all keys/passwords below are placeholders like
> `<YOUR_KEY>` / `<YOUR_SURREAL_PASSWORD>`. Never use these literally in prod.

---

## 1. Prerequisites

| Tool | Version | Why |
|------|---------|-----|
| Python | **3.12** (pinned in `.python-version`; `pyproject.toml` allows `>=3.11,<3.13`) | Backend runtime |
| Node.js | **22** (`README.md` badge) | Next.js 16 frontend |
| `uv` | latest (Astral) | Python dependency + venv manager |
| `npm` | bundled with Node 22 (`npm ci`, `npm run build`, `npm test`) | Frontend deps |
| Docker | for self-host SurrealDB (`make database`) | Optional in dev |
| SurrealDB | **v2** | Database (Docker image or bundled binary) |

macOS desktop builds additionally require: Xcode CLT (for `codesign`, `hdiutil`),
and `python3.12` available on `PATH` for the isolated build venv.

---

## 2. Backend dev environment (Python 3.12 + uv)

```bash
git clone https://github.com/Antman1526/open-notebook-Plus
cd open-notebook-Plus

# uv reads pyproject.toml + uv.lock and creates ./.venv
uv sync

# Environment file
cp .env.example .env
# then edit .env (see §5)
```

`uv sync` creates `.venv` and installs the locked dependency set from `uv.lock`
(~497 KB lockfile committed to the repo). The dev extras (`ruff`, `mypy`,
`pytest`, `pre-commit`, etc.) come from the `[project.optional-dependencies] dev`
and `[dependency-groups] dev` tables in `pyproject.toml`.

To run anything in the venv, prefix with `uv run`, e.g.
`uv run pytest tests/`.

### Core backend dependencies (`pyproject.toml`)

`requires-python = ">=3.11,<3.13"`. Runtime `dependencies`:

```
fastapi>=0.136.3
uvicorn>=0.24.0
pydantic>=2.9.2
loguru>=0.7.2
langchain>=1.2.0
langgraph>=1.0.10                  # bumped to remediate CVE-2026-28277
tiktoken>=0.12.0
langgraph-checkpoint-sqlite>=3.0.1
langchain-community>=0.4.1
langchain-openai>=1.1.14
langchain-anthropic>=1.3.0
langchain-ollama>=1.0.1
langchain-google-genai>=4.1.2
langchain-groq>=1.1.1
langchain_mistralai>=1.1.1
langchain_deepseek>=1.0.0
tomli>=2.0.2
python-dotenv>=1.2.2               # CVE-2026-28684
httpx[socks]>=0.27.0
content-core>=1.14.1,<2
ai-prompter>=0.4,<1
esperanto>=2.20.0,<3
surrealdb>=1.0.4
podcast-creator>=0.12.0,<1
surreal-commands>=1.3.1,<2
numpy>=2.4.1
pycountry>=26.2.16
babel>=2.18.0
prometheus-client>=0.20.0         # /metrics endpoint
mcp>=1.0.0                         # MCP client (Phase 2)
# Explicit CVE-remediation pins for transitive deps:
langchain-core>=1.3.3             # CVE-2026-44843
langsmith>=0.8.0                  # CVE-2026-45134
lxml>=6.1.0                       # CVE-2026-41066
urllib3>=2.7.0                    # CVE-2026-44431 + 44432
python-multipart>=0.0.27          # CVE-2026-42561
starlette>=1.2.1                  # CVE-2026-48710 (BadHost)
huggingface-hub>=1.3.0            # managed local-model snapshot installs
```

> **Known blocked upgrade** (documented in `pyproject.toml`): pillow cannot be
> bumped to `>=12.x` because `podcast-creator 0.12.0` pins `pillow<12.0`. The
> affected pillow CVEs are lower-impact because pillow only processes images
> extracted by content-core from uploaded PDFs/DOCX.

### Dev dependencies

```
# [project.optional-dependencies] dev
ipykernel>=6.29.5
ruff>=0.5.5
mypy>=1.11.1
types-requests>=2.32.0.20241016
ipywidgets>=8.1.5
pre-commit>=4.0.1
pytest>=9.0.3

# [dependency-groups] dev
pre-commit>=4.1.0
pytest-asyncio>=1.2.0
ruff>=0.14.13
types-requests>=2.32.4.20250913
```

Tooling config (also in `pyproject.toml`): `ruff` line-length 88, lint rules
`["E", "F", "I", "UP006", "UP007"]` (PEP 585 + PEP 604 modernization), with
`E501/E402/E722/F401/F541/F841` ignored. `isort` uses the black profile. `mypy`
config in `mypy.ini`.

---

## 3. Frontend dev environment (Node 22)

```bash
cd frontend
npm ci          # clean install from package-lock.json
cd ..
```

### Scripts (`frontend/package.json`)

```json
"dev":   "next dev",
"build": "next build",
"start": "node start-server.js",
"lint":  "eslint src/",
"test":  "vitest run --pool=forks --maxWorkers=1"
```

### Frontend runtime dependencies (exact, `frontend/package.json`)

```
next ^16.2.3
react ^19.2.3
react-dom ^19.2.3
zustand ^5.0.6
@tanstack/react-query ^5.83.0
@tanstack/react-virtual ^3.13.24
axios ^1.15.0
zod ^4.0.5
react-hook-form ^7.60.0
@hookform/resolvers ^5.1.1
react-markdown ^10.1.0
@uiw/react-md-editor ^4.0.8
remark-gfm ^4.0.1
lucide-react ^0.525.0
class-variance-authority ^0.7.1
clsx ^2.1.1
cmdk ^1.1.1
date-fns ^4.1.0
i18next ^25.7.3
i18next-browser-languagedetector ^8.2.0
react-i18next ^16.5.0
next-themes ^0.4.6
sonner ^2.0.6
tailwind-merge ^3.3.1
tw-animate-css ^1.3.5
use-debounce ^10.0.6
# Radix UI primitives (Shadcn/ui): accordion, alert-dialog, checkbox,
# collapsible, dialog, dropdown-menu, label, popover, progress, radio-group,
# scroll-area, select, separator, slot, tabs, tooltip
@tailwindcss/typography ^0.5.16
```

### Frontend dev dependencies

```
typescript ^5
tailwindcss ^4
@tailwindcss/postcss ^4
eslint ^9
eslint-config-next ^16.2.6
@next/bundle-analyzer ^16.2.6
vitest ^4.1.8
@vitest/ui ^4.1.8
@vitejs/plugin-react ^4.3.4
@testing-library/react ^16.2.0
@testing-library/jest-dom ^6.6.3
jsdom ^26.0.0
@types/node ^20
@types/react ^19
@types/react-dom ^19
@eslint/eslintrc ^3
```

`overrides`: `postcss ^8.5.10`.

Build/runtime config files: `next.config.ts` (rewrites to API), `tsconfig.json`,
`tailwind.config.ts`, `postcss.config.mjs`, `vitest.config.ts`, `eslint.config.mjs`,
`components.json` (Shadcn).

---

## 4. SurrealDB setup

### Option A — Docker (dev default)

`make database` runs `docker compose up -d surrealdb`. The relevant
`docker-compose.yml` service:

```yaml
services:
  surrealdb:
    image: surrealdb/surrealdb:v2
    command: start --log info --user root --pass root rocksdb:/mydata/mydatabase.db
    user: root
    ports:
      - "8000:8000"
    volumes:
      - ./surreal_data:/mydata
    environment:
      - SURREAL_EXPERIMENTAL_GRAPHQL=true
    restart: always
```

Data persists to `./surreal_data` (RocksDB store). Connection from the API is
`ws://localhost:8000/rpc`, namespace `open_notebook`, database `open_notebook` (or
`production` in the desktop bundle).

### Option B — Bundled binary (desktop)

The desktop launcher spawns a bundled `surreal` binary on an auto-allocated port
with a RocksDB store under `~/.open-notebook-plus/` and credentials from
`config.toml` (`surreal_user` / `surreal_password`). Fetched at build time by
`desktop/build/fetch_runtimes.py`.

### Schema migrations

Migrations are **not** run manually — `AsyncMigrationManager` applies all pending
`open_notebook/database/migrations/*.surrealql` on API startup (see doc 03).

---

## 5. Environment variables (`.env`)

Copy `.env.example` → `.env`. The **critical minimum** (from `README.md` /
`CONFIGURATION.md`), all values shown as placeholders:

```bash
# Database
SURREAL_URL=ws://localhost:8000/rpc
SURREAL_USER=root
SURREAL_PASSWORD=<YOUR_SURREAL_PASSWORD>     # CHANGE in production
SURREAL_NAMESPACE=open_notebook
SURREAL_DATABASE=open_notebook               # desktop uses "production"

# App auth (optional, dev-grade middleware)
OPEN_NOTEBOOK_PASSWORD=<YOUR_APP_PASSWORD>

# Credential encryption (required to store API keys / OAuth tokens)
OPEN_NOTEBOOK_ENCRYPTION_KEY=<YOUR_ENCRYPTION_PASSPHRASE>
# OR rotation form (new key first, old key second):
# OPEN_NOTEBOOK_ENCRYPTION_KEYS=<NEW_KEY>,<OLD_KEY>
```

> The repository ships a real `.env` (mode `0o600`) and `.env.example`. **Never
> copy real secret values into documentation.** The Docker compose default
> `OPEN_NOTEBOOK_ENCRYPTION_KEY=change-me-to-a-secret-string` is a placeholder
> that MUST be replaced.

### Optional tuning env vars (defaults in code)

```bash
ONP_ENCRYPTION_KDF=pbkdf2                       # PBKDF2-HMAC-SHA256, 600k iter
ONP_CHECKPOINT_KEEP_PER_THREAD=50              # LangGraph SQLite prune
ONP_CHECKPOINT_PRUNE_INTERVAL_HOURS=24
ONP_SLOW_QUERY_LOG_MS=500                      # log+count slow DB queries
ONP_CHAT_HISTORY_CHAR_CAP=12000                # chat history trim (~3k tokens)
OPEN_NOTEBOOK_AUTO_ROUTE_CHAT=1                # opt-in per-turn local/cloud routing
ONP_PRIVACY_GATE=1                             # fail-closed PII/secret gate
ONP_AGENT_FSM=1                                # agent-reliability FSM
ONP_MEMORY_KEEP_PER_TABLE / _BATCH_TURNS / _CONFIDENCE_FLOOR  # memory tuning
# Desktop sidecar tuning:
ONP_CHAT_LLM_N_GPU_LAYERS / ONP_EMBED_N_GPU_LAYERS   # -1 (Metal) / 0 (CPU)
ONP_CHAT_LLM_CTX_MAX / OPEN_NOTEBOOK_LOCAL_N_CTX     # context ceilings
OPEN_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH                 # speculative decode draft
# Web search (opt-in by key presence):
SERPER_API_KEY / TAVILY_API_KEY / SEARXNG_BASE_URL
```

---

## 6. Model directory (`model_dir`) conventions

- **Default** (`desktop/config.py::default_model_dir`):
  `~/Desktop/AI_Models` (`%USERPROFILE%\Desktop\AI_Models` on Windows).
- **GGUF subfolder convention** (from `README.md` + user memory): drop `.gguf`
  files into `~/Desktop/AI_Models/GGUF/`. They appear in the model picker on the
  next launch.
- **Ollama**: `ollama pull <name>` — Ollama-installed models auto-appear under
  the Ollama section (detected by the launcher).
- **Embeddings**: the desktop bundle's embed sidecar uses `nomic-embed-text-v1.5`
  (768-dim output, matching the HNSW `DIMENSION 768` in migrations 15 and 21).
- **Chat**: Hermes-3 / Qwen2.5-Instruct / Llama-3.2 GGUFs are the tested local
  chat models; `n_ctx` is auto-detected from GGUF metadata.

---

## 7. Running locally

### Three-terminal workflow (README)

```bash
make database     # terminal 1: SurrealDB via docker compose (:8000)
make api          # terminal 2: FastAPI (:5055)
make frontend     # terminal 3: Next.js (:3000)
```

Resolved Makefile recipes:

```make
database:
	docker compose up -d surrealdb

api:
	uv run --env-file .env run_api.py        # serves :5055

frontend:
	cd frontend && npm run dev               # serves :3000
```

### Background worker (required for podcasts / async embeds)

```make
worker-start:
	uv run --env-file .env surreal-commands-worker --import-modules commands

worker-stop:
	pkill -f "surreal-commands-worker" || true
```

### One-shot dev startup script

`./dev-init.sh` checks SurrealDB connectivity (`SURREAL_PORT`, default `8018`),
runs `uv sync` + `npm install`, then launches the API, the
`surreal-commands-worker`, and the frontend.

### First run

1. Open `http://localhost:3000`.
2. Enter `OPEN_NOTEBOOK_PASSWORD` if set.
3. Create a notebook, upload a source, chat about it.
4. Settings → Models to configure cloud providers (or use bundled local models).

---

## 8. Testing

```make
test:
	uv run pytest tests/ -v --ignore=tests/integration

test-integration:
	SURREAL_INTEGRATION=1 uv run --env-file .env pytest tests/integration/ -v -m integration_surreal
```

- Backend: `make test` (README cites **1712 hermetic backend tests**; integration
  tests need a live SurrealDB and run against a throwaway namespace).
- Frontend: `cd frontend && npm test` (Vitest, `--pool=forks --maxWorkers=1`;
  README cites **195 frontend tests**).
- Desktop: `desktop/tests/` + `desktop/memory/tests/`.
- Lint/typecheck: `make ruff` (ruff `--fix`), `make lint` (`uv run python -m mypy .`).
- Pre-commit hooks: `.pre-commit-config.yaml`.

> The desktop build's "Stage 0" precondition (`make build-mac-test`) runs both
> the desktop suite (test venv, py3.14) **and** the backend suite (repo `.venv`,
> py3.12) before spending time on a build.

---

## 9. Desktop build tooling (PyInstaller + make targets)

The full macOS build is `make build-mac`, a 6-stage pipeline (Makefile §
`build-mac*`). Build variables:

```make
BUILD_PYTHON ?= python3.12
BUILD_VENV   := .build-venv          # isolated from .venv (tests)
BUILD_ARCH   := $(shell uname -m)    # arm64 / x86_64 → DMG filename
ONP_CODESIGN_IDENTITY ?= -           # ad-hoc by default
```

`build-mac` chains:

```make
build-mac: build-mac-test build-mac-lock build-mac-venv \
           build-mac-frontend build-mac-runtimes \
           build-mac-pyinstaller build-mac-dmg
```

| Stage | Target | What it does |
|-------|--------|--------------|
| 0 | `build-mac-test` | Run desktop + backend unit suites as a build precondition (runs `pytest` **directly**, not piped to `tail`, so failures abort the build). |
| 0.5 | `build-mac-lock` | Regenerate `desktop/requirements.lock` from **both** `pyproject.toml` and `desktop/requirements.txt`: `uv pip compile pyproject.toml desktop/requirements.txt --python-version 3.12 -o desktop/requirements.lock`. |
| 1 | `build-mac-venv` | Create `.build-venv` with `python3.12`, `pip install -r desktop/requirements.txt`, then `pip install -e .`. |
| 2 | `build-mac-frontend` | `npm ci` (if needed) + `npm run build` → `frontend/.next/standalone`. |
| 3 | `build-mac-runtimes` | `desktop/build/fetch_runtimes.py` downloads the bundled `surreal`, `node`, `uv`, and python-build-standalone tarball into `desktop/bin/` (idempotent). |
| 4 | `build-mac-pyinstaller` | `pyinstaller desktop/build/pyinstaller.spec --noconfirm` → `dist/Open Notebook Plus.app`, then re-seal: `codesign --force --deep --sign "$(ONP_CODESIGN_IDENTITY)"` and verify with `spctl`/`codesign -v`. |
| 5 | `build-mac-dmg` | `bash desktop/build/post_build_mac.sh` wraps the `.app` into `dist/Open-Notebook-Plus-mac-<arch>.dmg` via `hdiutil`. |

Convenience: `make build-mac-install` quits any running instance then copies the
`.app` to `/Applications`; `make build-mac-clean` / `build-mac-distclean` clean
artifacts.

### Why the re-seal matters (from the Makefile comments)

macOS auto-applies an ad-hoc signature to arm64 Mach-O binaries. PyInstaller
writes the `.app` in multiple phases; any post-seal modification (even Spotlight
writing xattrs) invalidates the Gatekeeper seal, and macOS then **silently kills
the binary at launch** (no dialog, no crash report). The explicit final
`codesign --force --deep --sign -` re-seals the bundle's true final contents. A
**stable** signing identity (via `scripts/create-signing-identity.sh`, then
`make build-mac ONP_CODESIGN_IDENTITY="Open Notebook Plus Local"`) avoids TCC
(Files & Folders) permission resets on every rebuild.

### Desktop bundle requirements (`desktop/requirements.txt`, pinned)

```
pywebview==5.4
pyinstaller>=6.13.0,<7
aiohttp>=3.11.18,<4                 # CVE-2025-37960
llama-cpp-python[server]>=0.3.16,<0.4   # CVE-2024-42479; [server] extra needed
faster-whisper>=1.1.0,<2           # STT
piper-tts>=1.2.0,<2                # TTS (successor to broken `piper`)
mem0ai>=0.1.0,<2                   # in-process memory layer
mcp>=1.0,<2                        # OpenChronicle MCP bridge
fastmcp>=3.0,<4
httpx==0.28.1
tomli==2.2.1; python_version < "3.11"
pytest==8.3.4
pytest-asyncio==0.24.0
skillopt>=0.1.0,<0.2               # microsoft/SkillOpt prompt optimizer (MIT)
```

> The `[server]` extra on `llama-cpp-python` is load-bearing: it pulls in
> `starlette-context`, `sse-starlette`, `pydantic-settings`, and `PyYAML`, all
> required by `python -m llama_cpp.server`. Without it the embed/chat sidecars
> crash at import with `ModuleNotFoundError: No module named 'starlette_context'`.

---

## 10. Docker / self-host

```bash
cp .env.example .env       # fill in passwords + encryption key (placeholders!)
docker compose up -d
# Legacy UI :8502, API :5055, Metrics :5055/metrics
```

`docker-compose.yml` defines `surrealdb` (`surrealdb/surrealdb:v2`) and
`open_notebook` (`lfnovo/open_notebook:v1-latest`, ports `8502` + `5055`, data in
`./notebook_data`). Multi-stage `Dockerfile` / `Dockerfile.single` and
`supervisord.conf` / `supervisord.single.conf` drive the container process tree.
Multi-platform image release: `make docker-release`.

---

## 11. Common pitfalls (from CLAUDE.md + Makefile)

- **Service ordering:** SurrealDB → API → frontend. The UI needs the API; the API
  needs the DB.
- **Worker not running:** podcasts and async embeds stay stuck "Processing" if
  `surreal-commands-worker` isn't running.
- **Lockfile drift:** any backend dep added to `pyproject.toml` or
  `desktop/requirements.txt` must be in `desktop/requirements.lock` before a
  desktop build, or the bundle ships without it (this caused historical
  `ModuleNotFoundError` crashes for `prometheus-client` and `llama-cpp-python`).
- **`PORT` env collision:** never export a global `PORT` into the desktop session
  env — uvicorn-based sidecars read it and bind the wrong port.
