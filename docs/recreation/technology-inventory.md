# Technology Inventory — Open Notebook Plus

> Exhaustive audit of every language, framework, library, tool, database, service, and integration used in this codebase, with the **specific role each plays in this project**. Generated 2026-06-12. All secrets/credentials are redacted — only structure and key names are listed.

Open Notebook Plus is a desktop fork of `lfnovo/open-notebook`: a privacy-first, self-hosted research assistant (Notebook LM alternative). It is a **three-tier app** — Next.js frontend → FastAPI backend → SurrealDB — packaged as a **native desktop app** (pywebview + PyInstaller) that bundles its own Python, Node, SurrealDB, and local-model runtimes. The same code also ships as Docker images.

---

## 1. Languages

| Name | Version | Role in this project |
|------|---------|----------------------|
| Python | 3.11–3.12 (`requires-python >=3.11,<3.13`; `.python-version` = 3.12) | Backend API, LangGraph workflows, domain models, desktop launcher/shims, all tooling scripts |
| TypeScript | ^5 | Entire frontend (`frontend/src`), Next.js app router, hooks, components |
| JavaScript | — | Next.js runtime/build output, `start-server.js`, ESLint config |
| SurrealQL | — | DB schema migrations (`open_notebook/database/migrations/*.surrealql`), repository queries, vector search |
| Bash / Shell | — | `scripts/*.sh`, `dev-init.sh`, `desktop/build/post_build_mac.sh`, CI steps |
| PowerShell | — | `desktop/build/post_build_windows.ps1` (Windows packaging) |
| Jinja2 templates | — | AI prompt templates via ai-prompter (`prompts/`) |

---

## 2. Backend frameworks & runtime

| Name | Version | Role in this project |
|------|---------|----------------------|
| FastAPI | >=0.104.0 | REST API server (`api/`) @ port 5055 — notebooks, sources, notes, chat, podcasts, search, credentials, metrics endpoints |
| Uvicorn | >=0.24.0 | ASGI server running the FastAPI app (`run_api.py`, desktop launcher) |
| Starlette | (via FastAPI) | `BaseHTTPMiddleware` for `PasswordAuthMiddleware` (`api/auth.py`), CORS, middleware stack |
| Pydantic | >=2.9.2 (v2) | Request/response schemas (`api/models.py`), domain model validation, settings |
| Loguru | >=0.7.2 | Structured logging across backend and desktop (`open_notebook/logging.py`) |
| LangGraph | >=1.0.10 (CVE-2026-28277 remediation) | State-machine workflows: source ingest, chat, ask/search-synthesis, transformation (`open_notebook/graphs/`) |
| langgraph-checkpoint-sqlite | >=3.0.1 (lock 3.0.3) | Persists LangGraph workflow state to SQLite checkpoints (`/data/sqlite-db/`) |
| LangChain | >=1.2.0 | Core LLM abstractions consumed by graphs |
| langchain-core | >=1.3.3 (CVE-2026-44843) | Messages, runnables, base types used throughout graphs |
| langchain-community | >=0.4.1 | Community integrations / loaders |
| langchain-text-splitters | (via langchain) | Chunking source content before embedding |
| LangSmith | >=0.8.0 (CVE-2026-45134) | LangChain tracing/observability dependency |
| aiosqlite | 0.22.1 | Async SQLite driver backing LangGraph checkpointer |
| sse-starlette | 3.4.2 | Server-Sent Events for streaming chat responses |
| starlette-context | 0.3.6 | Required by `llama_cpp.server` `[server]` extra |
| prometheus-client | >=0.20.0 (lock 0.25.0) | `/metrics` endpoint (`api/metrics.py`) — histogram/counter instrumentation |
| python-multipart | >=0.0.27 (CVE-2026-42561) | Multipart file-upload parsing for source uploads |
| httpx[socks] | >=0.27.0 (desktop pin 0.28.1) | Async HTTP client (provider calls, MCP, web search, auto-register probes) |
| tiktoken | >=0.12.0 | Token counting for LLM context sizing (pre-cached `o200k_base` in Docker) |
| numpy | >=2.4.1 | Vector/embedding math, similarity ops |
| lxml | >=6.1.0 (CVE-2026-41066) | HTML/XML parsing (content extraction pipeline) |
| urllib3 | >=2.7.0 (CVE-2026-44431/44432) | Transitive HTTP transport, pinned for CVEs |
| tomli / tomllib | >=2.0.2 | TOML config parsing (`config.toml`, runtimes.toml) |
| python-dotenv | >=1.2.2 (CVE-2026-28684) | Loads `.env` environment config |
| babel | >=2.18.0 | Locale/date formatting for backend i18n |
| pycountry | >=26.2.16 | Country/language code lookups (podcast + locale features) |
| packaging | (transitive) | Version comparison in migration/runtime logic |

---

## 3. Frontend frameworks & libraries

| Name | Version | Role in this project |
|------|---------|----------------------|
| Next.js | ^16.2.3 | React framework / app router, dev+build, frontend @ port 3000 |
| React | ^19.2.3 | UI component runtime |
| React DOM | ^19.2.3 | DOM renderer |
| Zustand | ^5.0.6 | Global client state management |
| TanStack React Query | ^5.83.0 | Server-state data fetching/caching against the FastAPI REST API |
| TanStack React Virtual | ^3.13.24 | Virtualized long lists (sources/notes) |
| Axios | ^1.15.0 | HTTP client to the backend (`frontend/src/proxy.ts`, lib) |
| Radix UI (accordion, alert-dialog, checkbox, collapsible, dialog, dropdown-menu, label, popover, progress, radio-group, scroll-area, select, separator, slot, tabs, tooltip) | various ^1–^2 | Headless accessible primitives underpinning Shadcn/ui components |
| Shadcn/ui | (config `components.json`) | Component layer built on Radix + Tailwind |
| Tailwind CSS | ^4 | Styling system |
| @tailwindcss/postcss / @tailwindcss/typography | ^4 / ^0.5.16 | PostCSS pipeline + prose typography for rendered markdown |
| tw-animate-css | ^1.3.5 | Tailwind animation utilities |
| class-variance-authority | ^0.7.1 | Variant-based component styling |
| clsx / tailwind-merge | ^2.1.1 / ^3.3.1 | Conditional + de-duplicated className composition |
| lucide-react | ^0.525.0 | Icon set |
| next-themes | ^0.4.6 | Light/dark theme switching |
| sonner | ^2.0.6 | Toast notifications |
| cmdk | ^1.1.1 | Command palette / search menu |
| react-hook-form + @hookform/resolvers | ^7.60.0 / ^5.1.1 | Forms (settings, credentials, profiles) |
| zod | ^4.0.5 | Schema validation for forms and API payloads |
| @uiw/react-md-editor | ^4.0.8 | Markdown editor for notes |
| react-markdown + remark-gfm | ^10.1.0 / ^4.0.1 | Render markdown (chat, notes) with GitHub-flavored markdown |
| date-fns | ^4.1.0 | Date formatting |
| use-debounce | ^10.0.6 | Debounced inputs (search/autosave) |
| postcss | ^8.5.10 (override) | CSS processing |

---

## 4. Databases & storage

| Name | Version | Role in this project |
|------|---------|----------------------|
| SurrealDB (server) | 2.1.0 bundled (desktop) / `surrealdb/surrealdb:v2` (Docker), RocksDB storage | Primary database @ port 8000 — graph records (Notebook, Source, Note, ChatSession, Credential), edge tables (`reference`, `artifact`, `refers_to`), built-in vector embeddings + semantic search |
| surrealdb (Python driver) | >=1.0.4 | Async SurrealQL client / connection pooling (`open_notebook/database/`) |
| SQLite | (stdlib `sqlite3` / aiosqlite) | LangGraph checkpoint persistence |
| RocksDB | (inside SurrealDB) | On-disk storage engine for SurrealDB (`surreal_data/`, `rocksdb:` path) |
| Filesystem stores | — | Local model weights (GGUF), HuggingFace cache (`~/.cache/huggingface`), uploaded source files under `data/`, logs under `~/.open-notebook-plus/logs/` |
| AsyncMigrationManager | (in-repo) | Runs `*.surrealql` migrations 1–22 automatically on API startup |

---

## 5. AI / ML — providers, model runtimes, libraries

### Provider abstraction & cloud providers

| Name | Version | Role in this project |
|------|---------|----------------------|
| Esperanto | >=2.20.0,<3 | Unified multi-provider AI interface (LLM/embeddings/STT/TTS) used by ModelManager |
| langchain-openai | >=1.1.14 | OpenAI + OpenAI-compatible chat/embeddings |
| langchain-anthropic | >=1.3.0 | Anthropic Claude models |
| langchain-google-genai | >=4.1.2 (lock 4.2.2) | Google Gemini models |
| google-genai | 1.75.0 (transitive) | Google GenAI SDK under langchain-google-genai |
| langchain-groq | >=1.1.1 | Groq inference |
| langchain-mistralai | >=1.1.1 | Mistral models |
| langchain-deepseek | >=1.0.0 | DeepSeek models |
| langchain-ollama | >=1.0.1 | Ollama local models |
| (Esperanto provider ids) | — | Connection tester / provisioning also targets: openai, anthropic, google, groq, ollama, mistral, deepseek, **xAI**, **ElevenLabs** (TTS), **Voyage** (embeddings), **Vertex** |

### Local model runtimes (desktop-bundled)

| Name | Version | Role in this project |
|------|---------|----------------------|
| llama-cpp-python[server] | >=0.3.16,<0.4 (CVE-2024-42479) | Local GGUF chat + embedding inference via OpenAI-compatible `llama_cpp.server` (ports auto-registered) |
| gguf | (lib) | Parse GGUF model metadata/inventory (`open_notebook/local_models/gguf_metadata.py`) |
| Ollama | (external, auto-registered) | Detected local Ollama server; registered as a provider (`desktop/providers/ollama.py`) |
| Osaurus | (external, `brew install --cask osaurus`, port 1337) | Native macOS/Apple-Silicon MLX OpenAI-compatible local server, auto-registered (`desktop/auto_register/osaurus.py`) |
| faster-whisper | >=1.1.0,<2 | Local speech-to-text (CTranslate2 Whisper), OpenAI-compatible shim (`desktop_shims/whisper_shim.py`) |
| piper-tts | >=1.2.0,<2 | Local text-to-speech (ONNX voices), OpenAI-compatible shim (`desktop_shims/piper_shim.py`) |
| mem0ai (mem0) | >=0.1.0,<2 | In-process memory layer — chat session summarizer + fact extractor; custom **SurrealDB VectorStoreBase adapter** (`desktop/memory/surreal_store.py`) |
| skillopt | >=0.1.0,<0.2 | Prompt optimizer (microsoft/SkillOpt, MIT) — `open_notebook/prompt_optimizer/` |

### Content extraction / ML support

| Name | Version | Role in this project |
|------|---------|----------------------|
| content-core | >=1.14.1,<2 | File/URL content extraction (50+ file types) feeding the source-ingest graph |
| crawl4ai | (via content-core / web tools) | Web page crawling/extraction (`open_notebook/utils/crawler.py`, `tools/add_web_source.py`) |
| pymupdf | (transitive) | PDF text/image extraction |
| beautifulsoup4 | (transitive) | HTML parsing in extraction |
| youtube-transcript-api / pytubefix | (transitive) | YouTube transcript + video handling |
| moviepy | (transitive) | Audio/video media processing |
| firecrawl-py | (transitive) | Web scraping backend option |
| pillow (PIL) | <12.0 (pinned by podcast-creator; 6 CVEs noted/blocked) | Image handling for extracted PDF/DOCX images |
| ai-prompter | >=0.4,<1 | Jinja2-templated AI prompt construction (`prompts/`) |
| podcast-creator | >=0.12.0,<1 | End-to-end podcast generation (profiles, TTS, retry) |

---

## 6. Job queue & async

| Name | Version | Role in this project |
|------|---------|----------------------|
| surreal-commands | >=1.3.1,<2 | Async job queue backed by SurrealDB — podcast generation, long-running commands; polled via `/commands/{id}` |
| asyncio | (stdlib) | Async-first design; `asyncio.to_thread` wraps sync `submit_command` calls |
| Custom digest scheduler | (in-repo) | `open_notebook/digest/scheduler.py` — periodic Gmail digest with failure backoff |

---

## 7. Build, packaging & deployment

| Name | Version | Role in this project |
|------|---------|----------------------|
| uv (Astral) | 0.5.11 bundled / `astral-sh/uv:latest` in Docker | Python dependency resolution & install (`uv.lock`, `uv sync`) |
| setuptools | >=61.0 | Python build backend (`pyproject.toml`) |
| PyInstaller | >=6.13.0,<7 | Bundles desktop app into native `.app`/`.exe` (`desktop/build/pyinstaller.spec`) |
| pywebview | 5.4 | Native desktop webview window hosting the Next.js UI (`desktop/window.py`, `aiohttp_window.py`) |
| aiohttp | >=3.11.18,<4 (CVE-2025-37960) | Local static server / window plumbing in desktop launcher |
| python-build-standalone (CPython) | 3.12.8 (20241206) | Bundled portable Python runtime for the desktop app |
| Node.js | 20.18.0 bundled / 20.x in Docker (CI on Node 24) | Frontend build + bundled `node` runtime for desktop |
| npm | (via package-lock.json) | Frontend dependency install/build (`npm ci`, `npm run build`) |
| Next.js build (Webpack/Turbopack) | ^16 | Frontend production build; `@next/bundle-analyzer` for analysis |
| Docker / docker compose | — | Multi-stage `Dockerfile`, `Dockerfile.single`, `docker-compose.yml` (surrealdb + app) |
| docker buildx | — | Multi-platform image builds (`make docker-release`) |
| supervisord | (`supervisord.conf`, `.single.conf`) | Process supervision in single-container Docker image |
| create-dmg / codesign / notarytool | (macOS, post_build_mac.sh) | macOS DMG packaging, code signing, notarization |
| Makefile | — | Orchestrates dev, docker, mypy, export-docs, tag targets |
| GitHub Actions | — | `build-and-release.yml`, `build-desktop.yml`, `build-dev.yml`, `test.yml`, `claude*.yml` |
| Ralph Loop | (`scripts/ralph.sh`, `.ralph/`) | Autonomous self-correcting dev loop harness |

---

## 8. Testing

| Name | Version | Role in this project |
|------|---------|----------------------|
| pytest | >=9.0.3 (desktop pin 8.3.4) | Backend + desktop test suites (`tests/`, `desktop/tests/`) |
| pytest-asyncio | >=1.2.0 (desktop 0.24.0); `asyncio_mode=auto` | Async test support; custom `integration_surreal` marker (live SurrealDB, opt-in) |
| Vitest | ^4.1.8 | Frontend unit tests (`vitest.config.ts`, forks pool) |
| @vitest/ui | ^4.1.8 | Vitest interactive UI |
| @testing-library/react + jest-dom | ^16.2.0 / ^6.6.3 | React component testing + DOM matchers |
| jsdom | ^26.0.0 | DOM environment for Vitest |
| @vitejs/plugin-react | ^4.3.4 | React transform for Vitest |
| types-requests | >=2.32.x | Type stubs for mypy |

---

## 9. Dev tooling

| Name | Version | Role in this project |
|------|---------|----------------------|
| Ruff | >=0.14.13 (pre-commit v0.7.0) | Lint + format Python (rules E/F/I/UP006/UP007, line-length 88) |
| mypy | >=1.11.1 | Static type checking (`mypy.ini`, excludes Streamlit `pages.*`) |
| isort | (black profile, len 88) | Import ordering config |
| pre-commit | >=4.1.0 | Git hook runner: ruff, check-yaml/json/toml, EOL/whitespace, merge-conflict, large-file guard |
| ESLint | ^9 + eslint-config-next ^16.2.6 | Frontend linting (`eslint.config.mjs`) |
| TypeScript compiler | ^5 | Type checking frontend (`tsconfig.json`) |
| ipykernel / ipywidgets | >=6.29.5 / >=8.1.5 | Jupyter dev/notebook support (dev extra) |
| @types/node, @types/react, @types/react-dom | ^20 / ^19 | TS type definitions |

---

## 10. Desktop / native

| Name | Version | Role in this project |
|------|---------|----------------------|
| pywebview | 5.4 | Native window wrapper for the web UI |
| PyObjC (AppKit, CoreFoundation) | (macOS) | Native macOS tray, window state, splash (`desktop/tray.py`, `splash.py`) |
| tkinter | (stdlib) | Fallback/simple desktop UI elements (splash/first-run) |
| psutil | (lib) | Process/port management in launcher (`desktop/ports.py`, singleton) |
| plistlib / winreg | (stdlib) | macOS plist + Windows registry handling for install/launch |
| cryptography (Fernet / MultiFernet) | (lib) | Encrypts Credential records & Gmail OAuth tokens; optional PBKDF2-HMAC-SHA256 KDF via `ONP_ENCRYPTION_KDF=pbkdf2` (`open_notebook/utils/encryption.py`) |
| db_repair / singleton / launcher | (in-repo) | DB repair, single-instance lock, port allocation, model downloads, first-run server |

---

## 11. Third-party APIs & external services

| Name | Endpoint / detail | Role in this project |
|------|-------------------|----------------------|
| Serper | `https://google.serper.dev/search` (`SERPER_API_KEY`) | Web search provider (highest precedence) for chat web-search tool |
| Tavily | `https://api.tavily.com/search` (`TAVILY_API_KEY`) | Web search provider (2nd precedence) |
| SearXNG | self-hosted, `SEARXNG_BASE_URL` (e.g. `http://127.0.0.1:8080`) | Keyless self-hosted meta-search provider (3rd precedence); private compose stack in `deploy/searxng-private/` |
| Google Gmail API | OAuth2 (user-provided client config) | Gmail digest integration — encrypted OAuth tokens, proactive refresh (`open_notebook/domain/gmail.py`, `digest/`) |
| OpenAI / Anthropic / Google / Groq / Mistral / DeepSeek / xAI / ElevenLabs / Voyage / Vertex | provider APIs (user credentials) | Cloud LLM, embedding, and TTS providers via Esperanto |
| Hugging Face Hub | model download / `~/.cache/huggingface` | Source of faster-whisper, piper, and GGUF model assets |
| Docker Hub / GHCR | `lfnovo/open_notebook` | Image registries for release builds |

> All API keys/secrets are stored encrypted (Fernet) in SurrealDB Credential records or read from env; none are committed. `.env` / `config.toml` values are redacted here.

---

## 12. Integrations (MCP & tools)

| Name | Version | Role in this project |
|------|---------|----------------------|
| MCP (Model Context Protocol) client | mcp >=1.0.0 | Chat graph calls external MCP servers (web search, fetch) via streamable-http (`open_notebook/mcp/`) |
| fastmcp | >=3.0,<4 | MCP bridge used by OpenChronicle shim (`desktop_shims/openchronicle_shim.py`) |
| MCP registry / recommendations | (in-repo) | Curated MCP server catalog with default localhost URLs + install links: SearXNG, Crawl4AI (`:11235`), Microsoft Playwright MCP (`:8931`) |
| OpenChronicle | (MCP bridge) | External chronicle/memory MCP integration via desktop shim |
| opencode tool | (`open_notebook/tools/opencode.py`) | Code-related agent tool |
| web_search / add_web_source tools | (in-repo) | Backend chat tools wrapping the search providers + crawl4ai |

---

## 13. Internationalization (i18n)

| Name | Version | Role in this project |
|------|---------|----------------------|
| i18next | ^25.7.3 | Frontend translation framework |
| react-i18next | ^16.5.0 | React bindings for translations (locale files under `frontend/src/lib/locales/`) |
| i18next-browser-languagedetector | ^8.2.0 | Auto-detect user language in the browser |
| Babel (Python) | >=2.18.0 | Backend locale/date formatting |
| pycountry | >=26.2.16 | Language/country code resolution |

---

## 14. Misc utilities

| Name | Source | Role in this project |
|------|--------|----------------------|
| markdown-it-py | (lib) | Markdown rendering/parsing on backend |
| requests + types-requests | (lib) | Sync HTTP in scripts/tools |
| Jinja2 | 3.1.6 | Templating engine (ai-prompter, prompts) |
| secrets / hashlib / hmac | stdlib | Constant-time password compare, token/key derivation |
| ipaddress | stdlib | SSRF defense / URL host validation in web fetch |
| wave / struct | stdlib | WAV audio assembly in Piper TTS shim |
| tarfile / zipfile | stdlib | Runtime/asset extraction in desktop bootstrap |
| catalog.json (model_manager) | in-repo | Local model catalog keyed by `chat`, `embedding`, `stt`, `tts` |
| benchmark_models / backup_restore / export_docs | `scripts/` | Model benchmarking, DB backup/restore, docs export utilities |

---

### Notes on redaction & accuracy
- `.env`, `.env.example`, and any `config.toml` contained secrets and OAuth client values — **only key names and structure are referenced; no values copied.**
- Version numbers reflect declared constraints in `pyproject.toml` / `desktop/requirements.txt` and resolved pins in `desktop/requirements.lock` / `uv.lock` where checked.
- Provider list confirmed against `open_notebook/ai/connection_tester.py` (includes xAI, ElevenLabs, Voyage, Vertex beyond the langchain-* packages).
