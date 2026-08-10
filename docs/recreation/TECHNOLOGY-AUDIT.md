# Deeper Notebook — Technology Audit

> **Current identity note:** this audit covers the Deeper Notebook checkout.
> Historical `Open Notebook Plus` identifiers are listed only where they are
> compatibility aliases, persisted bundle IDs, or migration evidence.

An exhaustive inventory of every language, framework, library, tool, and service used, with each item's **specific role in this project** and version constraints. Sourced from `pyproject.toml`, `desktop/requirements.txt`, `frontend/package.json`, `Dockerfile*`, `.github/workflows/*`, `Makefile`, `supervisord*.conf`, `desktop/build/pyinstaller.spec`, and real imports.

> Version tracks: desktop app `0.8.5` (`desktop/__init__.py`); upstream/Docker image `1.8.5` (`pyproject.toml`). `requires-python = ">=3.11,<3.13"`.

---

## Languages

| Technology | Version | Role in this project |
|---|---|---|
| **Python** | 3.11–3.12 (`.python-version` → 3.11; Docker builder `python:3.12-slim-trixie`) | Entire backend: FastAPI API, `open_notebook/` domain + graphs + AI layer, `commands/` job handlers, and the `desktop/` supervisor/launcher/window shell. |
| **TypeScript** | `^5` | The whole Next.js frontend (`frontend/src/`) — components, hooks, API clients, types (e.g. `notebook-context.ts`). |
| **SurrealQL** | SurrealDB dialect | Schema + migrations (`open_notebook/database/migrations/*.surrealql`), edge-table `DEFINE`s, and the `fn::vector_search` DB function. |
| **Jinja2** | via `ai-prompter` | Prompt templates (`prompts/**/*.jinja`) for chat/ask/source_chat/podcast, rendered with variable injection + output-parser format instructions. |
| **Bash / Shell** | — | `scripts/*.sh` (ralph loop, `repair_desktop_db.sh`, `wait-for-api.sh`), `dev-init.sh`, and the in-app relaunch shell string in `desktop/window.py`. |

---

## Backend Framework & Runtime

| Technology | Version | Role |
|---|---|---|
| **FastAPI** | `>=0.136.3` | REST API in `api/`; routers for notebooks, sources, notes, chat, podcasts, models, credentials, transformations, insights, auth, languages, commands, settings; global exception handlers map the custom exception hierarchy to HTTP codes; lifespan runs migrations + starts the digest scheduler. |
| **Uvicorn** | `>=0.24.0` | ASGI server. Desktop launcher spawns `python -m uvicorn api.main:app`; Docker via supervisord. |
| **Starlette** | `>=1.2.1` (CVE-2026-48710 pin) | Underlies FastAPI; `BaseHTTPMiddleware` powers `PasswordAuthMiddleware` (`api/auth.py`). |
| **Pydantic** | `>=2.9.2` (v2) | All request/response schemas (`api/models.py`), domain models (`open_notebook/domain/*`), and `CommandInput`/`CommandOutput` for jobs. |
| **pydantic-settings** | via `llama-cpp-python[server]` | Env-driven config for the bundled `llama_cpp.server` sidecars. |
| **Loguru** | `>=0.7.2` | Structured logging across API/graphs/commands; `configure_logging("api")` writes a file sink so startup errors persist. |
| **python-dotenv** | `>=1.2.2` (CVE-2026-28684) | Loads `.env` at API startup. |
| **httpx[socks]** | `>=0.27.0` | Async HTTP client for provider connection tests, the `web_search` tool, launcher readiness probes, and internal calls. |
| **python-multipart** | `>=0.0.27` (CVE-2026-42561) | Multipart parsing for file-upload endpoints. |
| **tomli** | `>=2.0.2` | TOML parsing (config/version). |
| **numpy** | `>=2.4.1` | Embedding vector math (mean-pooling large content, similarity helpers). |
| **prometheus-client** | `>=0.20.0` | `/metrics` endpoint (pure-Python, histogram buckets). |

---

## LangGraph / LangChain AI Orchestration

| Technology | Version | Role |
|---|---|---|
| **LangGraph** | `>=1.0.10` (bumped for CVE-2026-28277) | State-machine workflows: `chat` (single "agent" node + tool loop), `source` (extract→save→fan-out transform), `ask` (multi-search synthesis), `source_chat`, `transformation`, `prompt`. `Send` powers transformation fan-out; `StateGraph.compile(checkpointer=...)`. |
| **langgraph-checkpoint-sqlite** | `>=3.0.1` | `SqliteSaver` (sync) + `AsyncSqliteSaver` (async streaming) persist chat message history to a WAL-tuned SQLite file (`LANGGRAPH_CHECKPOINT_FILE`), independent of SurrealDB. |
| **LangChain** | `>=1.2.0` | Message types (`SystemMessage`, `ToolMessage`), `RunnableConfig`, output parsers used by graphs/prompts. |
| **langchain-core** | `>=1.3.3` (CVE-2026-44843) | Core message/runnable primitives. |
| **langchain-community** | `>=0.4.1` | Community integrations pulled in transitively. |
| **langsmith** | `>=0.8.0` (CVE-2026-45134) | Transitive tracing dep (pinned for CVE, not necessarily enabled). |
| **langchain-openai** | `>=1.1.14` | OpenAI chat/embeddings provider binding. |
| **langchain-anthropic** | `>=1.3.0` | Anthropic (Claude) provider binding. |
| **langchain-ollama** | `>=1.0.1` | Ollama local-model binding. |
| **langchain-google-genai** | `>=4.1.2` | Google Gemini binding. |
| **langchain-groq** | `>=1.1.1` | Groq binding. |
| **langchain-mistralai** | `>=1.1.1` | Mistral binding. |
| **langchain-deepseek** | `>=1.0.0` | DeepSeek binding. |
| **tiktoken** | `>=0.12.0` | Token counting (`o200k_base`) in `utils/token_utils.py` — drives context sizing, the 105k large-context cutoff, history trimming, and local vs cloud routing math. |
| **ai-prompter** | `>=0.4,<1` | `Prompter` renders the Jinja prompt templates by path (`"chat/system"`) and auto-injects `{{ format_instructions }}` when bound to a Pydantic output parser. |

---

## AI Providers & Local Inference

| Technology | Version | Role |
|---|---|---|
| **Esperanto** | `>=2.20.0,<3` | Unified multi-provider abstraction (`LanguageModel`, `AIFactory`) for LLM / embeddings / TTS across OpenAI, Anthropic, Google, Groq, Ollama, Mistral, DeepSeek, xAI, OpenRouter, Voyage, ElevenLabs, Azure, Vertex, openai_compatible. `provision_langchain_model()` and `ModelManager` build on it. |
| **llama-cpp-python[server]** | `>=0.3.16,<0.4` (CVE-2024-42479 pin) | Bundled local GGUF inference sidecars. Launcher spawns `python -m llama_cpp.server` twice — a **chat** server and an **embed** (nomic) server — exposing an OpenAI-compatible API on dynamic ports; `--n_gpu_layers=-1` on macOS Metal for full offload. The `[server]` extra pulls in starlette-context/sse-starlette/PyYAML. |
| **mlx-lm** | `>=0.26,<0.27` (`darwin`+`arm64` only) | Apple-Silicon MLX local model server (`python -m mlx_lm.server`) against `~/Desktop/AI_Models/MLX`, same OpenAI-compatible shape as llama.cpp. |
| **Ollama** | via `langchain-ollama` / Esperanto | Local model provider (never gated by the offline gate — treated as machine-local). |
| **huggingface-hub** | `>=1.3.0` | `snapshot_download` for managed local-model installs (`desktop/model_downloads.py`, first-run model fetch). |
| **Smart router** | `open_notebook/ai/router.py` (in-repo) | `pick_provider()` chooses local vs cloud by health + token-fit + `default_provider`; gated behind `OPEN_NOTEBOOK_AUTO_ROUTE_CHAT` env / UI toggle. |
| **Offline gate** | `open_notebook/ai/offline_gate.py` (in-repo) | Substitutes a local model when offline + candidate is cloud; fail-open. |
| **Privacy gate** | `open_notebook/ai/privacy_gate.py` + `privacy_classifier.py` (in-repo) | Structured-secret detector; fails closed (reroute local / block) when cloud routing would leak keys/PII. |

**Cloud providers reachable via Esperanto (opt-in by credential/key):** OpenAI, Anthropic, Google, Groq, Mistral, DeepSeek, xAI, OpenRouter, Voyage (embeddings), ElevenLabs (TTS), Azure, Vertex, generic `openai_compatible` — 13 provider kinds handled in `api/routers/credentials.py`.

---

## Database

| Technology | Version | Role |
|---|---|---|
| **SurrealDB** (server binary) | bundled per-arch (`surreal-<arch>` in `desktop/bin/`) | Primary datastore: records (notebook, source, note, chat_session, source_embedding, source_insight, transformation, credential, studio_artifact, command) + RELATION edges (`reference`, `artifact`, `refers_to`) + vector search. Launcher spawns it on a dynamic port with file-backed storage under `~/.open-notebook-plus/surreal_data`. |
| **surrealdb** (Python driver) | `>=1.0.4` | Async client used by `open_notebook/database/repository.py` (`repo_query`, `repo_create`, `repo_upsert`, `ensure_record_id`); connection pool lazy-inits on first query. |
| **AsyncMigrationManager** | in-repo | Auto-applies `migrations/*.surrealql` on API lifespan startup; version-recorded, idempotent (`IF NOT EXISTS`), with `_down.surrealql` rollbacks. |
| **SQLite** (via stdlib + langgraph-checkpoint-sqlite) | — | LangGraph chat/checkpoint persistence only; WAL-tuned shared connection (`utils/sqlite_checkpoint.py`) to avoid "database is locked" under concurrent sessions. |
| **RocksDB** (inside SurrealDB) | — | SurrealDB's on-disk engine; its live-query bookkeeping is the corruption source `desktop/db_repair.py` heals. |

---

## Async Jobs

| Technology | Version | Role |
|---|---|---|
| **surreal-commands** | `>=1.3.1,<2` | SurrealDB-backed job queue. `@command(...)` handlers in `commands/` (`process_source`, `run_transformation`, `embed_source`/`embed_note`/`embed_insight`, `create_insight`, `rebuild_embeddings`, `generate_podcast`); a separate worker (`python -m surreal_commands.cli.worker --import-modules commands --max-tasks 5`) consumes them. Retries use blocklist `stop_on=[ValueError, ConfigurationError]` + exponential jitter. `submit_command` is wrapped in `asyncio.to_thread` from async code. |
| **CommandService** | `api/command_service.py` (in-repo) | `submit_command_job()` wraps submission with a timeout; `/commands/{command_id}` reports status. |

---

## Content Processing

| Technology | Version | Role |
|---|---|---|
| **content-core** | `>=1.14.1,<2` | File/URL extraction engine (`extract_content`, `ProcessSourceState`) — 50+ file types, web page text+metadata, YouTube transcripts; produces the `full_text` saved on a source. Engine choices come from `ContentSettings`. |
| **crawl4ai** | via `open_notebook/utils/crawler.py` | Optional local URL scraper (`extract_url_with_crawl4ai`) selected when `url_engine == "crawl4ai"`, with content-core fallback. |
| **lxml** | `>=6.1.0` (CVE-2026-41066) | HTML/XML parsing under content-core extraction. |
| **Pillow** | `<12.0` (pinned by podcast-creator; CVEs noted, upgrade blocked) | Image handling for images extracted from PDFs/DOCX by content-core. |
| **imageio-ffmpeg** | `>=0.6.0,<1.0` (locked `0.6.0`) | Supplies the platform FFmpeg executable used by `open_notebook/video/composer.py` to locally encode and decode-validate source-grounded Video Overview MP4 files; its runtime is bundled in desktop release preparation. |
| **chunking / embedding utils** | in-repo (`utils/chunking.py`, `utils/embedding.py`) | Content-type-aware splitting (HTML/Markdown/plain, ~1500 char / 225 overlap) and batched embedding (50/batch, per-batch retry, mean-pooling for oversized content). |
| **tiktoken** | `>=0.12.0` | (Also listed above) token counting for chunk/context sizing. |

---

## Podcast / TTS / STT

| Technology | Version | Role |
|---|---|---|
| **podcast-creator** | `>=0.12.0,<1` | End-to-end podcast pipeline (outline → transcript → audio) invoked by `generate_podcast` command; resolves model-registry references + credentials for all speaker profiles first. (Pins `pillow<12`.) |
| **piper-tts** | `>=1.2.0,<2` | Local neural TTS sidecar (voice synthesis) spawned by the launcher; the maintained successor to the raw `piper` namespace. |
| **faster-whisper** | `>=1.1.0,<2` | Local speech-to-text sidecar (Whisper.cpp bindings) for audio/video source transcription + voice chat; models cached under `~/.cache/huggingface`. |
| **ElevenLabs** | via Esperanto credential | Optional cloud TTS provider (opt-in by key). |

---

## Memory

| Technology | Version | Role |
|---|---|---|
| **mem0ai** | `>=0.1.0,<2` | In-process memory layer. A `memory_retriever` sidecar instantiates `mem0.Memory` (validates the local chat LLM + embed endpoints at startup — hence launcher ordering). The chat node recalls facts/preferences (`recall_memory` / `render_memory_block`) into the system prompt and extracts facts on the write path. |
| **memory_recall / message_history** | in-repo (`utils/memory_recall.py`, `utils/message_history.py`) | Recency-vs-semantic recall orchestration (`ONP_MEMORY_RECALL_MODE`) and history trimming. |
| **OpenChronicle bridge** | in-repo (`desktop/` + `mcp/`), optional | Optional local personal-memory MCP bridge sidecar. |

---

## Web Search

| Technology | Version | Role |
|---|---|---|
| **web_search tool** | in-repo (`open_notebook/tools/web_search.py`) | Chat tool that only *exists* when a provider is configured (key-presence = opt-in). Precedence Serper > Tavily > SearXNG, overridable via `ONP_WEB_SEARCH_PROVIDER`. |
| **Serper** | `SERPER_API_KEY` | Google Search API backend. |
| **Tavily** | `TAVILY_API_KEY` | Search API backend. |
| **SearXNG** | `SEARXNG_BASE_URL` | Self-hosted, keyless search backend. |

---

## Model Context Protocol (MCP)

| Technology | Version | Role |
|---|---|---|
| **mcp** | `>=1.0.0` | MCP client; chat graph can call external MCP tools (web search, fetch, etc.) over streamable-HTTP. `open_notebook/mcp/` holds the registry, client, and curated `recommendations.py` (SearXNG/Crawl4AI). Tool output is fenced as untrusted before feeding the model. |

---

## Desktop Packaging & Shell

| Technology | Version | Role |
|---|---|---|
| **pywebview** | `==5.4` | Native window shell (WKWebView on macOS). `webview.create_window(..., js_api=_OnpJsApi)` shows a splash, then navigates to the frontend URL; `webview.start(private_mode=False, storage_path=...)` persists the WebKit data store; `_OnpJsApi.relaunch()` restarts the app. |
| **PyInstaller** | `>=6.13.0,<7` | Freezes the app to a **onedir** bundle (`EXE(exclude_binaries=True)` + `COLLECT` + macOS `BUNDLE`, bundle id `com.antman1526.open-notebook-plus`, `CFBundleName "Open notebook+"`). Spec: `desktop/build/pyinstaller.spec`. |
| **codesign** (Apple toolchain) | — | Makefile does an explicit final `codesign --force --deep --sign "$ONP_CODESIGN_IDENTITY"` (default ad-hoc `-`) after PyInstaller to fix invalid seals, then `codesign -v`. |
| **hdiutil** | — | `make build-mac-dmg` wraps the `.app` into an (unsigned) `.dmg`. |
| **aiohttp** | `>=3.11.18,<4` (CVE-2025-37960) | Async HTTP inside the desktop shell (`desktop/aiohttp_window.py`, sidecar/window handoff). |
| **Supervisor (in-repo)** | `desktop/launcher.py` | Custom process supervisor: dynamic-port allocation, dependency-ordered spawn, readiness gates, process-group teardown, singleton PID-lock + orphan reaper, per-sidecar `.tail` logs with secret redaction, periodic DB export, and boot-time DB repair. |
| **ControlServer** | `desktop/launcher_control.py` | Stdlib `ThreadingHTTPServer` on `127.0.0.1:<random>` with bearer-token auth; lets the API POST `/restart_sidecar` + `/hot_swap_chat` back into the launcher. |

---

## Frontend Framework & Libraries

| Technology | Version | Role |
|---|---|---|
| **Next.js** | `^16.2.3` | React framework; App Router; standalone server build (`node server.js`) whose baked API port the launcher patches at boot (`next_rewrites_patcher.py`). Server-side API proxy via rewrites. |
| **React** | `^19.2.3` | UI runtime. |
| **react-dom** | `^19.2.3` | DOM renderer. |
| **@xyflow/react** | `^12.11.1` | The notebook **mind-map** graph visualization (nodes/edges from `reference`/`artifact`). |
| **react-markdown** | `^10.1.0` | Renders chat/insight/note Markdown. |
| **remark-gfm / remark-math / rehype-katex** | `^4.0.1 / ^6.0.0 / ^7.0.1` | GitHub-flavored Markdown, math parsing, KaTeX math rendering in messages. |
| **@uiw/react-md-editor** | `^4.0.8` | Markdown editor for notes. |
| **react-pdf** | `^10.4.1` | In-app PDF source viewer (with citation-passage highlighting). |
| **react-hook-form** + **@hookform/resolvers** + **zod** | `^7.60.0 / ^5.1.1 / ^4.0.5` | Forms + schema validation (credentials, settings, source add). |
| **axios** | `^1.15.0` | HTTP client for non-streaming API calls (`apiClient`); streaming chat uses native `fetch` + `ReadableStream` instead (Axios can't expose the stream body). |
| **date-fns** | `^4.1.0` | Date formatting. |
| **use-debounce** | `^10.0.6` | Debounced inputs (search, context toggles). |
| **@tanstack/react-virtual** | `^3.13.24` | Virtualized long lists. |

---

## State & Data-Fetching

| Technology | Version | Role |
|---|---|---|
| **@tanstack/react-query** | `^5.83.0` | Server-state cache for notebooks/sources/notes/sessions/models/credentials; mutations invalidate query keys (some broad — a known pain point). Also caches MCP tool-call metadata via `setQueryData`. |
| **Zustand** | `^5.0.6` | Client UI state (auth token store, context selections, UI toggles). |
| **i18next** + **react-i18next** + **i18next-browser-languagedetector** | `^25.7.3 / ^16.5.0 / ^8.2.0` | Internationalization; all UI strings keyed. |

---

## UI / Styling

| Technology | Version | Role |
|---|---|---|
| **Tailwind CSS** | `^4` (+ `@tailwindcss/postcss`, `@tailwindcss/typography`) | Utility styling; typography plugin for Markdown prose. |
| **Radix UI** (accordion, alert-dialog, checkbox, collapsible, dialog, dropdown-menu, label, popover, progress, radio-group, scroll-area, select, separator, slot, tabs, tooltip) | various `^1–^2` | Headless accessible primitives underlying the shadcn-style component library. |
| **lucide-react** | `^0.525.0` | Icon set (e.g. cancel-run Square icon in ChatPanel). |
| **framer-motion** | `^12.42.0` | Animations/transitions. |
| **class-variance-authority / clsx / tailwind-merge** | `^0.7.1 / ^2.1.1 / ^3.3.1` | Conditional/variant class composition. |
| **cmdk** | `^1.1.1` | Command-palette / combobox. |
| **sonner** | `^2.0.6` | Toast notifications. |
| **next-themes** | `^0.4.6` | Dark/light theme switching. |
| **react-resizable-panels** | `^2.1.9` | Resizable notebook layout panels — **deliberately pinned to v2** (v4 broke the layout API). |
| **tw-animate-css** | `^1.3.5` (dev) | Animation utilities. |

---

## Build / Test / Tooling

| Technology | Version | Role |
|---|---|---|
| **uv** (Astral) | latest (Docker `ghcr.io/astral-sh/uv`) | Python dependency resolver/installer; `uv.lock` lockfile; `uv run pytest`, `uv run uvicorn`. |
| **pnpm / npm** | — | Frontend package manager (`frontend/package.json` scripts). |
| **Node.js** | 22.x LTS (Docker `setup_22.x`) | Frontend build + runtime; bundled per-arch node binary in desktop builds. |
| **Ruff** | `>=0.14.13` (dev) | Lint + import sort; selects `E,F,I,UP006,UP007` (PEP 585/604 modernization). |
| **mypy** | `>=1.11.1` (dev) | Static typing (`mypy.ini`; Streamlit pages excluded). |
| **pytest** | `>=9.0.3` + **pytest-asyncio** `>=1.2.0` (`asyncio_mode=auto`) | Backend tests (`tests/`, `desktop/tests/`); custom `integration_surreal` marker skips live-DB tests unless `SURREAL_INTEGRATION=1`. |
| **Vitest** | `^4.1.8` (+ `@vitest/ui`) | Frontend unit tests (`vitest run --pool=forks --maxWorkers=1`). |
| **@testing-library/react + jest-dom** | `^16.2.0 / ^6.6.3` | Component testing (e.g. `ChatPanel.*.test.tsx`, `chat-race-guard.test.ts`). |
| **jsdom** | `^26.0.0` | DOM environment for Vitest. |
| **@vitejs/plugin-react** | `^4.3.4` | React transform for Vitest. |
| **ESLint** + **eslint-config-next** + **@eslint/eslintrc** | `^9 / ^16.2.6 / ^3` | Frontend linting. |
| **@next/bundle-analyzer** | `^16.2.6` | `build:analyze` bundle inspection. |
| **pre-commit** | `>=4.1.0` (dev) | Git hooks (`.pre-commit-config.yaml`). |
| **isort** | `black` profile, line 88 | Import ordering config (also enforced via Ruff `I`). |
| **types-requests** | `>=2.32.4` (dev) | Type stubs. |
| **Make** | — | `Makefile` orchestrates the full mac build chain (test→lock→venv→frontend→runtimes→pyinstaller→dmg) + Docker release. |
| **GitHub Actions** | — | `.github/workflows/`: `build-desktop.yml` (macos-14 arm64 + macos-13 x64 + windows PyInstaller → release), `build-windows.yml`, `build-dev.yml`, `build-and-release.yml` (Docker image tagged from `pyproject` version), `test.yml`, `claude.yml` + `claude-code-review.yml`. |

---

## Deployment / Infra

| Technology | Version | Role |
|---|---|---|
| **Docker** | `python:3.12-slim-trixie` base | Server/self-host track (separate from the desktop app). `Dockerfile` (multi-stage) + `Dockerfile.single`; `.dockerignore`. |
| **docker-compose** | — | `docker-compose.yml` orchestrates SurrealDB + API + worker + frontend for the self-host profile. |
| **Supervisord** | — | In-container process manager (`supervisord.conf`, `supervisord.single.conf`): runs `uvicorn api.main:app`, the `surreal-commands-worker`, and the frontend `node server.js` (gated by `wait-for-api.sh`). |
| **softprops/action-gh-release** | `@v2` | Publishes desktop build artifacts to GitHub Releases. |
| **pycountry** + **babel** | `>=26.2.16 / >=2.18.0` | Podcast language list (`GET /languages`) — country/locale data. |
| **urllib3** | `>=2.7.0` (CVE-2026-44431/44432 pin) | Transitive HTTP dep. |

---

## Security & Crypto

| Technology | Version | Role |
|---|---|---|
| **cryptography / Fernet** | via crypto stack | Symmetric encryption of provider credentials (`open_notebook/utils/encryption.py`, `domain/credential.py`); requires `OPEN_NOTEBOOK_ENCRYPTION_KEY`. |
| **secrets** (stdlib) | — | Constant-time password compare (`api/auth.py`), 32-byte control-plane tokens, SurrealDB session creds via `token_urlsafe`. |
| **SSRF guard** (in-repo) | `credentials._validate_url()` | Validates provider URL fields, allowing localhost/private IPs for self-hosted services (Ollama/LM Studio) but blocking unexpected egress. |

---

## Third-Party APIs / Services (all opt-in)

- **LLM/embeddings/TTS providers** (via Esperanto credentials, encrypted in DB): OpenAI, Anthropic, Google Gemini, Groq, Mistral, DeepSeek, xAI, OpenRouter, Voyage (embeddings), ElevenLabs (TTS), Azure OpenAI, Google Vertex, and any `openai_compatible` endpoint.
- **Web search:** Serper, Tavily, SearXNG (`open_notebook/tools/web_search.py`).
- **Hugging Face Hub:** model snapshot downloads for local GGUF/MLX/whisper models.
- **MCP servers:** user-configured external tool servers over streamable-HTTP.

> Nothing above is contacted unless the corresponding key/URL/credential is present — the project's "default-off, key = opt-in" egress contract, enforced further by the offline + privacy gates.
