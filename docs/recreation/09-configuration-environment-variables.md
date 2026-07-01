# 09 — Configuration & Environment Variables

Exhaustive configuration reference for Open Notebook Plus, transcribed from the
real source on branch `desktop-app`. Paths are repo-relative to
`/Users/Antman/Desktop/OpenNotebook/open-notebook-Plus`. **No secret values are
included** — only variable names, defaults, and where they are read.

Configuration comes from four layers, in precedence order (highest first):

1. **Shell / process env** (`export FOO=…`, Docker `-e`, systemd, CI).
2. **`.env` files** (backend `.env`, frontend `.env.local` for build-time
   `NEXT_PUBLIC_*`).
3. **Desktop launcher prefs file** `~/.open-notebook-plus/launcher.env`
   (whitelisted keys only; **never overrides** an already-set shell env — see §7).
4. **`ContentSettings` DB singleton** (per-install runtime toggles editable in
   Settings; see §6).

Also: `~/.open-notebook-plus/config.toml` (`desktop/config.py`) stores the
first-run desktop config — `model_dir`, `provider`, `default_model`,
`surreal_user`, `surreal_password`, `theme` (default `light-blue`),
`openchronicle_choice`, and a generated `encryption_key`. It is written `0600`
in a `0700` dir because it holds the SurrealDB password + the Fernet key that
decrypts every saved API key. The theme is also updated by
`window.ONP.setTheme` → `POST /api/onp/theme`.

---

## 1. Core / auth / encryption

| Variable | Default | Read at | Purpose |
|---|---|---|---|
| `OPEN_NOTEBOOK_PASSWORD` (+ `_FILE`) | unset (auth **off**) | `api/auth.py`, `api/routers/auth.py`, `api/main.py` | Shared password; sent as `Authorization: Bearer <password>`. Unset ⇒ middleware bypasses all auth. `_FILE` = Docker secret. |
| `OPEN_NOTEBOOK_ENCRYPTION_KEY` (+ `_FILE`) | unset (raises on encrypt) | `open_notebook/utils/encryption.py`, `api/credentials_service.py`, `api/main.py` | Passphrase → Fernet key (via KDF) for provider-key encryption at rest. |
| `OPEN_NOTEBOOK_ENCRYPTION_KEYS` (+ `_FILE`) | unset | `open_notebook/utils/encryption.py` | Comma-separated **rotation list**, primary first (decrypt-only for the rest). Takes precedence over the singular key. |
| `ONP_ENCRYPTION_KDF` | `sha256` | `open_notebook/utils/encryption.py` | KDF selection: `sha256` (fast) or `pbkdf2` (600k iters, recommended if DB may leave the machine). |
| `CORS_ORIGINS` | unset ⇒ `["*"]` | `api/main.py` | Comma-separated allowed origins. Unset ⇒ wildcard AND `allow_credentials=False`. |
| `OPEN_NOTEBOOK_LAUNCHER_CONTROL_TOKEN` | unset | launcher + `api/routers/system` | Bearer token for the launcher↔API control plane (`/api/system/env-refresh`); separate trust boundary from the user password. |
| `OPEN_NOTEBOOK_LAUNCHER_CONTROL_URL` | — | launcher | URL of the launcher control plane. |
| `ONP_RATE_LIMIT_PER_MIN` | (middleware default) | `api/main.py` `RateLimitMiddleware` | Per-minute request cap. |
| `ONP_METRICS_AUTH_TOKEN` | unset (no auth) | `api/main.py:1143` | Optional bearer for `/metrics` (compared with `secrets.compare_digest`). |
| `API_HOST` | `127.0.0.1` | `run_api.py:18` | uvicorn bind host. |
| `API_PORT` | `5055` | `run_api.py:19` | uvicorn bind port. |
| `API_RELOAD` | `true` | `run_api.py:20` | uvicorn reload flag. |

See doc `06-authentication-authorization.md` for the full auth + encryption flow.

---

## 2. Provider API keys (Esperanto)

Presence of a key is generally the opt-in — no separate flag. Read by the
credential/env-status system (`api/credentials_service.py` `PROVIDER_ENV_CONFIG`)
and Esperanto's `AIFactory`. Keys are migrated into encrypted `Credential` rows
via `POST /credentials/migrate-from-env`.

| Variable | Provider |
|---|---|
| `OPENAI_API_KEY` | OpenAI |
| `ANTHROPIC_API_KEY` | Anthropic |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | Google / Gemini |
| `GROQ_API_KEY` | Groq |
| `MISTRAL_API_KEY` | Mistral |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `XAI_API_KEY` | xAI (Grok) |
| `OPENROUTER_API_KEY` | OpenRouter |
| `VOYAGE_API_KEY` | Voyage (embeddings) |
| `ELEVENLABS_API_KEY` | ElevenLabs (TTS) |
| `DEEPGRAM_API_KEY` | Deepgram (STT) |
| `DASHSCOPE_API_KEY` | Alibaba DashScope |
| `MINIMAX_API_KEY` | MiniMax |
| `OPENAI_COMPATIBLE_API_KEY` / `OPENAI_COMPATIBLE_BASE_URL` | Generic OpenAI-compatible endpoint |
| `OLLAMA_API_BASE` | Ollama base URL (local) |
| `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_ENDPOINT_{LLM,EMBEDDING,STT,TTS}` | Azure OpenAI |
| `GOOGLE_APPLICATION_CREDENTIALS`, `VERTEX_PROJECT`, `VERTEX_LOCATION` | Google Vertex |

The `Credential` model also stores per-account overrides (`base_url`, `endpoint`,
`api_version`, `endpoint_llm/embedding/stt/tts`, `project`, `location`,
`credentials_path`) — see `open_notebook/domain/credential.py`.

---

## 3. Web search (Discover Sources + chat `web_search` tool)

**File:** `open_notebook/tools/web_search.py`. The tool only *exists* when a
provider is configured — **key presence is the opt-in** (no separate flag).
Precedence Serper → Tavily → SearXNG, overridable/failover chained.

| Variable | Default | Purpose |
|---|---|---|
| `SERPER_API_KEY` | unset | Serper (Google Search API). |
| `TAVILY_API_KEY` | unset | Tavily search API. |
| `SEARXNG_BASE_URL` | unset | Self-hosted SearXNG URL(s); comma/whitespace-separated for per-instance failover. Keyless. |
| `ONP_WEB_SEARCH_PROVIDER` | auto (chain) | Force `serper\|tavily\|searxng`. A stale override naming an unconfigured provider is ignored (falls back to auto). |
| `ONP_WEB_SEARCH_MAX_RESULTS` | `5` (ceiling 20) | Max results per search. |
| `ONP_WEB_SEARCH_TIMEOUT_SEC` | `10.0` (ceiling 60) | Per-attempt timeout. |
| `ONP_WEB_SEARCH_TOTAL_BUDGET_SEC` | `25.0` (ceiling 120) | Total wall-clock budget across the failover chain (kept under the tool-call timeout). |

---

## 4. Database (SurrealDB)

Read by the DB connection/repository layer (`open_notebook/database/`) and the
launcher.

| Variable | Purpose |
|---|---|
| `SURREAL_URL` / `SURREAL_ADDRESS` | SurrealDB connection URL/address. |
| `SURREAL_PORT` | Port (default 8000). |
| `SURREAL_NAMESPACE` | Namespace. |
| `SURREAL_DATABASE` | Database name. |
| `SURREAL_USER` / `SURREAL_PASS` / `SURREAL_PASSWORD` | Root credentials. |
| `ONP_DB_POOL_SIZE` | Connection pool size. |
| `ONP_DB_POOL_DISABLED` | Disable the connection pool. |
| `ONP_SURREAL_TCP_TIMEOUT` | TCP timeout for SurrealDB connections. |
| `ONP_SLOW_QUERY_LOG_MS` | Log queries slower than N ms. |
| `ONP_DISABLE_DB_AUTOREPAIR` | If set, the launcher skips the boot-time backup-first DB auto-repair (`desktop/launcher.py` ~1085/1128/1196). |
| `ONP_REPAIR_PORT` | Port used by the DB-repair helper. |
| `DATA_FOLDER` / `OPEN_NOTEBOOK_ARTIFACT_EXPORT_DIR` | Data + artifact-export directories. |

---

## 5. Frontend env vars

Build-time `NEXT_PUBLIC_*` are baked at build; the `/config` route + `getApiUrl`
resolve the API URL at runtime (see doc 05 §10).

| Variable | Default | Read at | Purpose |
|---|---|---|---|
| `NEXT_PUBLIC_API_TIMEOUT_MS` | `600000` (10 min); `0` disables; empty/invalid → default | `frontend/src/lib/api/client.ts` | axios request timeout for slow local LLMs. |
| `NEXT_PUBLIC_API_URL` | unset | `frontend/src/lib/config.ts`, `app/config/route.ts` | Build-time API base URL fallback. |
| `API_URL` | unset | `app/config/route.ts` | Server-side runtime API URL (public/external), returned by `/config`. |
| `INTERNAL_API_URL` | `http://localhost:5055` | `frontend/next.config.ts`, `app/api/_sse-proxy.ts` | Where Next server-side proxies API/SSE requests (multi-container override). |
| `NODE_ENV` | — | `frontend/src/lib/config.ts` | Enables verbose config logging in `development`. |
| `ANALYZE` | `false` | `frontend/next.config.ts` | `@next/bundle-analyzer` toggle. |
| `NEXT_PUBLIC_ONP_EVIDENCE_STUDIO` | `true` | `frontend/src/lib/features.ts` | Feature flag: Evidence Studio. |
| `NEXT_PUBLIC_ONP_VISUAL_REFRESH` | `true` | `frontend/src/lib/features.ts` | Feature flag: aurora/visual refresh. |
| `NEXT_PUBLIC_ONP_MODEL_FLEET` | `true` | `frontend/src/lib/features.ts` | Feature flag: model fleet badge. |
| `NEXT_PUBLIC_ONP_RESEARCH_RUNS` | `false` | `frontend/src/lib/features.ts` | Feature flag: research runs. |

There is a **parallel backend** feature-flag module `open_notebook/feature_flags.py`
reading the un-prefixed `ONP_VISUAL_REFRESH` (default `True`),
`ONP_EVIDENCE_STUDIO` (`True`), `ONP_MODEL_FLEET` (`True`), `ONP_RESEARCH_RUNS`
(`False`).

Frontend flag parsing (`features.ts`) treats `1/true/yes/on/enabled` as truthy:

```ts
const TRUTHY = new Set(['1', 'true', 'yes', 'on', 'enabled'])
function envFlag(name: string, defaultValue = false): boolean {
  const value = process.env[name]
  return value ? TRUTHY.has(value.trim().toLowerCase()) : defaultValue
}
```

Runtime API-URL fallback also exists purely in `window.ONP_VERSION` (sidebar
version badge) — not an env var, injected by the desktop wrapper.

---

## 6. `ContentSettings` singleton (runtime toggles)

**File:** `open_notebook/domain/content_settings.py` — a `RecordModel` singleton
`open_notebook:content_settings`, read/written via
`api/routers/settings.py` and editable in Settings. Verbatim fields:

```python
class ContentSettings(RecordModel):
    record_id: ClassVar[str] = "open_notebook:content_settings"
    default_content_processing_engine_doc: Optional[Literal["auto","docling","simple"]] = Field("auto", …)
    default_content_processing_engine_url: Optional[Literal["auto","crawl4ai","firecrawl","jina","simple"]] = Field("auto", …)
    default_embedding_option: Optional[Literal["ask","always","never"]] = Field("ask", …)
    auto_delete_files: Optional[Literal["yes","no"]] = Field("yes", …)
    youtube_preferred_languages: Optional[list[str]] = Field(["en","pt","es","de","nl","en-GB","fr","de","hi","ja"], …)
    offline_mode: Optional[bool] = Field(False, description="Force offline: never use the internet")
    auto_summarize_on_ingest: Optional[bool] = Field(False, description="Automatically summarize sources when they are added")
    auto_extract_topics_on_ingest: Optional[bool] = Field(False, description="Automatically extract key topics when sources are added")
```

| Field | Default | Meaning |
|---|---|---|
| `default_content_processing_engine_doc` | `auto` | Doc extractor: `auto`/`docling`/`simple`. |
| `default_content_processing_engine_url` | `auto` | URL extractor: `auto`/`crawl4ai`/`firecrawl`/`jina`/`simple`. |
| `default_embedding_option` | `ask` | Vector-search embedding: `ask`/`always`/`never`. |
| `auto_delete_files` | `yes` | Delete uploaded files after processing. |
| `youtube_preferred_languages` | list | Preferred YouTube transcript languages. |
| `offline_mode` | `false` | **Force offline**: cloud chat falls back to local model, web search short-circuits, Gmail digests defer; local-provider models unaffected. |
| `auto_summarize_on_ingest` | `false` | Run the "Summary" transformation on each new source (extra LLM call). |
| `auto_extract_topics_on_ingest` | `false` | Run "Key Topics" extraction on each new source (populates the card's topic badges). |

---

## 7. Desktop launcher prefs (`~/.open-notebook-plus/launcher.env`)

**File:** `desktop/launcher_prefs.py`. A KEY=VALUE file (comments/blank lines
preserved) editable via Settings → Launch Preferences. **Precedence:
`merge_with_env()` fills a key only if it's absent from the process env — shell
env always wins.** Only a strict whitelist may be written (a PUT with an unknown
key → 400):

```python
ALLOWED_KEYS: frozenset[str] = frozenset({
    "OPEN_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH",
    "OPEN_NOTEBOOK_LOCAL_DRAFT_N_PREDICT",
    "OPEN_NOTEBOOK_LOCAL_N_CTX",   # canonical alias
    "ONP_CHAT_LLM_CTX",
    "ONP_CHAT_LLM_CTX_MAX",
})
```

Read/written by `get_prefs()` / `update_prefs()`; exposed via
`GET/PUT /api/launcher-prefs` (`api/routers/launcher_prefs.py`) and the
`settings/launcher-prefs` page. The whitelist is deliberately small so the file
never becomes an accidental secrets store.

### Model directory (`OPEN_NOTEBOOK_MODEL_DIR`)

`OPEN_NOTEBOOK_MODEL_DIR` (with `OPEN_NOTEBOOK_MODEL_DIR_DEFAULT`) is the local
GGUF/MLX model directory, read across `api/routers/local_models.py`,
`api/routers/studio.py`, `open_notebook/ai/provision.py`,
`open_notebook/studio/artifact_generation.py`. Resolution order:
**`OPEN_NOTEBOOK_MODEL_DIR` > launcher default > POSIX default**
(`api/routers/local_models.py:1196`). Endpoints error with
"Configure OPEN_NOTEBOOK_MODEL_DIR" when unset/missing.

> Install note: `OPEN_NOTEBOOK_MODEL_DIR` must point at the **parent** of the
> `GGUF/` folder (e.g. `~/Desktop/AI_Models`), and changing it requires a full
> app quit + relaunch to take effect.

### Local-model / chat-provider launcher vars

| Variable | Purpose |
|---|---|
| `OPEN_NOTEBOOK_ACTIVE_GGUF_MODEL` | Currently selected GGUF model. |
| `OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL` / `OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID` | Local chat endpoint + model id. |
| `OPEN_NOTEBOOK_LOCAL_N_CTX` / `ONP_CHAT_LLM_CTX` / `ONP_CHAT_LLM_CTX_MAX` | Local context window (whitelisted prefs). |
| `OPEN_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH` / `OPEN_NOTEBOOK_LOCAL_DRAFT_N_PREDICT` | Speculative-draft model path + n_predict (whitelisted). |
| `OPEN_NOTEBOOK_CHAT_PROVIDER` / `OPEN_NOTEBOOK_AUTO_ROUTE_CHAT` | Chat provider + smart-routing toggle. |
| `OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID` / `OPEN_NOTEBOOK_OSAURUS_PORT` | Cloud fallback model id / Osaurus port. |
| `OPEN_NOTEBOOK_LAUNCHER_LOG_DIR` / `ONP_LOG_DIR` | Log directories. |
| `ONP_API_READY_TIMEOUT` / `ONP_FRONTEND_READY_TIMEOUT` / `ONP_SHUTDOWN_GRACE_SECS` | Launcher startup/shutdown timing. |

### `config.toml` fields (first-run desktop config)

**File:** `desktop/config.py`. The `Config` dataclass persisted to
`~/.open-notebook-plus/config.toml`:

```python
@dataclass(frozen=True)
class Config:
    model_dir: Path                 # default: $HOME/Desktop/AI_Models (parent of GGUF/)
    provider: Provider              # Literal["ollama","llamacpp","mlx","none"]
    default_model: str
    surreal_user: str
    surreal_password: str
    theme: str = "light-blue"
    openchronicle_choice: str = "skip"
    encryption_key: str = field(default_factory=lambda: secrets.token_urlsafe(32))
```

`model_dir` default is `$HOME/Desktop/AI_Models` (or
`%USERPROFILE%\Desktop\AI_Models` on Windows) — the **parent** of the `GGUF/`
folder. This value seeds `OPEN_NOTEBOOK_MODEL_DIR`. Provider whitelist:
`{ollama, llamacpp, mlx, none}`.

### Build-time codesign

> **Correction:** `ONP_CODESIGN_IDENTITY` / `CODESIGN_IDENTITY` **does not exist
> anywhere in this repository** (verified by exhaustive grep across source,
> scripts, shell, spec, and YAML). If a macOS `.dmg` codesign identity is used,
> it lives in an external build pipeline not checked into this tree — do **not**
> document it as an app-read variable.

---

## 8. Backend LLM / chat / agent tuning (`ONP_*`)

All read via `os.environ.get` in the backend. Grep source: `grep -rn 'ONP_' api/ open_notebook/ desktop/`.

Selected authoritative defaults (from `os.environ.get(...)` call sites):
`ONP_DB_POOL_SIZE`=`4`, `ONP_SLOW_QUERY_LOG_MS`=`500`, `ONP_LOG_LEVEL`=`INFO`,
`ONP_NETWORK_STATE_TTL_SEC`=`20`, `ONP_CHAT_HISTORY_CHAR_CAP`=`12000`,
`ONP_AGENT_MAX_ITERATIONS`=`4`, `ONP_MCP_TOOL_TIMEOUT_SEC`=`30`,
`ONP_CHAT_TIMEOUT_SEC`=`300`, `ONP_ASK_MAX_RESULTS`=`10`,
`ONP_ASK_PER_RESULT_CHAR_CAP`=`1500`, `ONP_TRANSFORMATION_INPUT_CAP`=`12000`,
`ONP_TRANSFORMATION_TIMEOUT_SEC`=`180`, `ONP_SOURCE_CHAT_HISTORY_CHAR_CAP`=`8000`,
`ONP_SOURCE_CHAT_SOURCE_CHAR_CAP`=`4000`, `ONP_SOURCE_CHAT_INSIGHT_CHAR_CAP`=`1000`,
`ONP_SOURCE_CHAT_MAX_INSIGHTS`=`10`, `ONP_STUDIO_MAX_FILE_CHARS`=`15000`,
`ONP_STUDIO_MAX_COMBINED_CHARS`=`60000`, `ONP_STUDIO_PAGE_TIMEOUT_SEC`=`180`,
`ONP_STUDIO_EXTRACT_TIMEOUT_SEC`=`60`, `ONP_NOTEBOOK_DELETE_BULK_THRESHOLD`=`25`,
`ONP_SOURCE_UPLOAD_MAX_BYTES`=`524288000` (500 MB),
`ONP_NOTE_TITLE_TIMEOUT_SEC`=`60`, `ONP_SUBMIT_COMMAND_TIMEOUT_SEC`=`10`,
`ONP_DISCOVER_MODELS_TIMEOUT_SEC`=`30`, `ONP_LOCAL_REPLY_HEADROOM_TOKENS`=`8192`,
`ONP_WORKER_MAX_TASKS`=`5`, `ONP_SHUTDOWN_GRACE_SECS`=`8`,
`ONP_REPAIR_PORT`=`18799`, `ONP_AUTO_EXPORT_HOURS`=`24`,
`ONP_AUTO_EXPORT_KEEP`=`7`, `ONP_AUTO_EXPORT_FIRST_DELAY_SECS`=`600`,
`ONP_CHAT_LLM_CTX_MAX`=`32768`, `ONP_MODEL_SCAN_TIMEOUT`=`20`,
`ONP_CHAT_TIMEOUT_S`=`30` (memory writer),
`ONP_PODCAST_GENERATION_TIMEOUT_SEC`=`1800`.

### Chat / LLM context & timeouts
`ONP_CHAT_LLM_GGUF`, `ONP_CHAT_LLM_N_GPU_LAYERS`, `ONP_CHAT_MODEL_NAME`,
`ONP_CHAT_MODEL_TIMEOUT_SEC`, `ONP_CHAT_TIMEOUT_SEC` / `ONP_CHAT_TIMEOUT_S`,
`ONP_CHAT_RAM_GB_CEILING`, `ONP_CHAT_HISTORY_CHAR_CAP`,
`ONP_CHAT_MESSAGE_CHAR_CAP`, `ONP_LOCAL_REPLY_HEADROOM_TOKENS`,
`ONP_EMBED_N_GPU_LAYERS`.

### Source chat
`ONP_SOURCE_CHAT_HISTORY_CHAR_CAP`, `ONP_SOURCE_CHAT_INSIGHT_CHAR_CAP`,
`ONP_SOURCE_CHAT_MAX_INSIGHTS`, `ONP_SOURCE_CHAT_SOURCE_CHAR_CAP`.

### Agent FSM / privacy gate
- `ONP_AGENT_FSM` — default **off**; gates the agent finite-state tool loop
  (`open_notebook/graphs/ask.py:101`, `chat.py:358`).
- `ONP_AGENT_MAX_ITERATIONS` — agent loop cap.
- `ONP_PRIVACY_GATE` — default **off**; `on`/`1`/`true`/`yes`/`local` enables the
  fail-closed on-device privacy gate (`open_notebook/ai/privacy_gate.py`).
- `ONP_PRIVACY_CLASSIFIER_MODEL` / `_URL` / `_TIMEOUT_SEC` — privacy classifier config.

### Ask / research
`ONP_ASK_MAX_RESULTS`, `ONP_ASK_NODE_TIMEOUT_SEC`, `ONP_ASK_PER_RESULT_CHAR_CAP`,
`ONP_RESEARCH_RUNS`, `ONP_SEARCH_TIMEOUT_SEC`.

### Transformations / notes
`ONP_TRANSFORMATION_TIMEOUT_SEC`, `ONP_TRANSFORM_NODE_TIMEOUT_SEC`,
`ONP_TRANSFORMATION_INPUT_CAP`, `ONP_NOTE_TITLE_TIMEOUT_SEC`,
`ONP_NOTE_TITLE_FALLBACK_LEN`.

### Studio (artifacts)
`ONP_STUDIO_EXTRACT_TIMEOUT_SEC`, `ONP_STUDIO_OUTLINE_TIMEOUT_SEC`,
`ONP_STUDIO_PAGE_TIMEOUT_SEC`, `ONP_STUDIO_MAX_COMBINED_CHARS`,
`ONP_STUDIO_MAX_FILE_CHARS`, `ONP_STUDIO_NOTEBOOK_MULTIPAGE`,
`ONP_STUDIO_NOTEBOOK_PAGES_MAX`, `ONP_STUDIO_NOTEBOOK_PARALLEL_PAGES`,
`ONP_EVIDENCE_STUDIO`.

### Podcasts
- `ONP_PODCAST_MAX_CONTENT_TOKENS` — default **`100000`**; `0` disables the cap
  (`api/podcast_service.py:185`).

### Sources / uploads / vectorization
`ONP_SOURCE_UPLOAD_MAX_BYTES` (validated with a minimum; falls back on bad
values — `api/routers/sources.py:67`), `ONP_BULK_VECTORIZE_MAX_SOURCES`,
`ONP_VECTOR_MIN_SCORE`, `ONP_NOTEBOOK_DELETE_BULK_THRESHOLD`.

### Memory (mem0)
`ONP_MEMORY_URL`, `ONP_MEMORY_BATCH_TURNS`, `ONP_MEMORY_CONFIDENCE_FLOOR`,
`ONP_MEMORY_KEEP_PER_TABLE`, `ONP_MEMORY_RECALL_MODE`,
`ONP_MEMORY_RECALL_EPISODES`, `ONP_MEMORY_RECALL_BUDGET_SEC`,
`ONP_MEMORY_RECALL_EMBED_TIMEOUT_SEC`, `ONP_MEMORY_RECALL_QUERY_TIMEOUT_SEC`.
Plus memory sidecar URLs `MEMORY_CHAT_LLM_URL`, `MEMORY_EMBED_URL`,
`MEMORY_SURREAL_URL` (all `desktop/memory/memory_commands.py`, default `""`),
and `OPENCHRONICLE_MCP_URL` (default `http://127.0.0.1:8742/mcp`,
`desktop/desktop_shims/openchronicle_shim.py`) / `ONP_REMIND_OPENCHRONICLE`.
`OPENCODE_BIN` (`open_notebook/tools/opencode.py`) points at the opencode binary.

### MCP
`ONP_MCP_AUTH_HEADER`, `ONP_MCP_RPC_TIMEOUT_SEC`, `ONP_MCP_TOOL_TIMEOUT_SEC`.

### Checkpoints / worker / commands
`ONP_CHECKPOINT_KEEP_PER_THREAD`, `ONP_CHECKPOINT_PRUNE_INTERVAL_HOURS`,
`ONP_WORKER_MAX_TASKS`, `ONP_SUBMIT_COMMAND_TIMEOUT_SEC`.

### Network / connection tests
`ONP_NETWORK_STATE_TTL_SEC`, `ONP_NET_PROBE_HOSTS`,
`ONP_CONNECTION_TEST_TIMEOUT_SEC` (+ `_OLLAMA` variant),
`ONP_SIDECAR_TCP_TIMEOUT`, `ONP_SURREAL_TCP_TIMEOUT`,
`ONP_DISCOVER_MODELS_TIMEOUT_SEC`, `ONP_MODEL_SCAN_TIMEOUT`,
`ONP_MODEL_FLEET`.

### Auto-export
`ONP_AUTO_EXPORT_HOURS`, `ONP_AUTO_EXPORT_KEEP`,
`ONP_AUTO_EXPORT_FIRST_DELAY_SECS`.

### Logging / STT / TTS / visuals
- `ONP_LOG_LEVEL` — default **`INFO`** (`open_notebook/logging.py:124`).
- `ONP_LOG_JSON`, `ONP_LOG_DIR`.
- `ONP_STT_URL`, `ONP_TTS_URL` — local STT/TTS sidecar URLs.
- `ONP_THEMES`, `ONP_VISUAL_REFRESH`, `ONP_VERSION`.

### Chunking / embeddings (`OPEN_NOTEBOOK_*`)
`OPEN_NOTEBOOK_CHUNK_SIZE`, `OPEN_NOTEBOOK_CHUNK_OVERLAP`,
`OPEN_NOTEBOOK_MIN_CHUNK_SIZE`, `OPEN_NOTEBOOK_EMBEDDING_BATCH_SIZE`,
`TIKTOKEN_CACHE_DIR`.

---

## 9. Where things are read (quick map)

| Concern | File(s) |
|---|---|
| Password auth | `api/auth.py`, `api/routers/auth.py`, `api/main.py` |
| Encryption / KDF | `open_notebook/utils/encryption.py`, `api/credentials_service.py` |
| CORS | `api/main.py` |
| Web search | `open_notebook/tools/web_search.py` |
| Model dir / local models | `api/routers/local_models.py`, `open_notebook/ai/provision.py` |
| Podcasts | `api/podcast_service.py` |
| Privacy gate / agent FSM | `open_notebook/ai/privacy_gate.py`, `open_notebook/graphs/{ask,chat}.py` |
| Logging | `open_notebook/logging.py` |
| DB autorepair | `desktop/launcher.py` |
| Launcher prefs file | `desktop/launcher_prefs.py`, `api/routers/launcher_prefs.py` |
| ContentSettings | `open_notebook/domain/content_settings.py`, `api/routers/settings.py` |
| Frontend runtime config | `frontend/src/lib/config.ts`, `frontend/src/app/config/route.ts`, `frontend/next.config.ts` |
| Frontend client timeout / flags | `frontend/src/lib/api/client.ts`, `frontend/src/lib/features.ts` |

*(To reproduce the exhaustive inventory: `grep -rhoE "ONP_[A-Z0-9_]+" api/
open_notebook/ desktop/ frontend/src/` and `grep -rhoE
"os\.(environ\.get|getenv)\(['\"]?[A-Z0-9_]+" api/ open_notebook/ desktop/`.)*

---

## 10. Read timing & documented references

- **Lazy (request-time) reads** — many `ONP_*` timeouts/caps and
  `ONP_METRICS_AUTH_TOKEN`, `ONP_CHAT_TIMEOUT_SEC` are read on each use, so a
  `.env` edit + `/api/system/env-refresh` (or a plain re-request) can pick them
  up without a restart.
- **Startup/init reads** — DB pool size, log config, and most launcher timing
  are read once at process start and need a **full relaunch** (the same rule
  applies to `OPEN_NOTEBOOK_MODEL_DIR` on the desktop app).
- **Reference files** in-repo: `.env.example` (full backend var reference incl.
  the ONP_* block and web-search failover), `examples/docker.env.example`
  (Docker only — the desktop app never uses Docker), `CONFIGURATION.md` (a stub
  redirecting to `docs/5-CONFIGURATION/`), and the authoritative
  `docs/5-CONFIGURATION/environment-reference.md`.
- **Library-consumed vars** (Esperanto / content-core / podcast-creator, not
  read directly by app code) documented in the reference: `API_CLIENT_TIMEOUT`,
  `ESPERANTO_LLM_TIMEOUT`, `ESPERANTO_SSL_VERIFY`, `ESPERANTO_TTS_TIMEOUT`,
  `TTS_BATCH_SIZE`, `FIRECRAWL_API_KEY`, `JINA_API_KEY`,
  `SURREAL_COMMANDS_MAX_TASKS`, `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`,
  `LANGCHAIN_*`.
