# Open notebook+

A desktop-app fork of [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook) focused on **local-first AI research notebooks** with a closed-loop memory layer, fail-closed cloud-privacy gating, agent-reliability state machine, end-to-end source ingestion + chat + podcast generation, complete observability, and **130+ production-hardening commits** on top of upstream.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![Python 3.11+ / 3.12](https://img.shields.io/badge/Python-3.11%20|%203.12-blue)
![Node 22](https://img.shields.io/badge/Node-22-green)
![Next.js 16](https://img.shields.io/badge/Next.js-16-black)
![FastAPI 0.104+](https://img.shields.io/badge/FastAPI-0.104%2B-009688)
![SurrealDB v2](https://img.shields.io/badge/SurrealDB-v2-ff5722)
![Tests](https://img.shields.io/badge/tests-1587%20backend%20%2B%20183%20frontend-success)
![Version](https://img.shields.io/badge/version-v0.8.65d-blue)

---

## What it does

Upload PDFs, audio, video, web pages, or text. Take notes. Chat with AI grounded in your sources. Run multi-step "Ask" synthesis across your library. Generate multi-speaker podcasts. **Memory** — facts and preferences automatically extracted from each chat persist across sessions. Everything runs locally if you want it to.

## Why Open notebook+ over NotebookLM?

v0.8.0 differentiators:

- **Local-first chat:** runs cloud-grade conversation against the GGUF model you put on your drive. No request leaves the machine when local is healthy and fits.
- **MCP servers:** plug in any Model Context Protocol server (web search, fetch, custom tools); the chat graph wires them into the LLM's tool surface automatically.
- **Smart routing:** opt-in `OPEN_NOTEBOOK_AUTO_ROUTE_CHAT` picks local vs cloud per turn based on context size and sidecar health — no manual switching.
- **Source-grounded citations:** every claim derived from your notebook documents or MCP tools renders as an interactive pill in the chat panel.
- **Full data ownership:** your notebook, sources, and chat history live in your SurrealDB, on your drive, behind a password you set.

## What's different from upstream

- **Native desktop app** — Mac `.dmg` (`make build-mac`). Windows builds on a Windows host (PyInstaller is not a cross-compiler). No Docker, no terminal.
- **Bundled SurrealDB + Node.js runtime** — single `.app`, no separate installs.
- **Local-model-first** — bundled `llama-cpp-python` + Ollama auto-detect + a **GGUF Manager** (HuggingFace download, hot-swap). Cloud APIs are opt-in.
- **Closed-loop memory (Phase 5.1)** — per-turn facts/preferences/episodes written to mem0/SurrealDB and recalled into every chat's system prompt, with **bounded retention** (`ONP_MEMORY_KEEP_PER_TABLE`), **batched extraction** (`ONP_MEMORY_BATCH_TURNS`), a **confidence floor** (`ONP_MEMORY_CONFIDENCE_FLOOR`), and **stored-prompt-injection sanitization**.
- **Fail-closed privacy gate (Phase 5.2)** — `ONP_PRIVACY_GATE` keeps turns containing detected secrets/PII **on the local model** instead of sending them to cloud (or blocks them), with an **interactive "On-device" review badge** + a consent **"Re-ask allowing cloud"** action. Optional pluggable model classifier for unstructured PII.
- **Agent-reliability FSM (Phase 5.3)** — `ONP_AGENT_FSM` lets the agent declare `clarify`/`complete`; the ask graph declines to synthesize ungrounded answers, and the chat tool loop surfaces `clarify`/`truncated` states in the UI.
- **Smart routing & MCP** — per-turn local/cloud routing (`OPEN_NOTEBOOK_AUTO_ROUTE_CHAT`) + per-conversation MCP tool servers.
- **Native web search (v0.8.64–65d)** — a built-in `web_search` chat tool, opt-in by key presence (`SERPER_API_KEY` / `TAVILY_API_KEY` / `SEARXNG_BASE_URL`), with a **failover chain** (multi-URL SearXNG + cross-provider on error, total-budget bounded), results rendered as citation pills, a **toggleable picker row**, and a ship-it-yourself **private localhost SearXNG** (`deploy/searxng-private/`) since public mirrors block the JSON API. Verified end-to-end with a local Ollama model calling it against live Serper.
- **Complete observability** — request-ID correlation, Prometheus `/metrics` (incl. privacy-gate + tool-loop counters), slow-query + checkpoint-prune + memory-recall metrics.
- **135+ production-hardening commits (v0.7.49 → v0.8.65d)** covering streaming cancellation, SSE disconnect handling, connection-pool race correctness, delete cascades, event-loop unblocking, encryption rotation + PBKDF2 KDF, local-LLM resilience, end-to-end timeout coverage, the Osaurus-inspired Phase 5 work, the native web-search subsystem, and CVE remediation across backend + frontend.

## Three-tier architecture

```
+--------------------------------------------------------+
|  Frontend  Next.js 16 + React 19 + TypeScript :3000    |
|  Zustand state, TanStack Query 5, Shadcn/ui + Tailwind |
+-----------------------+--------------------------------+
                        |  HTTP REST + NDJSON + SSE streams
+-----------------------v--------------------------------+
|  API       FastAPI 0.104 + Python 3.12 :5055           |
|  LangGraph 1.0 workflows, Esperanto 14-provider model  |
|  layer, surreal_commands job queue, Pydantic v2        |
|  Prometheus /metrics, request-ID middleware            |
+-----------------------+--------------------------------+
                        |  SurrealQL (AsyncSurreal pool)
+-----------------------v--------------------------------+
|  Database  SurrealDB v2 :8000                          |
|  Graph + vector + JSON + KV in one engine              |
|  HNSW indexes; native vector::similarity::cosine       |
+--------------------------------------------------------+

Desktop bundle additionally spawns:
  llama-cpp-python embed server (nomic-embed-text-v1.5)
  llama-cpp-python chat server  (Hermes-3 / Qwen2.5-Instruct)
  Whisper STT, Piper TTS, mem0 memory_shim, surreal_commands worker
```

## Install

### macOS (desktop app)

1. Download the `.dmg` from [Releases](https://github.com/Antman1526/open-notebook-Plus/releases)
2. Drag the app to **Applications**
3. **Right-click → Open** the first time (unsigned build; macOS Gatekeeper)

### Self-host (Docker Compose)

```bash
git clone https://github.com/Antman1526/open-notebook-Plus
cd open-notebook-Plus
cp .env.template .env                    # fill in passwords + encryption key
docker compose --profile multi up -d
# UI: http://localhost:3000, API: http://localhost:5055, Metrics: http://localhost:5055/metrics
```

### Local development

```bash
git clone https://github.com/Antman1526/open-notebook-Plus
cd open-notebook-Plus

# Backend
uv sync                                  # creates .venv via uv
cp .env.template .env                    # set SURREAL_*, OPEN_NOTEBOOK_PASSWORD, ENCRYPTION_KEY

# Frontend
cd frontend && npm ci && cd ..

# Run (3 terminals)
make database                             # terminal 1: SurrealDB via docker-compose
make api                                  # terminal 2: FastAPI :5055
make frontend                             # terminal 3: Next.js :3000
```

Run the test suites:

```bash
make test                                 # 594 hermetic backend tests + frontend
make test-integration                     # 6 SurrealDB integration tests (requires `make database`)
```

## First run

1. Open the app — the main UI launches at `http://localhost:3000`
2. Enter the password set in `OPEN_NOTEBOOK_PASSWORD` (if you set one)
3. Create a notebook, upload a source, chat about it
4. Visit Settings → Models to configure cloud providers (or use the bundled local models)

## Adding more local models

- Drop any `.gguf` file into `~/Desktop/AI_Models/GGUF/` — it appears in the picker on next launch.
- `ollama pull <name>` — Ollama-installed models show up under the Ollama section.

## Configuration

All env vars documented in [`CONFIGURATION.md`](CONFIGURATION.md). Critical minimum:

```bash
SURREAL_URL=ws://localhost:8000/rpc
SURREAL_USER=root
SURREAL_PASSWORD=root                            # CHANGE in production
SURREAL_NAMESPACE=open_notebook
SURREAL_DATABASE=production
OPEN_NOTEBOOK_PASSWORD=open-notebook-change-me   # CHANGE
OPEN_NOTEBOOK_ENCRYPTION_KEY=any-passphrase      # required to store credentials
# OR rotation form:
# OPEN_NOTEBOOK_ENCRYPTION_KEYS=new-key,old-key

# v0.7.123+ optional — switches encryption from raw-Fernet to PBKDF2-HMAC-SHA256 (600k iter):
# ONP_ENCRYPTION_KDF=pbkdf2

# v0.7.124+ optional — pushes /metrics auth-free for Prometheus scrapers:
# (just hit GET /metrics; no env var needed, but consider nginx auth_basic in front)

# v0.7.125+ optional — LangGraph SQLite checkpoint pruning:
# ONP_CHECKPOINT_KEEP_PER_THREAD=50
# ONP_CHECKPOINT_PRUNE_INTERVAL_HOURS=24

# v0.7.120+ optional — log + counter queries exceeding threshold:
# ONP_SLOW_QUERY_LOG_MS=500
```

## Observability

Every response carries an `X-Request-ID` header (UUID4 if not inbound). Every log line includes `req=<8-char-id>`. Hit `http://localhost:5055/metrics` for Prometheus exposition format:

```
# HELP http_requests_total HTTP requests
http_requests_total{method="GET",route="/notebooks/{notebook_id}",status="200"} 142
# HELP http_request_duration_seconds HTTP request latency
http_request_duration_seconds_bucket{le="0.05",method="POST",route="/chat/stream"} 38
# HELP db_query_duration_seconds DB query latency
db_query_duration_seconds_bucket{le="0.1"} 4823
# HELP db_slow_queries_total Queries exceeding ONP_SLOW_QUERY_LOG_MS
db_slow_queries_total 12
# HELP memory_recall_fallthrough_total Memory recall fell through to recency-only
memory_recall_fallthrough_total{reason="embed_timeout"} 3
# HELP checkpoint_prune_runs_total LangGraph checkpoint prune cycles
checkpoint_prune_runs_total 7
```

See [`16_v0.7.120_to_v0.7.129_Update.md`](../16_v0.7.120_to_v0.7.129_Update.md) for the full metric catalogue.

## Memory feature

The full memory loop is on by default in the desktop build:

```
Turn N completes
  → /chat/stream fires memory_extract_turn (fire-and-forget)
  → worker invokes Hermes-3 to parse facts/preferences
  → mem0 SurrealMemoryStore writes memory_fact / memory_preference

Turn N+1 starts
  → chat_graph calls recall_memory(query=last_user_message)
  → orchestrator picks recency (<30 rows) or semantic (vector::similarity::cosine)
  → renders into "# WHAT YOU REMEMBER ABOUT THE USER" section of system prompt

User deletes session
  → DELETE /chat/sessions/{id} fires memory_summarize_session BEFORE delete
  → writer produces one memory_episode record from the transcript
```

Configure via `ONP_MEMORY_RECALL_MODE = recent | semantic | auto`. All four memory-recall failure modes (`embed_timeout`, `embed_error`, `query_timeout`, `query_error`) emit Prometheus counters so you can see when recall falls through to recency-only.

## Backup & restore

```bash
make backup                                         # OUT=backups/onp-backup-<ts>.tar.gz
make backup OUT=path/to/backup.tar.gz                # explicit path
make verify-backup BUNDLE=path/to/backup.tar.gz      # integrity check only
make restore BUNDLE=path/to/backup.tar.gz            # refuses non-empty data/
make restore BUNDLE=path/to/backup.tar.gz FORCE=1    # nukes existing data/
```

Atomic `.tmp`-then-rename write semantics. SHA-256 manifest embedded in the tarball. 50 GB total cap, 1 GB per-file warning. Bundle format is versioned — a v1 backup will fail to restore on a future v2-only CLI to prevent silent corruption.

## Frontend bundle analysis

```bash
cd frontend && npm run build:analyze
open .next/analyze/client.html
```

Interactive treemap of the client bundle. Operator-facing guide at [`frontend/docs/BUNDLE_ANALYSIS.md`](frontend/docs/BUNDLE_ANALYSIS.md). Known lazy-load candidates already identified — operator chooses whether to wrap them in `dynamic()`.

## Building from source

**macOS** (produces `dist/Open-Notebook-Plus-mac-<arch>.dmg`, ~175 MB, unsigned —
first launch: right-click → Open to clear Gatekeeper):

```bash
make build-mac          # test → lockfile → build venv → Next.js build →
                        # fetch runtimes → PyInstaller → hdiutil dmg (~20–40 min first run)
open "dist/Open notebook+.app"
```

**Windows** (must run on a Windows host — PyInstaller is not a cross-compiler):

```powershell
cd frontend; npm ci; npm run build; cd ..
python desktop/build/fetch_runtimes.py
pyinstaller desktop/build/pyinstaller.spec
powershell -ExecutionPolicy Bypass -File desktop/build/post_build_windows.ps1
# Output: dist/open-notebook-Plus/
```

## Documentation

| Doc | Where |
|---|---|
| User documentation | [`docs/`](docs/) |
| Configuration | [`CONFIGURATION.md`](CONFIGURATION.md) |
| Backend architecture | [`open_notebook/CLAUDE.md`](open_notebook/CLAUDE.md) |
| Frontend architecture | [`frontend/src/CLAUDE.md`](frontend/src/CLAUDE.md) |
| API structure | [`api/CLAUDE.md`](api/CLAUDE.md) |
| Domain models | [`open_notebook/domain/CLAUDE.md`](open_notebook/domain/CLAUDE.md) |
| LangGraph workflows | [`open_notebook/graphs/CLAUDE.md`](open_notebook/graphs/CLAUDE.md) |
| AI / Esperanto integration | [`open_notebook/ai/CLAUDE.md`](open_notebook/ai/CLAUDE.md) |
| Database layer | [`open_notebook/database/CLAUDE.md`](open_notebook/database/CLAUDE.md) |
| Frontend bundle analysis | [`frontend/docs/BUNDLE_ANALYSIS.md`](frontend/docs/BUNDLE_ANALYSIS.md) |
| Release notes | [`desktop/CHANGELOG.md`](desktop/CHANGELOG.md) |
| Standing AI-agent workflow | [`CLAUDE.md`](CLAUDE.md) |
| Project-knowledge docs (15 reconstruction docs) | `~/Desktop/OpenNotebook/0[1-9]_*.md` + `1[0-6]_*.md` (outside the repo) |
| AI-reviewer context | `~/Desktop/OpenNotebook/open-notebook-Plus-AI-Context.md` |
| Full technology audit | `~/Desktop/OpenNotebook/open-notebook-Plus-Technology-Audit.md` |

## Hardening Summary (v0.7.49 → v0.8.65d)

135+ patch commits across the hardening run.

**v0.7.49 → v0.7.87** — original reliability sweep: streaming cancellation, SSE disconnect handling, connection-pool race correctness, delete cascades.

**v0.7.88 → v0.7.119** — structured outputs, filesystem I/O, end-to-end timeout coverage on every async LLM/embed/DB call, XSS hardening, `/healthz/deep`, encryption rotation, Studio multi-page notebooks.

**v0.7.120 → v0.7.129** — observability + supply chain + integration testing:

- **v0.7.120** — Request-ID middleware, GZip, security headers baseline, slow-query log, pre-commit hook
- **v0.7.121** — HSTS (HTTPS-only), Permissions-Policy, cookie hardening, prefers-reduced-motion + focus-visible
- **v0.7.122** — **23 CVEs closed** (16 backend + 7 frontend); 8 remaining are upstream-blocked (pillow via podcast-creator)
- **v0.7.123** — PBKDF2 key-derivation option (`ONP_ENCRYPTION_KDF=pbkdf2`, 600k iter)
- **v0.7.124** — Prometheus `/metrics` endpoint with 7 metric series; cardinality protection via route templates
- **v0.7.125** — LangGraph SQLite checkpoint pruning background loop (per-thread retention via `ROW_NUMBER() OVER (PARTITION BY ...)`)
- **v0.7.126** — Backup + restore tooling with atomic write + SHA-256 manifest + format versioning
- **v0.7.127** — Frontend bundle analyzer (`@next/bundle-analyzer`); operator-facing guide
- **v0.7.128** — Documented deferral of `studio.py` / `exports.py` split (CHANGELOG-only)
- **v0.7.129** — **Real-SurrealDB integration test fixture** that caught a real `Note.save()` bug on its first CI run; CI bumped to Node 24-era action versions; tests workflow now fires on `desktop-app` branch

**v0.7.130 → v0.8.49** — the **v0.8 local-first chat platform**: smart local/cloud routing (`pick_provider`), MCP per-conversation tool servers + picker, GGUF Manager (HuggingFace download / hot-swap / cancel-resume), launcher↔API control plane, plus a run of audit fixes (session-delete regression, notebook-delete checkpoint leak, memory prompt-injection sanitization, episode recall).

**v0.8.50 → v0.8.63** — the Osaurus-inspired **Phase 5** (all default-off):

- **5.1 memory** — retention ceiling (`ONP_MEMORY_KEEP_PER_TABLE`), batched extraction (`ONP_MEMORY_BATCH_TURNS`), confidence floor + persistence (`ONP_MEMORY_CONFIDENCE_FLOOR`).
- **5.2 privacy** — fail-closed gate (`ONP_PRIVACY_GATE`), optional model PII classifier (`ONP_PRIVACY_CLASSIFIER_URL`, `=auto`), gate decision surfaced on the chat response, interactive **On-device** review badge + **"Re-ask allowing cloud"** consent bypass.
- **5.3 agent FSM** — `ONP_AGENT_FSM`: core state machine, ask-graph ungrounded→clarify gate, chat tool-loop truncation observability + `<state>` clarify/complete classification, UI chips.

**v0.8.64 → v0.8.65d** — the **native web-search subsystem** (opt-in by key presence):

- **v0.8.64** — built-in `web_search` chat tool (`open_notebook/tools/web_search.py`) reading `SERPER_API_KEY` / `TAVILY_API_KEY` / `SEARXNG_BASE_URL`; wired into the chat tool loop, citation-pill compatible; prompt nudge so the LLM calls + cites it; conftest env isolation.
- **v0.8.65 / 65b** — failover chain (comma-separated multi-URL SearXNG + cross-provider on error; total-budget guard `ONP_WEB_SEARCH_TOTAL_BUDGET_SEC`); `web_search` surfaced as a toggleable row in the chat MCP picker (`GET /api/mcp/web-search`) with a tool-calling capability hint.
- **v0.8.65c** — `deploy/searxng-private/` (localhost-only SearXNG with the JSON API enabled) + [config guide](docs/5-CONFIGURATION/private-searxng-web-search.md), since public mirrors block `format=json`.
- **v0.8.65d** — decoupled `web_search` binding from MCP/DB failures (a SurrealDB blip during MCP lookup no longer drops web search). End-to-end verified: a local Ollama model called `web_search` against live Serper and produced a URL-cited answer.

### CI status at v0.8.65d

All Tests jobs green: **1587 backend tests + 183 frontend vitest tests** (+ SurrealDB integration tests). Workflow: [`/.github/workflows/test.yml`](.github/workflows/test.yml). See [`desktop/CHANGELOG.md`](desktop/CHANGELOG.md) Unreleased for per-commit detail.

## Support

- **Plus fork issues**: https://github.com/Antman1526/open-notebook-Plus/issues
- **Upstream issues**: https://github.com/lfnovo/open-notebook/issues
- **Upstream Discord**: https://discord.gg/37XJPXfz2w

## License

MIT (see [LICENSE](LICENSE)). Same license as upstream.

## Acknowledgements

This is a downstream fork. All upstream credit goes to [@lfnovo](https://github.com/lfnovo). The Plus delta is maintained by [@Antman1526](https://github.com/Antman1526).
