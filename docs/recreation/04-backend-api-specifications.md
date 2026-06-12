# 04 — Backend API Specifications

> Exhaustive recreation reference for the FastAPI backend of **Open Notebook Plus**
> (`open-notebook` v1.8.5, FastAPI 0.104+, Python 3.11–3.12, Pydantic v2,
> LangGraph 1.0.10+, SurrealDB async driver, `surreal-commands` job queue).
> All snippets are real code; secrets are placeholders.

---

## 1. Application bootstrap (`api/main.py`)

The FastAPI app is created with a `lifespan` async context manager and a large
middleware stack. Server is launched via `uv run uvicorn api.main:app --host 127.0.0.1 --port 5055`
(the desktop launcher binds to `127.0.0.1` only).

```python
app = FastAPI(
    title="Open Notebook API",
    description="API for Open Notebook - Research Assistant",
    lifespan=lifespan,
)
```

### 1.1 Lifespan startup sequence

`lifespan()` (`api/main.py:202`) runs, in order:

1. `configure_logging("api")` — rotated file sink at `~/.open-notebook-plus/logs/api.log` (honors `ONP_LOG_DIR`, `ONP_LOG_LEVEL`, `ONP_LOG_JSON`).
2. **Encryption-key check** — warns if neither `OPEN_NOTEBOOK_ENCRYPTION_KEY` nor `OPEN_NOTEBOOK_ENCRYPTION_KEYS` is set.
3. **DB migrations** — `AsyncMigrationManager()`; if `needs_migration()` → `run_migration_up()`. **Fail-fast**: any exception raises `RuntimeError` and the API refuses to start with an outdated schema.
4. **Podcast profile migration** — `migrate_podcast_profiles()` (non-fatal).
5. **Legacy edge dedup** — `dedupe_legacy_edges()` (idempotent, non-fatal).
6. **Stale-command reaper (startup)** — `UPDATE command SET status='failed' … WHERE status IN ['new','queued','running'] AND updated < (time::now() - 30m)`.
7. **Periodic reaper** — background task on a 5-minute loop, anchored via `_track_task()` into module-level `_BACKGROUND_TASKS`.
8. **Gmail digest scheduler** — `run_forever()` background task (wakes every 5 min).
9. **DB pool warmup** — pre-acquires up to 2 connections with retry/backoff (`_WARMUP_RETRY_DELAYS_S = (0.5, 1.0, 2.0)`, each bounded by `asyncio.wait_for(timeout=10)`).
10. **Checkpoint-prune loop** — trims LangGraph SQLite checkpoints (`ONP_CHECKPOINT_PRUNE_INTERVAL_HOURS`, default 24; keeps 50 newest per thread).
11. **Gmail TTL-cache prewarm** — `GmailIntegration.get()`.

On shutdown: cancels all background tasks, `close_pool()`, and closes the chat / source-chat `AsyncSqliteSaver` connections.

### 1.2 Middleware stack (registration order matters)

Starlette wraps in **reverse** registration order. Request flow:

```
request → CORS → RateLimit → RequestID → Prometheus → SecurityHeaders → SelectiveGZip → PasswordAuth → handler
```

| Middleware | Source | Purpose |
|---|---|---|
| `PasswordAuthMiddleware` | `api/auth.py` | Bearer-password gate (registered first → innermost) |
| `SelectiveGZipMiddleware` | `api/main.py` | GZip ≥ 1000 bytes, **bypassed** for streaming paths |
| `SecurityHeadersMiddleware` | `api/middleware/security_headers.py` | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, CSP |
| `PrometheusMetricsMiddleware` | `api/middleware/metrics.py` | request timing → `/metrics` |
| `RequestIDMiddleware` | `api/middleware/request_id.py` | UUID4 per request, `X-Request-ID` response header |
| `RateLimitMiddleware` | `api/rate_limit.py` | env-gated (`ONP_RATE_LIMIT_PER_MIN`, default OFF) |
| `CORSMiddleware` | starlette | registered last → outermost (handles preflight OPTIONS) |

**Streaming GZip bypass** (`_NO_GZIP_PREFIXES = ("/api/chat/stream", "/api/search/ask")`, plus any `POST …/messages`) — token streams use `application/x-ndjson` / `text/plain`, so per-chunk GZip would defeat real-time delivery.

**CORS**: `CORS_ALLOWED_ORIGINS` parsed from `CORS_ORIGINS` env (default `["*"]`). When wildcard, `allow_credentials=False` (the Fetch spec forbids `*` + credentials).

### 1.3 The `/api` prefix

Every router is mounted under `/api` via `app.include_router(<router>.router, prefix="/api", tags=[...])`. Four routers (`local_models`, `mcp`, `launcher_prefs`, `system`) already embed `/api` in their own paths and are mounted **without** the prefix.

### 1.4 Health / probe endpoints (root-mounted, auth-exempt)

| Path | Method | Returns | Notes |
|---|---|---|---|
| `/` | GET | `{"message": "Open Notebook API is running"}` | |
| `/health` | GET | `{"status": "healthy"}` | back-compat; same shape as `/livez` |
| `/livez` | GET | `{"status": "alive"}` | trivial, no DB call, <1ms |
| `/readyz` | GET | `{"status": "ready"|"not_ready", "checks": {...}}` | **200** ready / **503** not ready; checks DB online + migrations applied |
| `/healthz/deep` | GET | `{"status": "healthy"|"degraded"|"not_ready", "checks": {...}}` | per-subsystem; `?probe_providers=true` probes each credential |
| `/api/healthz/deep` | GET | alias of above | added v0.7.148 for the Setup Wizard rewrite path |
| `/api/version` | GET | `{"version": "...", "name": "Open Notebook Plus"}` | splash badge |
| `/metrics` | GET | Prometheus exposition | optional `ONP_METRICS_AUTH_TOKEN` bearer gate (constant-time compare) |

`/readyz` example body:

```json
{
  "status": "ready",
  "checks": {
    "database": "online",
    "database_error": null,
    "migrations_applied": true,
    "migrations_pending": false,
    "migrations_error": null
  }
}
```

`/healthz/deep` checks: `database`, `migrations` (must-have → 503 on fail), plus optional `embedding_model`, `chat_model`, `command_registry`, and `upstream_providers`. Optional failures yield `"degraded"` (still 200).

### 1.5 Global exception handlers → HTTP status mapping

Typed exceptions from `open_notebook/exceptions.py` are mapped by `@app.exception_handler(...)` registrations. All error responses carry CORS headers via `_cors_headers(request)`.

| Exception (base `OpenNotebookError`) | HTTP | Handler |
|---|---|---|
| `NotFoundError` | 404 | `not_found_error_handler` |
| `InvalidInputError` | 400 | `invalid_input_error_handler` |
| `AuthenticationError` | 401 | `authentication_error_handler` |
| `RateLimitError` | 429 | `rate_limit_error_handler` |
| `ConfigurationError` | 422 | `configuration_error_handler` |
| `NetworkError` | 502 | `network_error_handler` |
| `ExternalServiceError` | 502 | `external_service_error_handler` |
| `OpenNotebookError` (base) | 500 | `open_notebook_error_handler` |
| `StarletteHTTPException` | passthrough | `custom_http_exception_handler` (preserves status + adds CORS) |

Full hierarchy (`open_notebook/exceptions.py`):

```python
class OpenNotebookError(Exception): ...
class DatabaseOperationError(OpenNotebookError): ...
class UnsupportedTypeException(OpenNotebookError): ...
class InvalidInputError(OpenNotebookError): ...
class NotFoundError(OpenNotebookError): ...
class AuthenticationError(OpenNotebookError): ...
class ConfigurationError(OpenNotebookError): ...
class ExternalServiceError(OpenNotebookError): ...
class RateLimitError(OpenNotebookError): ...
class FileOperationError(OpenNotebookError): ...
class NetworkError(OpenNotebookError): ...
class NoTranscriptFound(OpenNotebookError): ...
```

---

## 2. Error classification (`open_notebook/utils/error_classifier.py`)

`classify_error(exception) -> tuple[type[OpenNotebookError], str]` converts raw
LLM/Esperanto/LangChain errors into a typed exception + a user-friendly message,
used in graph nodes and SSE handlers.

**Mechanism**: lowercases `"{type_name}: {str(exception)}"` and matches against an
ordered keyword ruleset. First match wins; `message=None` passes the original
(truncated to 200 chars) through.

| Keywords (sample) | Exception | Message |
|---|---|---|
| `authentication`, `unauthorized`, `invalid api key`, `401` | `AuthenticationError` | "Authentication failed. Please check your API key in Settings -> Credentials." |
| `rate limit`, `429`, `quota exceeded` | `RateLimitError` | "Rate limit exceeded. Please wait a moment and try again." |
| `model not found`, `does not exist` | `ConfigurationError` | passthrough |
| `model not loaded`, `still loading`, `warming up` | `ExternalServiceError` | "The local model is still loading. Please wait a few seconds and try again." |
| `connection refused`, `timed out`, `connecterror` | `NetworkError` | local-server hint (llama.cpp / Ollama) |
| `context length`, `token limit`, `max_tokens` | `ExternalServiceError` | "Content too large for the selected model…" |
| `413`, `payload too large` | `ExternalServiceError` | payload-size hint |
| `500`, `502`, `503`, `overloaded` | `ExternalServiceError` | "The AI provider is temporarily unavailable…" |
| (unmatched) | `ExternalServiceError` | `"AI service error: {truncated}"` + warning log |

A companion `classify_sidecar_error(tail_text) -> str | None` (v0.8.38) maps the last
~50 lines of a local sidecar's stderr to a one-line hint (e.g. `"failed to load model"`
→ "Model file could not be loaded — check the GGUF path and integrity.").

---

## 3. The `surreal-commands` job-submission pattern

Long-running work (source ingest, embeddings, podcast generation, Studio extract) is
queued to the **`surreal-commands`** worker rather than handled inline.

**Submission** (from `api/routers/sources.py:521`):

```python
import commands.source_commands  # noqa: F401  — ensures command is registered

command_input = SourceProcessingInput(
    source_id=str(source.id),
    content_state=content_state,
    notebook_ids=source_data.notebooks,
    transformations=transformation_ids,
    embed=source_data.embed,
)

command_id = await CommandService.submit_command_job(
    "open_notebook",   # app name
    "process_source",  # command name
    command_input.model_dump(),
)

source.command = ensure_record_id(command_id)  # command_id includes 'command:' prefix
await source.save()
```

> **Critical quirk**: `surreal_commands.submit_command` is **synchronous**; calling it
> from `async def` must be wrapped in `asyncio.to_thread`. `CommandService.submit_command_job`
> is the async wrapper used by routers.

**Status tracking** — `api/routers/commands.py`:

| Method | Path | Request / Query | Response model | Status |
|---|---|---|---|---|
| POST | `/api/commands/jobs` | `CommandExecutionRequest{command, app, input}` | `CommandJobResponse{job_id, status, message}` | 200 / 500 |
| GET | `/api/commands/jobs/{job_id}` | — | `CommandJobStatusResponse` | 200 / **404** if unknown / 500 |
| GET | `/api/commands/jobs` | `command_filter?, status_filter?, limit=50` | `list[dict]` | 200 / 500 |
| DELETE | `/api/commands/jobs/{job_id}` | — | `{job_id, cancelled}` | 200 / **404** / **409** (not cancellable) / 500 |
| GET | `/api/commands/registry/debug` | — | `{total_commands, commands_by_app, command_items}` | 200 |

```python
class CommandJobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    created: Optional[str] = None
    updated: Optional[str] = None
    progress: Optional[dict[str, Any]] = None
```

Statuses observed: `new`, `queued`, `running`, `completed`, `failed`, `canceled`.
The frontend polls every 2s while a source/episode status is in `{new, queued, running}`.

---

## 4. Router catalog

All routers live in `api/routers/`. Pydantic request/response schemas live in
`api/models.py` (shared) or inline in the router module.

### 4.1 `notebooks.py`

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| GET | `/api/notebooks` | `archived?`, `order_by="updated desc"` | `list[NotebookResponse]` | `order_by` validated against allowlist `{name, created, updated}` × `{asc, desc}` to block SurrealQL injection |
| POST | `/api/notebooks` | `NotebookCreate{name, description}` | `NotebookResponse` | |
| GET | `/api/notebooks/{id}/delete-preview` | — | `NotebookDeletePreview{note_count, exclusive_source_count, shared_source_count}` | |
| GET | `/api/notebooks/{id}` | — | `NotebookResponse` | 404 if missing |
| PUT | `/api/notebooks/{id}` | `NotebookUpdate{name?, description?, archived?}` | `NotebookResponse` | |
| POST | `/api/notebooks/{nb}/sources/{src}` | — | `{message}` | idempotent link via `RELATE $src->reference->$nb` |
| DELETE | `/api/notebooks/{nb}/sources/{src}` | — | `{message}` | unlink reference edge |
| DELETE | `/api/notebooks/{id}` | `delete_exclusive_sources=false` | `NotebookDeleteResponse{deleted_notes, deleted_sources, unlinked_sources}` | cascade; cleans LangGraph checkpoint threads (v0.8.48) |

Counts use SurrealDB edge traversal: `count(<-reference.in) as source_count`, `count(<-artifact.in) as note_count`.

```python
class NotebookResponse(BaseModel):
    id: str
    name: str
    description: str
    archived: bool
    created: Optional[str] = None
    updated: Optional[str] = None
    source_count: int
    note_count: int
```

### 4.2 `sources.py`

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/sources` | query filters | `list[SourceListResponse]` |
| POST | `/api/sources` | `SourceCreate` (JSON **or** multipart `UploadFile`) via `Depends(parse_source_form_data)` | `SourceResponse` |
| POST | `/api/sources/json` | `SourceCreate` | `SourceResponse` |
| GET | `/api/sources/{id}` | — | `SourceResponse` |
| GET | `/api/sources/{id}/download` | — | file stream |
| GET | `/api/sources/{id}/status` | — | `SourceStatusResponse` |
| PUT | `/api/sources/{id}` | update body | `SourceResponse` |
| POST | `/api/sources/{id}/retry` | — | `SourceResponse` |
| DELETE | `/api/sources/{id}` | — | `{message}` |
| GET | `/api/sources/{id}/insights` | — | `list[SourceInsightResponse]` |
| POST | `/api/sources/{id}/insights` | transformation body | insight job |

`type` ∈ `{link, upload, text}`. Upload path enforces `ONP_SOURCE_UPLOAD_MAX_BYTES`
(default 500 MB → **413** on overflow) and validates the file path is inside `UPLOADS_FOLDER`
(LFI guard). `async_processing=true` → queues `process_source` command; `false` → sync
`execute_command_sync`.

### 4.3 `notes.py`

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/notes` | filters | `list[NoteResponse]` |
| POST | `/api/notes` | `NoteCreate{title?, content, note_type="human", notebook_id?}` | `NoteResponse` |
| GET | `/api/notes/{id}` | — | `NoteResponse` |
| PUT | `/api/notes/{id}` | `NoteUpdate` | `NoteResponse` |
| DELETE | `/api/notes/{id}` | — | `{message}` |

`NoteResponse` carries `command_id` (the fire-and-forget `embed_note` job submitted on save).

### 4.4 `chat.py`

Session CRUD + execution + streaming. Key schemas:

```python
class ExecuteChatRequest(BaseModel):
    session_id: str
    message: str
    context: dict[str, Any]
    model_override: Optional[str] = None
    disabled_mcp_servers: Optional[List[str]] = None   # v0.8.42 per-turn MCP picker
    bypass_privacy_gate: bool = False                  # v0.8.63 explicit cloud consent

class ExecuteChatResponse(BaseModel):
    session_id: str
    messages: list[ChatMessage]
    selected_provider: Optional[str] = None     # 'local' | 'cloud' | None (smart router)
    selected_model_id: Optional[str] = None
    offline_fallback: Optional[Dict[str, Any]] = None
    mcp_tool_calls: Optional[List[Dict[str, Any]]] = None
    privacy_gated: Optional[bool] = None
    privacy_categories: Optional[List[str]] = None   # labels only, never secret values
    agent_state: Optional[str] = None            # 'complete' | 'clarify' | 'truncated'
```

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/chat/sessions` | `notebook_id` (req), `limit` (cap 1000) | `list[ChatSessionResponse]` |
| POST | `/api/chat/sessions` | `CreateSessionRequest` | `ChatSessionResponse` |
| GET | `/api/chat/sessions/{id}` | — | `ChatSessionResponse` |
| PUT | `/api/chat/sessions/{id}` | `UpdateSessionRequest` | `ChatSessionResponse` |
| DELETE | `/api/chat/sessions/{id}` | — | `SuccessResponse` |
| POST | `/api/chat/execute` | `ExecuteChatRequest` | `ExecuteChatResponse` |
| POST | `/api/chat/stream` | `ExecuteChatRequest` | **NDJSON stream** |
| POST | `/api/chat/context` | `BuildContextRequest` | `BuildContextResponse{context, token_count, char_count}` |

**`/api/chat/stream` wire format** — `StreamingResponse(media_type="application/x-ndjson")`
with headers `X-Accel-Buffering: no`, `Cache-Control: no-cache, no-transform`. The generator
`_stream_chat_events()` emits newline-delimited JSON objects:

- `{"type":"start","session_id":...}`
- per-token deltas filtered from LangGraph `astream_events` `on_chat_model_stream`
- `{"type":"error","detail":...}` on failure (partial-stream safe)

Per-session serialization uses `get_session_lock(full_session_id)` (manual acquire/finally
release across the multi-yield body) to prevent concurrent turns clobbering the checkpoint.
Client disconnects are detected between yields and stop the stream (saves local-LLM compute).

### 4.5 `source_chat.py`

Chat scoped to a single source. Routes under `/api/sources/{source_id}/chat/...`:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sources/{source_id}/chat/sessions` | create source-chat session |
| GET | `/api/sources/{source_id}/chat/sessions` | list |
| GET | `/api/sources/{source_id}/chat/sessions/{id}` | get |
| PUT | `/api/sources/{source_id}/chat/sessions/{id}` | update |
| DELETE | `/api/sources/{source_id}/chat/sessions/{id}` | delete |
| POST | `/api/sources/{source_id}/chat/sessions/{id}/messages` | **streaming** (`text/plain`, GZip-bypassed) |

Backed by the `source_chat` LangGraph with its own `AsyncSqliteSaver`.

### 4.6 `podcasts.py`

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/podcasts/generate` | `PodcastGenerationRequest` | `PodcastGenerationResponse` |
| GET | `/api/podcasts/jobs/{job_id}` | — | job status |
| GET | `/api/podcasts/episodes` | filters | `list[PodcastEpisodeResponse]` |
| GET | `/api/podcasts/episodes/{id}` | — | `PodcastEpisodeResponse` |
| GET | `/api/podcasts/episodes/{id}/audio` | — | audio stream |
| POST | `/api/podcasts/episodes/{id}/retry` | — | retry (no silent-audio fallback; TTS failure marks episode failed) |
| POST | `/api/podcasts/episodes/{id}/cancel` | — | cancel running job |
| PUT | `/api/podcasts/episodes/{id}/outline` | edited outline | staged-generation outline edit |
| POST | `/api/podcasts/episodes/{id}/approve-outline` | — | proceed to transcript/audio |
| DELETE | `/api/podcasts/episodes/{id}` | — | delete |
| POST | `/api/podcasts/suggest` | suggest body | `SuggestResponse` |

Jobs use `max_attempts: 1` to prevent duplicate episode records. Generation is orchestrated
by `api/podcast_service.py` (outline → transcript → TTS) via `surreal-commands`.

### 4.7 `transformations.py`

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/transformations` | — | `list[TransformationResponse]` |
| POST | `/api/transformations` | `TransformationCreate{name, title, description, prompt, apply_default}` | `TransformationResponse` |
| POST | `/api/transformations/{id}/optimize` | — | optimized prompt (SkillOpt) |
| POST | `/api/transformations/execute` | `TransformationExecuteRequest{transformation_id, input_text, model_id}` | `TransformationExecuteResponse{output, transformation_id, model_id}` |
| GET | `/api/transformations/default-prompt` | — | `DefaultPromptResponse` |
| PUT | `/api/transformations/default-prompt` | `DefaultPromptUpdate` | `DefaultPromptResponse` |
| GET | `/api/transformations/{id}` | — | `TransformationResponse` |
| PUT | `/api/transformations/{id}` | `TransformationUpdate` | `TransformationResponse` |
| DELETE | `/api/transformations/{id}` | — | `{message}` |

### 4.8 `models.py`

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/models` | — | `list[ModelResponse]` |
| POST | `/api/models` | `ModelCreate{name, provider, type, credential?}` | `ModelResponse` |
| DELETE | `/api/models/{id}` | — | `{message}` |
| POST | `/api/models/{id}/test` | — | `ModelTestResponse` |
| GET | `/api/models/defaults` | — | `DefaultModelsResponse` |
| PUT | `/api/models/defaults` | partial defaults | `DefaultModelsResponse` |
| GET | `/api/models/providers` | — | `ProviderAvailabilityResponse{available, unavailable, supported_types}` |
| GET/POST | `/api/models/sync/{provider}` & `/api/models/sync` | — | provider/all sync |
| GET | `/api/models/count/{provider}` | — | `ProviderModelCountResponse` |
| GET | `/api/models/by-provider/{provider}` | — | `list[ModelResponse]` |
| POST | `/api/models/auto-assign` & `/api/models/auto-assign-capability` | — | `AutoAssignResult` |

`DefaultModelsResponse` covers chat / transformation / large-context / TTS / STT /
embedding / tools / reasoning defaults plus the smart-router knobs (`auto_route_enabled`,
`auto_route_cloud`, `auto_route_provider_pref`).

### 4.9 `settings.py`

| Method | Path | Response |
|---|---|---|
| GET | `/api/settings` | `SettingsResponse` |
| PUT | `/api/settings` | `SettingsResponse` |
| GET | `/api/settings/observability` | `ObservabilityResponse` |

### 4.10 `system.py` (mounted without `/api` prefix — paths embed it)

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/system/env-refresh` | **own bearer** (`OPEN_NOTEBOOK_LAUNCHER_CONTROL_TOKEN`) | launcher → API env push (e.g. `n_ctx` after hot-swap); exempt from password middleware |
| GET | `/api/system/db-repair-needed` | password | |
| GET | `/api/system/network-status` | password | online/offline state |

### 4.11 `mcp.py` (paths embed `/api`)

| Method | Path | Status |
|---|---|---|
| GET | `/api/mcp` | list servers |
| GET | `/api/mcp/recommendations` | suggested connectors |
| GET | `/api/mcp/web-search` | web-search MCP config |
| POST | `/api/mcp` | **201** create |
| PATCH | `/api/mcp/{server_id}` | update |
| DELETE | `/api/mcp/{server_id}` | delete |
| POST | `/api/mcp/{server_id}/test` | connection test |

### 4.12 `gmail.py` (mounted at `/api`, internal prefix per route)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/gmail/status` | `GmailStatusResponse` |
| POST | `/api/gmail/credentials` | store OAuth client |
| POST | `/api/gmail/settings` | digest schedule |
| POST | `/api/gmail/disconnect` | |
| DELETE | `/api/gmail/credentials` | |
| GET | `/api/gmail/connect` | start OAuth flow |
| GET | `/api/gmail/callback` | OAuth redirect → `HTMLResponse` |
| POST | `/api/gmail/send-test` | test digest |

### 4.13 `credentials.py` — provider key management

| Method | Path | Notes |
|---|---|---|
| GET | `/api/credentials` | `?provider=` filter; **never returns api_key values** |
| GET | `/api/credentials/status` | `{configured, source, encryption_configured}` |
| GET | `/api/credentials/env-status` | which providers have env vars |
| GET | `/api/credentials/by-provider/{provider}` | |
| POST | `/api/credentials` | create (requires `OPEN_NOTEBOOK_ENCRYPTION_KEY`) |
| GET/PUT/DELETE | `/api/credentials/{id}` | get / update / delete |
| POST | `/api/credentials/{id}/test` | minimal upstream call via `connection_tester` |
| POST | `/api/credentials/{id}/discover` | list available models |
| POST | `/api/credentials/{id}/register-models` | register discovered |
| POST | `/api/credentials/migrate-from-env` | env → Credential records |
| POST | `/api/credentials/migrate-from-provider-config` | legacy ProviderConfig → Credential |

13 providers: simple-key (`openai`, `anthropic`, `google`, `groq`, `mistral`, `deepseek`,
`xai`, `openrouter`, `voyage`, `elevenlabs`), URL (`ollama`), multi-field (`azure`, `vertex`,
`openai_compatible`). URL fields pass `_validate_url()` SSRF guard (allows localhost/private
IPs for self-hosted servers).

### 4.14 Other routers

| Router | Representative paths |
|---|---|
| `search.py` | POST `/api/search`, POST `/api/search/ask` (NDJSON stream), POST `/api/search/ask/simple` |
| `studio.py` | POST `/api/generate` (one-shot upload + mode → notebook/podcast) |
| `insights.py` | GET/DELETE `/api/insights/{id}`, POST `/api/insights/{id}/save-as-note` |
| `embedding.py` | POST `/api/embed`, POST embedding ops |
| `embedding_rebuild.py` | mounted at `/api/embeddings` |
| `context.py` | POST `/api/notebooks/{id}/context` |
| `config.py` | GET `/api/config` (runtime config for the frontend; auth-exempt) |
| `episode_profiles.py`, `speaker_profiles.py` | podcast voice/profile CRUD |
| `exports.py`, `filesystem.py` | host filesystem picker + notebook/note export to disk |
| `local_models.py` | GET `/api/local-models/health` (auth-exempt splash poll) + sidecar mgmt |
| `launcher_prefs.py` | launcher env-var preferences UI |
| `languages.py` | GET `/api/languages` (podcast languages via pycountry+babel) |
| `onp.py` | desktop-wrapper endpoints |

---

## 5. Common router patterns

- **Async throughout**: every DB query, graph invoke, AI call is `await`-ed.
- **Typed-exception passthrough**: handlers re-raise `HTTPException` and `(NotFoundError, InvalidInputError)` *before* the broad `except Exception` (which returns generic 500), so the global handlers map them correctly (v0.7.179).
- **Sanitized 500 bodies**: internal errors log full detail but return a generic `detail` string (e.g. `/readyz` migration errors, decryption errors) to avoid leaking driver frames / paths / DSNs.
- **Repository functions**: `repo_query`, `repo_create`, `repo_upsert`, `ensure_record_id` from `open_notebook.database.repository`; lazy connection pool.
- **Datetime serialization**: `api/utils/iso.py:iso()` for Safari-safe `new Date()` compatibility.
- **No per-resource permission checks**: single-user model; all endpoints trust the password middleware (see doc 06).
