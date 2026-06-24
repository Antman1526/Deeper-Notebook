# 01 — Project Overview & Architecture

> Recreation documentation for **Open Notebook Plus** (`open-notebook-Plus`), a
> desktop-app fork of [`lfnovo/open-notebook`](https://github.com/lfnovo/open-notebook).
> This document describes the high-level system design so another engineer (or AI)
> can rebuild the architecture from scratch. Companion docs:
> [`02-environment-setup-dependencies.md`](./02-environment-setup-dependencies.md)
> and [`03-database-schema-data-models.md`](./03-database-schema-data-models.md).
>
> **Secrets policy:** every key / password / token in this document is a
> placeholder (`<YOUR_KEY>`). Never commit real `.env` values.

---

## 1. What it is

Open Notebook Plus is a **privacy-first, local-first alternative to Google
NotebookLM**. Users upload PDFs, audio, video, web pages, or text; take notes;
chat with an AI grounded in their own sources; run multi-step "Ask" synthesis
across their library; generate multi-speaker podcasts; and turn videos, audio,
PDFs, documents, and links into instructor-ready **Course Packs** through Evidence
Studio. A closed-loop memory layer extracts facts/preferences from each chat and
recalls them into future sessions. Everything can run **entirely on the host
machine** — no request leaves the device when the local model is healthy.

Project version at the time of writing: **`pyproject.toml` reports `1.8.5`** (the
upstream package version), while the desktop fork tracks its own build string
(`v0.8.67w` in `README.md`). The Python package name is `open-notebook`.

Two ways to run it:

1. **Native desktop app** — a macOS `.dmg` (built with `make build-mac`) or a
   Windows local-dev install. The desktop bundle ships SurrealDB, a Node.js
   runtime, a Python-standalone runtime, and local llama.cpp / MLX model servers. It
   **never runs in Docker**.
2. **Self-host** — `docker compose up -d` (legacy path) or a 3-terminal local
   dev workflow (SurrealDB + FastAPI + Next.js).

---

## 2. Three-tier architecture

The system is a classic three-tier stack. Source of truth:
`README.md`, root `CLAUDE.md`, and the running services.

```
+--------------------------------------------------------------+
|  FRONTEND   Next.js 16 + React 19 + TypeScript    :3000      |
|  - Zustand state, TanStack Query 5                           |
|  - Shadcn/ui (Radix primitives) + Tailwind CSS 4            |
|  - Notebooks / sources / notes / chat / podcasts / search UI |
+----------------------------+---------------------------------+
                             |  HTTP REST + NDJSON + SSE streams
                             v
+--------------------------------------------------------------+
|  API        FastAPI 0.104+ on Python 3.12         :5055      |
|  - LangGraph 1.0 workflow orchestration (chat/ask/source...) |
|  - Esperanto multi-provider model layer (14+ providers)      |
|  - surreal_commands async job queue (podcasts, embeds)       |
|  - Pydantic v2 validation, Loguru logging                    |
|  - Prometheus /metrics, X-Request-ID middleware              |
+----------------------------+---------------------------------+
                             |  SurrealQL over AsyncSurreal (ws://)
                             v
+--------------------------------------------------------------+
|  DATABASE   SurrealDB v2                            :8000     |
|  - Graph + document + vector + KV in one engine              |
|  - HNSW vector indexes (DIMENSION 768)                       |
|  - native vector::similarity::cosine, BM25 full-text         |
+--------------------------------------------------------------+
```

The same diagram is mirrored in `CLAUDE.md` (root) and `open_notebook/CLAUDE.md`.

### Default ports

| Service     | Dev port | Notes |
|-------------|----------|-------|
| Frontend    | `3000`   | `make frontend` / `npm run dev` |
| API         | `5055`   | `make api` → `uv run --env-file .env run_api.py` |
| SurrealDB   | `8000`   | `make database` → `docker compose up -d surrealdb` |
| Legacy Streamlit UI | `8502` | Docker-only legacy path |

In the **desktop bundle**, ports are not fixed — the launcher allocates 9 free
ports atomically at startup via `desktop/ports.py::find_free_ports(9)` (surreal,
api, frontend, embed, whisper, piper, chat-llm, memory, openchronicle). See §4.

---

## 3. Component relationships

```
                         frontend/src/lib/api/*  (axios clients)
                                   |
                                   v
   frontend (Next.js)  --rewrites-->  /api/*  --->  api/main.py (FastAPI)
                                                       |
        +----------------------------------------------+-------------------+
        |                         |                    |                   |
        v                         v                    v                   v
  api/routers/*.py         api/*_service.py     open_notebook/graphs/*  open_notebook/
  (thin HTTP layer)        (orchestration)      (LangGraph workflows)   domain/*.py
        |                         |                    |                   |
        +-------------------------+--------------------+-------------------+
                                  |
                                  v
                 open_notebook/database/repository.py
                 (repo_query / repo_create / repo_relate / ...)
                                  |
                                  v
                          SurrealDB (graph DB)
```

Key layering rules (from `api/CLAUDE.md`, `open_notebook/CLAUDE.md`):

- **Routers** (`api/routers/*.py`) are thin: parse request → call a service →
  shape the HTTP response. Registered in `api/main.py` via `app.include_router(...)`
  under the `/api` prefix.
- **Services** (`api/*_service.py`, e.g. `chat_service.py`, `podcast_service.py`,
  `credentials_service.py`) own orchestration and call into domain models and
  LangGraph workflows.
- **Domain models** (`open_notebook/domain/*.py`) are Pydantic models bound to
  SurrealDB tables via the repository layer. Two base classes:
  - `ObjectModel` — mutable records (notebook, source, note, chat_session,
    model, credential…).
  - `RecordModel` — singleton config rows (ContentSettings, DefaultPrompts).
- **Repository** (`open_notebook/database/repository.py`) is the only place that
  speaks SurrealQL. No connection pooling — each `repo_*` call opens and closes a
  connection via the `db_connection()` async context manager.
- **AI layer** (`open_notebook/ai/`) wraps Esperanto's `AIFactory` and resolves
  model selection + credentials (`models.py`, `provision.py`, `key_provider.py`,
  `router.py`, `offline_gate.py`, `privacy_gate.py`).

---

## 4. Desktop launcher + sidecars

The desktop app is a Python process (entry `desktop/__main__.py` → `desktop/app.py`
→ `desktop/launcher.py`) that renders a `pywebview` window pointing at the local
Next.js frontend, and **supervises a tree of child processes ("sidecars")**.

Spawn orchestration lives in `desktop/launcher.py` (`Supervisor.start_all`). At
startup it allocates 9 ports and spawns:

| Sidecar | Spawn method | Command (paraphrased from `launcher.py`) | Purpose |
|---------|--------------|------------------------------------------|---------|
| SurrealDB | `_spawn_surreal(port)` | bundled `surreal` binary, RocksDB store | Database engine |
| FastAPI   | `_spawn_api(port)`     | `run_api.py` via bundled venv python | REST/SSE API |
| Next.js   | `_spawn_next(port)`    | Node standalone server, `PORT=<frontend_port>` | Frontend |
| llama.cpp **embed** | `_spawn_llamacpp_embed(port)` | `python -m llama_cpp.server --model <nomic-embed> --embedding true --n_gpu_layers ...` | Embeddings (nomic-embed-text-v1.5, 768-dim) |
| llama.cpp **chat**  | `_spawn_llamacpp_chat(port)`  | `python -m llama_cpp.server --model <chat.gguf> --n_ctx <auto> --n_gpu_layers ...` | Local chat LLM (Hermes-3 / Qwen2.5-Instruct / Llama-3.2) |
| MLX **chat** | `desktop/providers/mlx.py` | `python -m mlx_lm.server --model <AI_Models/MLX/repo> --host 127.0.0.1 --port <free>` | Apple-Silicon local OpenAI-compatible chat |
| Whisper STT | `_spawn_whisper(port)` | `python -m desktop_shims.whisper_shim --model <name>` | Speech-to-text (faster-whisper) |
| Piper TTS   | `_spawn_piper(port)`   | `python -m desktop_shims.piper_shim --voice name=<path> ...` | Text-to-speech |
| Memory      | `_spawn_memory_retriever(...)` | mem0-backed memory shim | Fact/preference/episode recall |
| OpenChronicle | `_spawn_openchronicle(...)` | `desktop_shims/openchronicle_shim.py` (MCP bridge) | Optional MCP integration |

Reference (verbatim) — the embed sidecar spawn, `desktop/launcher.py:1599`:

```python
def _spawn_llamacpp_embed(self, port: int) -> None:
    if self.nomic_embed_path is None or not self.nomic_embed_path.exists():
        return  # silently skip; embeddings just won't work this session
    args = [
        str(self.venv_python), "-m", "llama_cpp.server",
        "--model", str(self.nomic_embed_path),
        "--host", "127.0.0.1", "--port", str(port),
        "--embedding", "true",
        # v0.8.67c — GPU-offload the embedder too (Metal on Apple Silicon).
        "--n_gpu_layers", _n_gpu_layers("ONP_EMBED_N_GPU_LAYERS"),
    ]
    self._spawn(args, cwd=self.upstream_root, name="llamacpp_embed")
```

And the chat sidecar (`desktop/launcher.py:1939`):

```python
args = [
    str(self.venv_python), "-m", "llama_cpp.server",
    "--model", str(self.chat_llm_path),
    "--host", "127.0.0.1", "--port", str(port),
    "--n_ctx", n_ctx,                     # auto-detected from GGUF metadata
    "--n_gpu_layers", _n_gpu_layers("ONP_CHAT_LLM_N_GPU_LAYERS"),  # -1 = all on macOS
]
```

### Sidecar wiring (env handed to the API)

`start_all` builds a shared `session_env` dict and exports the sidecar URLs to
the API process (`desktop/launcher.py:~373`), e.g.:

```python
"SURREAL_URL":      f"ws://127.0.0.1:{surreal_port}/rpc",
"API_PORT":         str(api_port),
"MEMORY_CHAT_LLM_URL":  f"http://127.0.0.1:{chat_llm_port}/v1",
"MEMORY_EMBED_URL":     f"http://127.0.0.1:{embed_port}/v1",
"MEMORY_SURREAL_URL":   f"ws://127.0.0.1:{surreal_port}/rpc",
```

> **Gotcha baked into the code (`launcher.py:~379`):** `PORT` is deliberately
> *not* placed in the shared `session_env`. `llama_cpp.server` and other
> uvicorn-based children read `PORT` from the environment, so a shared `PORT`
> caused the embed server to bind the frontend's port. `PORT` is now passed
> **only** to the Next.js spawn.

### GPU offload helper

`_n_gpu_layers(env_name)` (`launcher.py:42`) resolves `--n_gpu_layers`: defaults
to `-1` (all layers) on macOS (Metal), `0` (CPU) elsewhere, overridable per
sidecar via the named env var without a rebuild.

### Context-length autodetection

`_detect_gguf_context_length(gguf_path)` (`launcher.py:1639`) reads the
`<arch>.context_length` GGUF metadata field without loading the whole model, so
`n_ctx` matches what the model advertises (e.g. Hermes-3 → 131072), capped by
`ONP_CHAT_LLM_CTX_MAX` for RAM safety. Falls back to `32768` on any parse error.

### Port allocation

`desktop/ports.py::find_free_ports(n)` binds `n` probe sockets with
`SO_REUSEADDR` simultaneously (held until return) and de-duplicates the result,
re-probing up to `_MAX_REPROBE_ATTEMPTS = 5` times to avoid a race where the OS
hands the same ephemeral port to two sockets.

### Desktop config

`desktop/config.py` defines a frozen `Config` dataclass persisted to
`~/.open-notebook-plus/config.toml` (mode `0o600`, parent dir `0o700`). Fields:
`model_dir`, `provider` (`ollama` | `llamacpp` | `none`), `default_model`,
`surreal_user`, `surreal_password`, `theme`, `openchronicle_choice`,
`encryption_key` (auto-generated `secrets.token_urlsafe(32)` if absent). The
default `model_dir` is `~/Desktop/AI_Models` (`desktop/config.py::default_model_dir`).
GGUF models are expected under `~/Desktop/AI_Models/GGUF/`; complete MLX model
repositories are expected under `~/Desktop/AI_Models/MLX/`.

> Path resolution is centralized in `desktop/paths.py::user_home()` —
> `$HOME` → `$USERPROFILE` → `Path.home()` — to guarantee a writable home dir
> on every OS (Windows installs put the `.exe` in a read-only `Program Files`).

---

## 5. LangGraph workflow patterns

All AI workflows are LangGraph `StateGraph`s living in `open_notebook/graphs/`.
Each defines a `TypedDict` state, node coroutines, edges, and compiles with a
checkpointer. They all resolve models through `provision_langchain_model()` /
`provision_langchain_chat_model()` (`open_notebook/ai/provision.py`).

### `chat.py` — conversational agent

State + graph (`open_notebook/graphs/chat.py:69,916`):

```python
class ThreadState(TypedDict):
    messages: Annotated[list, add_messages]
    notebook: Optional[Notebook]
    context: Optional[str]
    # ... routing / memory / tool-loop fields

agent_state = StateGraph(ThreadState)
agent_state.add_node("agent", call_model_with_messages)
agent_state.add_edge(START, "agent")
agent_state.add_edge("agent", END)
graph = agent_state.compile(checkpointer=memory)            # sync SqliteSaver
_async_graph = agent_state.compile(checkpointer=async_memory)  # AsyncSqliteSaver
```

Notable patterns:
- **Dual checkpointers** — a sync `SqliteSaver` for `asyncio.to_thread(graph.get_state)`
  reads and an `AsyncSqliteSaver` for the `astream_events` / `ainvoke` streaming
  path. Both point at the **same** SQLite file (`LANGGRAPH_CHECKPOINT_FILE`).
- **Message-history trimming** — `add_messages` is append-only, so each turn the
  graph trims history to `ONP_CHAT_HISTORY_CHAR_CAP` (default `12_000` chars ≈
  3,000 tokens) via `trim_message_history`.
- **Memory recall** — `recall_memory(query=last_user_message)` +
  `render_memory_block` inject a "WHAT YOU REMEMBER ABOUT THE USER" block into
  the system prompt.
- **Smart routing / privacy gate / MCP tools** — opt-in per-turn local-vs-cloud
  routing (`open_notebook/ai/router.py`), fail-closed privacy gate
  (`privacy_gate.py`), and DB-backed MCP tool servers resolved per conversation.

### `ask.py` — search + synthesis

Multi-node graph (`open_notebook/graphs/ask.py:348`):

```python
agent_state = StateGraph(ThreadState)
agent_state.add_node("agent", call_model_with_messages)        # plan queries
agent_state.add_node("provide_answer", provide_answer)         # per-query subgraph
agent_state.add_node("write_final_answer", write_final_answer) # synthesize
agent_state.add_edge(START, "agent")
agent_state.add_edge("provide_answer", "write_final_answer")
agent_state.add_edge("write_final_answer", END)
```

The "Ask" flow plans search queries, fans out into a `provide_answer` subgraph
(`SubGraphState`), then synthesizes a final grounded answer. Per-node timeouts
(`_ask_node_timeout_sec`) and an optional agent-reliability FSM (`_agent_fsm_enabled`,
`open_notebook/graphs/agent_fsm.py`) let the agent decline to synthesize an
ungrounded answer (declare `clarify` / `complete`).

### Other graphs

- `source.py` — content ingestion: extract → embed → save.
- `source_chat.py` — chat scoped to a single source.
- `transformation.py` — run reusable transformation prompts over content.
- `prompt.py`, `tools.py` — prompt assembly + tool definitions.

---

## 6. Async job queue (`surreal_commands`)

Long-running work (podcast generation, embedding, insight creation) is **not**
done inline. It is submitted to the `surreal_commands` library, which persists a
`command` record in SurrealDB and runs a worker process. Patterns:

- `Source.vectorize()` returns a `command_id` and does **not** wait
  (fire-and-forget).
- `Note.save()` auto-submits an `embed_note` command.
- `PodcastEpisode.command` links the episode to its `surreal_commands` job;
  `get_job_status()` / `get_job_detail()` poll status.
- **Critical concurrency rule** (root `CLAUDE.md`): the sync
  `surreal_commands.submit_command` must be wrapped in `asyncio.to_thread(...)`
  when called from `async def`, or it blocks the event loop.

The worker is started via `make worker` / `make worker-start` (or as a desktop
sidecar). Podcast commands use `retry={"max_attempts": 1}` to avoid duplicate
episode records; retries are user-initiated (`POST /podcasts/episodes/{id}/retry`).

---

## 7. Technology stack (with versions)

Exact versions from `pyproject.toml`, `frontend/package.json`,
`desktop/requirements.txt`. See doc 02 for the full pinned lists.

### Backend (`pyproject.toml`, `requires-python = ">=3.11,<3.13"`)

| Component | Package | Version constraint |
|-----------|---------|--------------------|
| Web framework | `fastapi` | `>=0.104.0` |
| ASGI server | `uvicorn` | `>=0.24.0` |
| Validation | `pydantic` | `>=2.9.2` |
| Workflows | `langgraph` | `>=1.0.10` (CVE-2026-28277 fix) |
| LangChain core | `langchain` | `>=1.2.0`; `langchain-core>=1.3.3` |
| Checkpoints | `langgraph-checkpoint-sqlite` | `>=3.0.1` |
| Multi-provider AI | `esperanto` | `>=2.20.0,<3` |
| Database driver | `surrealdb` | `>=1.0.4` |
| Job queue | `surreal-commands` | `>=1.3.1,<2` |
| Podcasts | `podcast-creator` | `>=0.12.0,<1` |
| Content extraction | `content-core` | `>=1.14.1,<2` |
| Prompts | `ai-prompter` | `>=0.4,<1` |
| Tokenization | `tiktoken` | `>=0.12.0` |
| Logging | `loguru` | `>=0.7.2` |
| Metrics | `prometheus-client` | `>=0.20.0` |
| MCP client | `mcp` | `>=1.0.0` |
| LLM providers | `langchain-openai>=1.1.14`, `langchain-anthropic>=1.3.0`, `langchain-ollama>=1.0.1`, `langchain-google-genai>=4.1.2`, `langchain-groq>=1.1.1`, `langchain_mistralai>=1.1.1`, `langchain_deepseek>=1.0.0` | — |

### Frontend (`frontend/package.json`)

| Component | Package | Version |
|-----------|---------|---------|
| Framework | `next` | `^16.2.3` |
| UI runtime | `react` / `react-dom` | `^19.2.3` |
| State | `zustand` | `^5.0.6` |
| Data fetching | `@tanstack/react-query` | `^5.83.0` |
| HTTP | `axios` | `^1.15.0` |
| Styling | `tailwindcss` | `^4` |
| Components | `@radix-ui/*` (Shadcn/ui), `lucide-react ^0.525.0` | — |
| Forms | `react-hook-form ^7.60.0`, `zod ^4.0.5`, `@hookform/resolvers ^5.1.1` | — |
| Markdown | `react-markdown ^10.1.0`, `@uiw/react-md-editor ^4.0.8`, `remark-gfm ^4.0.1` | — |
| i18n | `i18next ^25.7.3`, `react-i18next ^16.5.0` | — |
| Tests | `vitest ^4.1.8`, `@testing-library/react ^16.2.0`, `jsdom ^26.0.0` | — |

### Desktop bundle (`desktop/requirements.txt`)

| Component | Package | Version |
|-----------|---------|---------|
| Webview window | `pywebview` | `==5.4` |
| Packager | `pyinstaller` | `>=6.13.0,<7` |
| Async HTTP | `aiohttp` | `>=3.11.18,<4` |
| Local LLM server | `llama-cpp-python[server]` | `>=0.3.16,<0.4` |
| STT | `faster-whisper` | `>=1.1.0,<2` |
| TTS | `piper-tts` | `>=1.2.0,<2` |
| Memory layer | `mem0ai` | `>=0.1.0,<2` |
| MCP bridge | `mcp>=1.0,<2`, `fastmcp>=3.0,<4` | — |
| Prompt optimizer | `skillopt` | `>=0.1.0,<0.2` (microsoft/SkillOpt, MIT) |

### Database

- **SurrealDB v2** — single engine providing graph + document + vector + KV.
  Schema lives in `open_notebook/database/migrations/*.surrealql` and is applied
  automatically on API startup by `AsyncMigrationManager` (see doc 03).

---

## 8. Cross-cutting concerns

- **Observability** — every response carries an `X-Request-ID` header
  (`RequestIDMiddleware`); every log line includes `req=<8-char-id>`. A
  `PrometheusMetricsMiddleware` exposes `GET /metrics` (`api/metrics.py`):
  HTTP request totals/latency, `db_query_duration_seconds`, `db_slow_queries_total`
  (gated by `ONP_SLOW_QUERY_LOG_MS`), `memory_recall_fallthrough_total`,
  `checkpoint_prune_runs_total`, privacy-gate + tool-loop counters.
- **Security middleware** (`api/main.py`): `SecurityHeadersMiddleware`,
  `SelectiveGZipMiddleware`, `RateLimitMiddleware` (`api/rate_limit.py`), CORS,
  and a simple password auth middleware (`api/auth.py`, dev-grade — replace with
  OAuth/JWT in production).
- **Encryption** — provider API keys + Gmail OAuth tokens are encrypted at rest
  with Fernet (`open_notebook/utils/encryption.py`), keyed by
  `OPEN_NOTEBOOK_ENCRYPTION_KEY`. Optional PBKDF2-HMAC-SHA256 KDF
  (`ONP_ENCRYPTION_KDF=pbkdf2`, 600k iterations) and key rotation
  (`OPEN_NOTEBOOK_ENCRYPTION_KEYS=new-key,old-key`).
- **Privacy gate** (`ONP_PRIVACY_GATE`) — keeps turns containing detected
  secrets/PII on the local model (or blocks them) instead of sending to cloud.
- **Offline gate** (`open_notebook/ai/offline_gate.py`) — `offline_mode` setting
  forces local-only operation and short-circuits web search / Gmail digests.

---

## 9. API startup sequence

`api/main.py` uses a FastAPI `lifespan` handler (`api/main.py:203`):

1. Construct `AsyncMigrationManager()` (auto-discovers migrations).
2. `await migration_manager.run_migration_up()` — apply all pending SurrealQL
   migrations.
3. `await migrate_podcast_profiles()` — data-migrate legacy podcast
   provider/model strings to `record<model>` references.
4. Pre-warm connections, start the digest scheduler task, register routers.

> **Ordering invariant:** SurrealDB must be up before the API starts, and the
> API must be up before the UI — the UI depends on the API for all data.

---

## 10. Repository map (top level)

```
api/                 FastAPI app: main.py, routers/, *_service.py, middleware/
open_notebook/       Backend core
  ai/                Esperanto wrapper, model resolution, routing, gates
  database/          repository.py, async_migrate.py, migrations/*.surrealql
  domain/            ObjectModel/RecordModel domain models
  graphs/            LangGraph workflows (chat, ask, source, transformation)
  podcasts/          Podcast domain models + data migration
  mcp/, memory*, digest/, health/, local_models/, tools/, utils/
frontend/            Next.js 16 app (src/app, src/components, src/lib)
desktop/             pywebview launcher, sidecar supervision, build/, shims
prompts/             Jinja2 prompt templates (ai-prompter)
scripts/             Dev/ops scripts (incl. ralph.sh autonomous loop)
Makefile             dev + docker + build-mac targets
pyproject.toml       Backend deps (uv-managed)
docker-compose.yml   SurrealDB + services for self-host
```
