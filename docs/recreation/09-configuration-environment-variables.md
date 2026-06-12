# 09 — Configuration & Environment Variables

Complete configuration reference for Open Notebook Plus: `config.toml` (desktop),
`.env` keys, all `ONP_*` / `OPEN_NOTEBOOK_*` env vars, provider keys, feature flags,
ports, and the desktop launcher. **All secret values are REDACTED** — only names and
non-sensitive defaults appear.

---

## 1. `config.toml` — Desktop Launcher Config

Persisted by `desktop/config.py` (`Config` frozen dataclass). Default path:

- macOS/Linux: `~/.open-notebook-plus/config.toml`
- Windows: `%USERPROFILE%\.open-notebook-plus\config.toml`

**Structure** (TOML key = value; serialized via `_toml_string()`):

```toml
model_dir = '<MODEL_DIR>'          # default ~/Desktop/AI_Models (Win: %USERPROFILE%\Desktop\AI_Models)
provider = 'none'                  # one of: ollama | llamacpp | none
default_model = ''                 # model identifier
surreal_user = 'root'              # SurrealDB user            [REDACTED in practice]
surreal_password = '<REDACTED>'    # random secrets.token_urlsafe(24) on first run
theme = 'light-blue'
openchronicle_choice = 'skip'      # first-run wizard choice
encryption_key = '<REDACTED>'      # random secrets.token_urlsafe(32) if unset
```

**Security.** `Config.save()` writes the file `0o600` and the parent dir `0o700`
(atomic temp-file + `os.replace`) because the file stores both the SurrealDB password
and the Fernet `encryption_key` that decrypts every saved API key + Gmail OAuth token
(v0.6.8 — default umask 022 made it world-readable on shared machines). Provider must be
one of `{ollama, llamacpp, none}` or `load_or_create()` raises `ValueError`. A
missing/blank `encryption_key` is regenerated and persisted.

> NOTE per project memory: the runtime `model_dir` in this install is
> `~/Desktop/AI_Models/GGUF`.

---

## 2. `.env` Keys (names only — values REDACTED)

From `.env.example`. **Required block:**

| Key | Role |
|---|---|
| `OPEN_NOTEBOOK_ENCRYPTION_KEY` | Fernet key (any string; SHA-256-derived). **Required** — credential encryption is unavailable until set. |

**Database block** (defaults match `docker-compose.yml`):

| Key | Default (docker) |
|---|---|
| `SURREAL_URL` | `ws://surrealdb:8000/rpc` |
| `SURREAL_USER` | `<REDACTED>` (`root` in example) |
| `SURREAL_PASSWORD` | `<REDACTED>` (`root` in example) |
| `SURREAL_NAMESPACE` | `open_notebook` |
| `SURREAL_DATABASE` | `open_notebook` |

(The code also reads alternate forms `SURREAL_ADDRESS`, `SURREAL_PORT`, `SURREAL_PASS`
in some paths.)

**Optional AI provider keys** (commented in `.env.example`; UI config preferred):
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` (/`GEMINI_API_KEY`),
`GROQ_API_KEY`, `MISTRAL_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`,
`OPENROUTER_API_KEY`, `VOYAGE_API_KEY`, `ELEVENLABS_API_KEY`, `DASHSCOPE_API_KEY`,
`MINIMAX_API_KEY`, `OLLAMA_API_BASE`, plus Azure (`AZURE_OPENAI_API_KEY`,
`AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_ENDPOINT_{LLM,
EMBEDDING,STT,TTS}`), Vertex (`VERTEX_PROJECT`, `VERTEX_LOCATION`,
`GOOGLE_APPLICATION_CREDENTIALS`), and OpenAI-compatible
(`OPENAI_COMPATIBLE_API_KEY`, `OPENAI_COMPATIBLE_BASE_URL`).

**Web search** (opt-in by key presence): `SERPER_API_KEY`, `TAVILY_API_KEY`,
`SEARXNG_BASE_URL`.

**Other optional:** `API_URL`/`API_BASE_URL`, `OLLAMA_BASE_URL`, `CHUNK_SIZE`,
`CHUNK_OVERLAP`, `BASIC_AUTH_USERNAME`, `BASIC_AUTH_PASSWORD`, `CORS_ORIGINS`.

### 2.1 Encryption key handling (`open_notebook/utils/encryption.py`)

- `get_secret_from_env(VAR)` checks `VAR_FILE` (Docker secrets) first, then `VAR`.
- **Key rotation:** `OPEN_NOTEBOOK_ENCRYPTION_KEYS` (plural, comma-separated) — first =
  new primary, rest = old keys accepted for decryption only. Falls back to
  `OPEN_NOTEBOOK_ENCRYPTION_KEY` (singular). Both honor `_FILE` variants. KDF selector:
  `ONP_ENCRYPTION_KDF`. Fernet = AES-128-CBC + HMAC-SHA256; legacy unencrypted values
  decrypt-through gracefully (InvalidToken → original).

---

## 3. `ONP_*` Environment Variables (local-deploy knobs)

All have sane defaults; set only to tune. Grouped by subsystem.

### Workflow context / timeout caps
| Var | Default | Purpose |
|---|---|---|
| `ONP_CHAT_HISTORY_CHAR_CAP` | 12000 | chat message-history budget |
| `ONP_CHAT_MESSAGE_CHAR_CAP` | — | per-message cap |
| `ONP_CHAT_TIMEOUT_SEC` / `ONP_CHAT_TIMEOUT_S` | 300 / 30 | `/chat/execute` outer wrap / memory extraction |
| `ONP_CHAT_MODEL_TIMEOUT_SEC` | 300 | per `model.ainvoke` in tool loop |
| `ONP_AGENT_MAX_ITERATIONS` | 4 | chat tool-loop cap |
| `ONP_MCP_TOOL_TIMEOUT_SEC` | 30 | per MCP tool call |
| `ONP_MCP_RPC_TIMEOUT_SEC` | 30 | per MCP RPC |
| `ONP_MCP_AUTH_HEADER` | — | `Name: <REDACTED>` auth header |
| `ONP_ASK_MAX_RESULTS` | 10 | ask graph vector rows |
| `ONP_ASK_PER_RESULT_CHAR_CAP` | 1500 | ask per-result cap |
| `ONP_ASK_NODE_TIMEOUT_SEC` | 120 | per ask node |
| `ONP_TRANSFORMATION_INPUT_CAP` | 12000 | transform input cap |
| `ONP_TRANSFORM_NODE_TIMEOUT_SEC` / `ONP_TRANSFORMATION_TIMEOUT_SEC` | 180 | transform node |
| `ONP_SOURCE_CHAT_SOURCE_CHAR_CAP` | 4000 | source-chat source cap |
| `ONP_SOURCE_CHAT_INSIGHT_CHAR_CAP` | 1000 | per-insight cap |
| `ONP_SOURCE_CHAT_MAX_INSIGHTS` | 10 | max insights injected |
| `ONP_SOURCE_CHAT_HISTORY_CHAR_CAP` | 8000 | source-chat history budget |
| `ONP_SEARCH_TIMEOUT_SEC` / `ONP_SUBMIT_COMMAND_TIMEOUT_SEC` | — | search / command submit |

### Offline / network / routing
| Var | Default | Purpose |
|---|---|---|
| `ONP_NETWORK_STATE_TTL_SEC` | 20 | network probe cache TTL |
| `ONP_NET_PROBE_HOSTS` | `1.1.1.1:443,8.8.8.8:443` | TCP probe targets |
| `ONP_LOCAL_REPLY_HEADROOM_TOKENS` | 8192 | router reply reservation |
| `ONP_CHAT_LLM_CTX` / `ONP_CHAT_LLM_CTX_MAX` | 32768 | local n_ctx |

### Privacy gate (Phase 5.2)
`ONP_PRIVACY_GATE` (feature flag, off), `ONP_PRIVACY_CLASSIFIER_MODEL`,
`ONP_PRIVACY_CLASSIFIER_URL`, `ONP_PRIVACY_CLASSIFIER_TIMEOUT_SEC`.

### Agent FSM (Phase 5.3)
`ONP_AGENT_FSM` (feature flag, off — enables `<state>complete/clarify</state>`).

### Memory
`ONP_MEMORY_RECALL_MODE` (`recent|semantic|auto`), `ONP_MEMORY_RECALL_EPISODES` (1),
`ONP_MEMORY_RECALL_EMBED_TIMEOUT_SEC`, `ONP_MEMORY_RECALL_QUERY_TIMEOUT_SEC`,
`ONP_MEMORY_RECALL_BUDGET_SEC`, `ONP_MEMORY_BATCH_TURNS`, `ONP_MEMORY_CONFIDENCE_FLOOR`,
`ONP_MEMORY_KEEP_PER_TABLE`, `ONP_MEMORY_URL`, `ONP_MEMORY_INJECTED`,
`ONP_VOICE_INJECTED`, `ONP_STT_URL`, `ONP_TTS_URL` (last group set by the launcher).

### Web search
`ONP_WEB_SEARCH_PROVIDER` (`serper|tavily|searxng|auto`), `ONP_WEB_SEARCH_MAX_RESULTS`
(5), `ONP_WEB_SEARCH_TIMEOUT_SEC` (10), `ONP_WEB_SEARCH_TOTAL_BUDGET_SEC` (25).

### Podcast
`ONP_PODCAST_GENERATION_TIMEOUT_SEC` (1800), `ONP_PODCAST_MAX_CONTENT_TOKENS`.

### Prompt optimizer
`ONP_PROMPT_OPT_TIMEOUT_SEC`.

### Studio (one-shot generation)
`ONP_STUDIO_MAX_FILE_CHARS` (15000), `ONP_STUDIO_MAX_COMBINED_CHARS` (60000),
`ONP_STUDIO_MAX_FILE_CHARS`, `ONP_STUDIO_EXTRACT_TIMEOUT_SEC`,
`ONP_STUDIO_OUTLINE_TIMEOUT_SEC`, `ONP_STUDIO_PAGE_TIMEOUT_SEC`,
`ONP_STUDIO_NOTEBOOK_MULTIPAGE`, `ONP_STUDIO_NOTEBOOK_PAGES_MAX`,
`ONP_STUDIO_NOTEBOOK_PARALLEL_PAGES`.

### Database / worker / queue
`ONP_DB_POOL_SIZE` (4, range 1–32), `ONP_DB_POOL_DISABLED`, `ONP_SLOW_QUERY_LOG_MS`,
`ONP_DISABLE_DB_AUTOREPAIR`, `ONP_REPAIR_PORT`, `ONP_SURREAL_TCP_TIMEOUT`,
`ONP_SIDECAR_TCP_TIMEOUT`, `ONP_WORKER_MAX_TASKS`, `ONP_VECTOR_MIN_SCORE`,
`ONP_BULK_VECTORIZE_MAX_SOURCES`, `ONP_NOTEBOOK_DELETE_BULK_THRESHOLD`,
`ONP_CHECKPOINT_KEEP_PER_THREAD`, `ONP_CHECKPOINT_PRUNE_INTERVAL_HOURS`.

### Connection testing / model discovery
`ONP_CONNECTION_TEST_TIMEOUT_SEC` (+ `_OLLAMA` and other per-provider suffixes),
`ONP_DISCOVER_MODELS_TIMEOUT_SEC`, `ONP_MODEL_SCAN_TIMEOUT`.

### Source / notes / export
`ONP_SOURCE_UPLOAD_MAX_BYTES` (524288000 = 500 MB), `ONP_NOTE_TITLE_FALLBACK_LEN`,
`ONP_NOTE_TITLE_TIMEOUT_SEC`, `ONP_AUTO_EXPORT_HOURS`, `ONP_AUTO_EXPORT_KEEP`,
`ONP_AUTO_EXPORT_FIRST_DELAY_SECS`.

### Security / ops
`ONP_RATE_LIMIT_PER_MIN` (API rate limit), `ONP_METRICS_AUTH_TOKEN` (gates `/metrics`),
`ONP_ENCRYPTION_KDF`, `ONP_CODESIGN_IDENTITY` (build).

### Logging / lifecycle
`ONP_LOG_DIR` (default `~/.open-notebook-plus/logs`), `ONP_LOG_LEVEL` (INFO),
`ONP_LOG_JSON` (0), `ONP_DATA_DIR`, `ONP_VERSION`, `ONP_SHUTDOWN_GRACE_SECS`,
`ONP_API_READY_TIMEOUT`, `ONP_FRONTEND_READY_TIMEOUT`, `ONP_BENCHMARK_ONLY`,
`ONP_REMIND_OPENCHRONICLE`.

---

## 4. `OPEN_NOTEBOOK_*` Environment Variables

| Var | Default | Purpose |
|---|---|---|
| `OPEN_NOTEBOOK_ENCRYPTION_KEY` | — (required) | Fernet credential key |
| `OPEN_NOTEBOOK_ENCRYPTION_KEYS` | — | rotation (new,old…) |
| `OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE` | — | Docker-secret variant |
| `OPEN_NOTEBOOK_PASSWORD` / `_FILE` | — | simple password middleware (dev) |
| `OPEN_NOTEBOOK_CHUNK_SIZE` | 400 | embedding chunk size (tokens) |
| `OPEN_NOTEBOOK_CHUNK_OVERLAP` | 15 % | chunk overlap (tokens) |
| `OPEN_NOTEBOOK_EMBEDDING_BATCH_SIZE` | 50 | embed batch size |
| `OPEN_NOTEBOOK_AUTO_ROUTE_CHAT` | off | **flag** — smart local/cloud routing |
| `OPEN_NOTEBOOK_CHAT_PROVIDER` | auto | `auto|local|cloud` |
| `OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID` | — | SurrealDB model id (local) |
| `OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID` | — | SurrealDB model id (cloud) |
| `OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL` | — | sidecar health-probe URL |
| `OPEN_NOTEBOOK_LOCAL_N_CTX` | 32768 | router n_ctx |
| `OPEN_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH` / `_N_PREDICT` | — | speculative draft model |
| `OPEN_NOTEBOOK_MODEL_DIR` / `_DEFAULT` | — | GGUF model dir |
| `OPEN_NOTEBOOK_OSAURUS_PORT` | — | Osaurus provider port |
| `OPEN_NOTEBOOK_LAUNCHER_CONTROL_URL` / `_TOKEN` | — | API→launcher control channel |
| `OPEN_NOTEBOOK_LAUNCHER_LOG_DIR` | — | launcher logs |

---

## 5. Core App Config (`open_notebook/config.py`)

| Var | Default | Resolves to |
|---|---|---|
| `DATA_FOLDER` | `./data` (launcher injects absolute `~/.open-notebook-plus/data/`) | root data dir |
| — | — | `LANGGRAPH_CHECKPOINT_FILE = {DATA_FOLDER}/sqlite-db/checkpoints.sqlite` |
| — | — | `UPLOADS_FOLDER = {DATA_FOLDER}/uploads` |
| `TIKTOKEN_CACHE_DIR` | `{DATA_FOLDER}/tiktoken-cache` | tiktoken encodings cache |

The launcher injects an absolute `DATA_FOLDER` because a DMG-mounted `.app` has a
read-only CWD — a relative `./data` raised `OSError: Read-only file system` at import
and crashed uvicorn before it bound a port (the "app won't open" incident, v0.7.147).

---

## 6. Feature Flags Summary

| Flag | Default | Effect |
|---|---|---|
| `OPEN_NOTEBOOK_AUTO_ROUTE_CHAT` | off | smart local/cloud routing (UI toggle `DefaultModels.auto_route_enabled` when env unset) |
| `ONP_PRIVACY_GATE` | off | fail-closed PII gate (cloud→local) |
| `ONP_AGENT_FSM` | off | declared-state tool loop + ungrounded-synthesis guard |
| `ONP_MEMORY_RECALL_EPISODES` | on | inject session-summary episodes |
| web_search | by key | `SERPER/TAVILY/SEARXNG` presence binds the tool |
| crawl4ai | by install | `url_engine=crawl4ai` + package installed |
| opencode | by install | `opencode` on PATH binds `opencode_run` |
| skillopt | by install | prompt optimizer feature |
| `ONP_DB_POOL_DISABLED` | off | disable SurrealDB pool (debug) |

UI-driven routing also reads `DefaultModels.auto_route_provider_pref` and
`auto_route_cloud` from SurrealDB.

---

## 7. Ports

| Service | Port | Source |
|---|---|---|
| Frontend (Next.js) | 3000 | `frontend/`; `supervisord.conf` `node server.js` |
| API (FastAPI/uvicorn) | 5055 | `uvicorn api.main:app --port 5055` (`supervisord.conf`, `docker-compose.yml`) |
| SurrealDB | 8000 | `docker-compose.yml` `8000:8000`, `ws://…:8000/rpc` |
| Ollama (if used) | 11434 | `OLLAMA_API_BASE` / `OLLAMA_BASE_URL` |
| Local llama.cpp + STT/TTS/embed/memory sidecars | dynamic | `desktop/ports.py:find_free_ports()` allocates free 127.0.0.1 ephemeral ports (SO_REUSEADDR, de-dupe, ≤5 reprobes) |

The desktop app allocates sidecar ports dynamically (not fixed) to avoid collisions;
URLs are passed to the API via env (`OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL`, `ONP_STT_URL`,
`ONP_TTS_URL`, `ONP_MEMORY_URL`).

---

## 8. Desktop Launcher Config

- **Process model** (`supervisord.conf` for Docker; `desktop/launcher.py` for native):
  `[program:api]` (uvicorn :5055), `[program:worker]`
  (`surreal-commands-worker --import-modules commands`), `[program:frontend]`
  (`wait-for-api.sh && node server.js`). The single-container variant
  (`supervisord.single.conf`) also runs `[program:surrealdb]`
  (`surreal start … rocksdb:/mydata/mydatabase.db`).
- **First-run wizard** (`desktop/first_run/`) writes `config.toml`, picks
  `provider` + `default_model`, and `openchronicle_choice` (`skip` default).
- **Control channel** — the API reaches the launcher (model spawn/stop) via
  `OPEN_NOTEBOOK_LAUNCHER_CONTROL_URL` + `OPEN_NOTEBOOK_LAUNCHER_CONTROL_TOKEN`.
- **Auto-register** (`desktop/auto_register/`) writes the local model env so the offline
  gate / smart router treat the spawned sidecar as a local provider.
- The Plus desktop app runs **natively on the host** (macOS `.dmg`, Windows local-dev)
  — never in Docker; the Docker/supervisord layout is the server-deploy alternative.
