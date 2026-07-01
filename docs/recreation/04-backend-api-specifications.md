# 04 — Backend API Specifications

> Recreation reference for the **Open Notebook Plus** FastAPI backend
> (`api/` + `open_notebook/`), `desktop-app` branch. Runs on port **5055**
> (`uvicorn api.main:app`). FastAPI 0.104+ / Pydantic v2 / Python 3.11+.

The API is a thin HTTP layer over the domain models (`open_notebook.domain.*`,
`open_notebook.ai.models`, `open_notebook.podcasts.models`) and the LangGraph
workflows (`open_notebook.graphs.*`). Business logic mostly lives in the routers;
only four `*_service.py` modules do heavy orchestration
(`chat_service.py`, `podcast_service.py`, `command_service.py`,
`credentials_service.py`).

---

## 1. Application assembly (`api/main.py`)

### 1.1 Router registration — every router carries the `/api` prefix

```python
app.include_router(auth.router,            prefix="/api", tags=["auth"])
app.include_router(config.router,          prefix="/api", tags=["config"])
app.include_router(notebooks.router,       prefix="/api", tags=["notebooks"])
app.include_router(search.router,          prefix="/api", tags=["search"])
app.include_router(models.router,          prefix="/api", tags=["models"])
app.include_router(transformations.router, prefix="/api", tags=["transformations"])
app.include_router(notes.router,           prefix="/api", tags=["notes"])
app.include_router(onp.router,             prefix="/api", tags=["onp"])
app.include_router(gmail_router.router,    prefix="/api", tags=["onp-gmail"])
app.include_router(embedding.router,       prefix="/api", tags=["embedding"])
app.include_router(settings.router,        prefix="/api", tags=["settings"])
app.include_router(context.router,         prefix="/api", tags=["context"])
app.include_router(sources.router,         prefix="/api", tags=["sources"])
app.include_router(insights.router,        prefix="/api", tags=["insights"])
app.include_router(commands_router.router, prefix="/api", tags=["commands"])
app.include_router(podcasts.router,        prefix="/api", tags=["podcasts"])
app.include_router(studio.router,          prefix="/api", tags=["studio"])
app.include_router(episode_profiles.router,prefix="/api", tags=["episode-profiles"])
app.include_router(speaker_profiles.router,prefix="/api", tags=["speaker-profiles"])
app.include_router(chat.router,            prefix="/api", tags=["chat"])
app.include_router(source_chat.router,     prefix="/api", tags=["source-chat"])
app.include_router(credentials.router,     prefix="/api", tags=["credentials"])
app.include_router(languages.router,       prefix="/api", tags=["languages"])
app.include_router(filesystem.router,      prefix="/api", tags=["filesystem"])
app.include_router(exports.router,         prefix="/api", tags=["exports"])
# these routers already embed /api in their own paths → registered WITHOUT prefix:
app.include_router(_local_models_router.router, tags=["health"])
app.include_router(_mcp_router.router,          tags=["mcp"])
app.include_router(_launcher_prefs_router.router, tags=["launcher-prefs"])
app.include_router(_system_router.router,       tags=["system"])
app.include_router(_updates_router.router,      tags=["updates"])
```

Full router set (`api/routers/`, 32 files):
`auth, chat, commands, config, context, credentials, embedding,
embedding_rebuild, episode_profiles, exports, filesystem, gmail, insights,
languages, launcher_prefs, local_models, mcp, models, notebooks, notes, onp,
podcasts, search, settings, source_chat, sources, speaker_profiles, studio,
system, transformations, updates` (+ `__init__.py`).

### 1.2 Middleware stack (order matters; CORS is outermost)

Registered inner→outer in `main.py`:
1. **`PasswordAuthMiddleware`** — checks `Authorization: Bearer {password}`
   against `OPEN_NOTEBOOK_PASSWORD` (default `open-notebook-change-me`; Docker
   secret via `OPEN_NOTEBOOK_PASSWORD_FILE`). `excluded_paths` include `/`,
   `/health`, `/livez`, `/readyz`, `/healthz/deep`, `/api/healthz/deep`,
   `/api/system/env-refresh` (own launcher-token auth), `/docs`, `/openapi.json`,
   `/redoc`, `/api/auth/status`, `/api/config`, `/api/version`,
   `/api/local-models/health`, `/metrics`.
2. **`SelectiveGZipMiddleware`** (`minimum_size=1000`) — GZip for large JSON,
   but **bypassed entirely for streaming paths** (`/api/chat/stream`,
   `/api/search/ask`, and any `POST …/messages`) so token chunks flush in real
   time (audit H1).
3. **`SecurityHeadersMiddleware`** — X-Content-Type-Options, X-Frame-Options,
   Referrer-Policy, CSP (skipped on `/docs`).
4. **`PrometheusMetricsMiddleware`** — records method/route/status/duration at
   `/metrics`.
5. **`RequestIDMiddleware`** — UUID4 per request → `X-Request-ID` + loguru bind.
6. **`RateLimitMiddleware`** — env-gated (`ONP_RATE_LIMIT_PER_MIN`, default off).
7. **`CORSMiddleware`** (outermost):
   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=CORS_ALLOWED_ORIGINS,          # default ["*"]
       allow_credentials=not CORS_IS_DEFAULT_WILDCARD,  # honest wildcard contract
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```

### 1.3 Lifespan handler (`@asynccontextmanager async def lifespan`)

Startup order:
1. `configure_logging("api")` → rotated file sink (`~/.open-notebook-plus/logs/api.log`).
2. Encryption-key check — warn if neither `OPEN_NOTEBOOK_ENCRYPTION_KEY` nor
   `OPEN_NOTEBOOK_ENCRYPTION_KEYS` is set.
3. **Run migrations**: `AsyncMigrationManager().run_migration_up()`. **Fail-fast**
   — a migration error raises `RuntimeError` and the API refuses to start.
4. Podcast profile data migration (legacy provider/model strings → Model records).
5. `dedup_edges` sweep; reap stale commands (start + every 5 min).
6. Pre-warm the DB pool; start the Gmail digest scheduler + checkpoint-prune loop.

Shutdown: cancel background tasks, drain DB pool, close `AsyncSqliteSaver`
connections.

Health routes: `/health` (back-compat), `/livez`, `/readyz`, `/healthz/deep`.

### 1.4 Global exception handlers + HTTP-status map

Custom exceptions from `open_notebook.exceptions` are mapped to HTTP codes; every
error response re-injects CORS headers (`_cors_headers(request)`):

```python
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail},
                        headers={**(exc.headers or {}), **_cors_headers(request)})

@app.exception_handler(NotFoundError)        # → 404
@app.exception_handler(InvalidInputError)    # → 400
@app.exception_handler(AuthenticationError)  # → 401
@app.exception_handler(RateLimitError)       # → 429
@app.exception_handler(ConfigurationError)   # → 422
@app.exception_handler(NetworkError)         # → 502
@app.exception_handler(ExternalServiceError) # → 502
@app.exception_handler(OpenNotebookError)    # → 500 (base)
```

| Exception | Status | When |
|-----------|--------|------|
| `NotFoundError` | 404 | resource missing |
| `InvalidInputError` | 400 | bad request data / bad pagination |
| `AuthenticationError` | 401 | invalid/missing key |
| `RateLimitError` | 429 | provider rate limit |
| `ConfigurationError` | 422 | model not found / misconfig |
| `NetworkError` | 502 | can't reach provider |
| `ExternalServiceError` | 502 | provider 5xx / context-length |
| `OpenNotebookError` | 500 | anything else |

LangGraph nodes call `classify_error()` (`open_notebook.utils.error_classifier`)
to turn raw LLM/Esperanto exceptions into these typed exceptions with
user-friendly messages before they reach the handlers.

### 1.5 The HTTPException-reraise convention

Every non-trivial endpoint follows this pattern so typed 4xx/5xx are not
clobbered to 500 by the catch-all. Representative example
(`api/routers/sources.py`, `GET /sources/{source_id}`):

```python
@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(source_id: str):
    try:
        source = await Source.get(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        ...
        if source.command:
            try:
                status = await source.get_status()
                processing_info = await source.get_processing_progress()
            except HTTPException:
                raise                       # re-raise typed HTTP errors
            except Exception as e:
                logger.warning(f"Failed to get status for source {source_id}: {e}")
                status = "unknown"
        ...
        return SourceResponse(...)
    except HTTPException:                    # (1) let 4xx/5xx bubble unchanged
        raise
    except NotFoundError:                    # (2) map typed domain error
        raise HTTPException(status_code=404, detail="Source not found")
    except Exception as e:                   # (3) everything else → 500
        logger.error(f"Error fetching source {source_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching source")
```

Streaming/notebook endpoints add `except (NotFoundError, InvalidInputError): raise`
before the catch-all (see `GET /notebooks/{id}/suggested-questions`).

---

## 2. Representative Pydantic schemas (`api/models.py` + service files)

```python
class NotebookCreate(BaseModel):
    name: str
    description: str = ""

class NoteCreate(BaseModel):
    title: Optional[str] = None
    content: str                      # required, must be non-blank
    note_type: Optional[str] = "human"   # "human" | "ai"
    notebook_id: Optional[str] = None

class SourceCreate(BaseModel):
    notebook_id: Optional[str] = None    # deprecated single-link
    notebooks: Optional[list[str]] = None  # multi-notebook
    type: str                            # "link" | "upload" | "text"
    url: Optional[str] = None            # link
    file_path: Optional[str] = None      # upload
    content: Optional[str] = None        # text
    title: Optional[str] = None
    topics: Optional[list[str]] = []
    provenance: Optional[dict[str, Any]] = {}
    source_type: Optional[Literal["link","upload","text","web_import","deep_research_report"]] = None
    transformations: Optional[list[str]] = []
    embed: bool = True
    delete_source: bool = False
    async_processing: bool = True

class SearchRequest(BaseModel):
    query: str
    type: Literal["text", "vector"] = "text"
    limit: int = 100                     # 1..1000
    search_sources: bool = True
    search_notes: bool = True
    minimum_score: float = 0.3           # vector floor

class AskRequest(BaseModel):
    question: str
    strategy_model: str
    answer_model: str
    final_answer_model: str

# api/routers/chat.py
class ExecuteChatRequest(BaseModel):
    session_id: str
    message: str
    context: dict[str, Any]              # sources+notes, from /chat/context
    model_override: Optional[str] = None
    disabled_mcp_servers: Optional[List[str]] = None
    bypass_privacy_gate: bool = False

class ExecuteChatResponse(BaseModel):
    session_id: str
    messages: list[ChatMessage]
    selected_provider: Optional[str]     # "local" | "cloud" (smart router)
    selected_model_id: Optional[str]
    offline_fallback: Optional[Dict[str, Any]]
    mcp_tool_calls: Optional[List[Dict[str, Any]]]
    privacy_gated: Optional[bool]
    privacy_categories: Optional[List[str]]
    agent_state: Optional[str]           # FSM terminal state

# api/podcast_service.py
class PodcastGenerationRequest(BaseModel):
    episode_profile: str
    speaker_profile: str
    episode_name: str
    content: Optional[str] = None
    notebook_id: Optional[str] = None
    briefing_suffix: Optional[str] = None
    episode_length: Optional[str] = None # "short"|"medium"|"long" overrides profile
    review_outline: bool = False

# api/models.py — credentials
class CreateCredentialRequest(BaseModel):
    name: str
    provider: str                        # openai/anthropic/.../ollama/azure/vertex/openai_compatible
    modalities: list[str]                # language/embedding/text_to_speech/speech_to_text
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    endpoint: Optional[str] = None       # azure
    api_version: Optional[str] = None
    endpoint_llm / endpoint_embedding / endpoint_stt / endpoint_tts: Optional[str]  # azure
    project / location / credentials_path: Optional[str]  # vertex
```

---

## 3. Endpoint catalog by router

Paths below are the **full path including the `/api` prefix**. Method · path ·
request body · response · logic.

### 3.1 `notebooks.py`

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| GET | `/api/notebooks` | — | `list[NotebookResponse]` | List; `?archived=`, `?order_by=` (allowlist name/created/updated). Computes `source_count`/`note_count` via reference/artifact edges. |
| POST | `/api/notebooks` | `NotebookCreate` | `NotebookResponse` | Create; returns id + ISO timestamps + zero counts. |
| GET | `/api/notebooks/{id}` | — | `NotebookResponse` | Fetch one w/ counts. |
| PUT | `/api/notebooks/{id}` | `NotebookUpdate` | `NotebookResponse` | Update name/description/archived. |
| DELETE | `/api/notebooks/{id}` | — | `NotebookDeleteResponse` | Cascade delete (see doc 03 §5.5); cleans LangGraph checkpoint threads for cascade-deleted sessions. |
| GET | `/api/notebooks/{id}/delete-preview` | — | `NotebookDeletePreview` | `{note_count, exclusive_source_count, shared_source_count}` for the confirm dialog. |
| POST | `/api/notebooks/{id}/sources/{source_id}` | — | success | Idempotent `reference` edge link. |
| DELETE | `/api/notebooks/{id}/sources/{source_id}` | — | success | Unlink; optionally delete source if orphaned. |
| GET | `/api/notebooks/{id}/suggested-questions` | `?limit=4` (1..8) | `{"questions":[...]}` | LLM starter questions grounded in source titles/topics; **best-effort** — returns `[]` on any generation failure, `NotFound/InvalidInput` still surface. 30s timeout. |
| GET | `/api/notebooks/{id}/graph` | — | `NotebookGraphResponse` | Mind-map: `Notebook.get_graph()` → hub + source/note nodes + reference/artifact edges. |
| POST | `/api/notebooks/{id}/discover-sources` | `DiscoverSourcesRequest` | `DiscoverSourcesResponse` | Guarded web search (`open_notebook.tools.web_search`); returns `{enabled, provider, results:[{title,url,snippet}]}`. `enabled=False` (HTTP 200) when no provider configured; search errors degrade to empty, never 500. |

### 3.2 `sources.py`

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| GET | `/api/sources` | — | `list[SourceListResponse]` | List; filter by notebook/status; summary preview + insights_count. |
| POST | `/api/sources` | `SourceCreate` | `SourceResponse` | Ingest link/upload/text; async extract→embed→transform; returns command_id + status. |
| POST | `/api/sources/json` | `SourceCreate` | `SourceResponse` | JSON variant (testing). |
| GET | `/api/sources/{id}` | — | `SourceResponse` | Full detail: full_text, embedded_chunks, notebooks list, insights_count, file_available, extraction_quality. |
| PUT | `/api/sources/{id}` | `SourceUpdate` | `SourceResponse` | Update title/topics/provenance/source_type. |
| DELETE | `/api/sources/{id}` | — | success | Delete + unlink + file cleanup (see doc 03 §5.2). |
| POST | `/api/sources/{id}/retry` | — | `SourceResponse` | Re-trigger failed extraction/embed/transform. |
| GET | `/api/sources/{id}/status` | — | `SourceStatusResponse` | Poll processing status + `processing_info` + `error_message`. |
| HEAD | `/api/sources/{id}/download` | — | 200/404/500 | File-availability probe. |
| GET | `/api/sources/{id}/download` | — | `FileResponse` | Stream original file, path-containment checked vs upload root. |
| POST | `/api/sources/{id}/locate-passage` | `LocatePassageRequest` | `LocatePassageResponse` | (v0.8.78) Find a citation passage's char offsets in `full_text` for jump-to-highlight; returns `{start,end,snippet}`. |
| GET | `/api/sources/{id}/insights` | — | `list[SourceInsightResponse]` | List insights for the source. |
| POST | `/api/sources/{id}/insights` | `CreateSourceInsightRequest` | `InsightCreationResponse` | Apply a transformation → insight (async via `create_insight` command). |

### 3.3 `notes.py`

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| GET | `/api/notes` | `?notebook_id=` | `list[NoteResponse]` | List (paginated). |
| POST | `/api/notes` | `NoteCreate` | `NoteResponse` | Create; optional notebook link; type human/ai. `Note.save()` fires `embed_note`. |
| GET | `/api/notes/{id}` | — | `NoteResponse` | Fetch. |
| PUT | `/api/notes/{id}` | `NoteUpdate` | `NoteResponse` | Update content/title/type. |
| DELETE | `/api/notes/{id}` | — | success | Delete + sweep artifact edges. |

### 3.4 `chat.py` (session CRUD + turn execution + SSE)

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| GET | `/api/chat/sessions` | `?notebook_id&limit=100&offset=0` | `list[ChatSessionResponse]` | Parallel LangGraph checkpoint reads (N+1 fix). |
| POST | `/api/chat/sessions` | `CreateSessionRequest` | `ChatSessionResponse` | New session, `refers_to` link to notebook; optional title + model_override. |
| GET | `/api/chat/sessions/{id}` | — | `ChatSessionWithMessagesResponse` | Session + messages from checkpoint. |
| PUT | `/api/chat/sessions/{id}` | `UpdateSessionRequest` | `ChatSessionResponse` | Update title/model_override/disabled_mcp_servers. |
| DELETE | `/api/chat/sessions/{id}` | — | success | Delete session; fire `memory_summarize_session` if configured; clean checkpoints. |
| POST | `/api/chat/execute` | `ExecuteChatRequest` | `ExecuteChatResponse` | One synchronous chat turn; returns messages + `selected_provider` (smart router) + `mcp_tool_calls` + privacy info. |
| POST | `/api/chat/stream` | `ExecuteChatRequest` | **SSE / NDJSON** | Stream tokens (`application/x-ndjson`); GZip-exempt; per-token `is_disconnected()` check. |
| POST | `/api/chat/context` | `BuildContextRequest` | `BuildContextResponse` | Build notebook context (sources+notes) + token/char counts. |

**Streaming pattern**: `StreamingResponse` yielding NDJSON lines
`{"type": ..., "data": ...}` / `{"token": "..."}`. The handler polls
`request.is_disconnected()` each token and cancels the LangGraph reader with
`reader.cancel()` before release (recurring bug class per CLAUDE.md).

### 3.5 `source_chat.py`

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| POST | `/api/sources/{sid}/chat/sessions` | `CreateSourceChatSessionRequest` | `SourceChatSessionResponse` | Session scoped to ONE source (`refers_to` → source). |
| GET | `/api/sources/{sid}/chat/sessions` | — | `list[...]` | List source-chat sessions. |
| GET | `/api/sources/{sid}/chat/sessions/{id}` | — | `...WithMessages` | Session + messages. |
| PUT | `/api/sources/{sid}/chat/sessions/{id}` | `Update...` | `...Response` | Update title/model_override. |
| DELETE | `/api/sources/{sid}/chat/sessions/{id}` | — | success | Delete. |
| POST | `/api/sources/{sid}/chat/sessions/{id}/messages` | `ExecuteSourceChatRequest` | **SSE / NDJSON** | Stream a turn; context = the source's `full_text` only. |

### 3.6 `search.py` (search + /ask)

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| POST | `/api/search` | `SearchRequest` | `SearchResponse` | Text (BM25 `fn::text_search`) or vector (`fn::vector_search`) search across sources+notes; returns results + total_count + search_type. |
| POST | `/api/search/ask` | `AskRequest` | **SSE / NDJSON** | Ask graph: strategy → retrieve → synthesize; streams the final answer token-by-token (GZip-exempt). |
| POST | `/api/search/ask/simple` | `AskRequest` | `AskResponse` | Non-streaming ask. |

### 3.7 `podcasts.py`

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| POST | `/api/podcasts/generate` | `PodcastGenerationRequest` | `PodcastGenerationResponse` | Submit async job (outline→transcript→TTS); returns job_id; `review_outline` stops after outline. |
| GET | `/api/podcasts/jobs/{job_id}` | — | `CommandJobStatusResponse` | Poll generation job. |
| GET | `/api/podcasts/episodes` | — | `list[PodcastEpisodeResponse]` | List episodes (name, profiles, briefing, audio_file, transcript, outline, generation_stage). |
| GET | `/api/podcasts/episodes/{id}` | — | `PodcastEpisodeResponse` | Fetch episode. |
| GET | `/api/podcasts/episodes/{id}/audio` | — | `FileResponse` | Stream audio (path-containment checked). |
| POST | `/api/podcasts/episodes/{id}/retry` | — | `PodcastEpisodeResponse` | Retry failed episode (per-episode lock; `max_attempts:1` so no dup records). |
| POST | `/api/podcasts/episodes/{id}/cancel` | — | success | Set `cancel_requested`; worker polls + aborts. |
| PUT | `/api/podcasts/episodes/{id}/outline` | `OutlineUpdateRequest` | `PodcastEpisodeResponse` | Edit outline in review workflow. |
| POST | `/api/podcasts/episodes/{id}/approve-outline` | — | `PodcastEpisodeResponse` | Approve outline → resume transcript + TTS. |
| DELETE | `/api/podcasts/episodes/{id}` | — | success | Delete episode + audio. |
| POST | `/api/podcasts/suggest` | `SuggestRequest` | `SuggestResponse` | One-shot outline suggestion from content. |

Episode/speaker profile CRUD lives in `episode_profiles.py` /
`speaker_profiles.py` (`GET/POST/PUT/DELETE /api/episode-profiles`,
`/api/speaker-profiles`).

### 3.8 `transformations.py`

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| GET | `/api/transformations` | — | `list[TransformationResponse]` | List (user + built-in summarize/key_topics). |
| POST | `/api/transformations` | `TransformationCreate` | `TransformationResponse` | Create prompt template. |
| GET | `/api/transformations/{id}` | — | `TransformationResponse` | Fetch. |
| PUT | `/api/transformations/{id}` | `TransformationUpdate` | `TransformationResponse` | Update. |
| DELETE | `/api/transformations/{id}` | — | success | Delete. |
| POST | `/api/transformations/{id}/optimize` | — | `TransformationResponse` | LLM-rewrite the prompt. |
| POST | `/api/transformations/execute` | `TransformationExecuteRequest` | `TransformationExecuteResponse` | Apply a transformation to input text with a chosen model. |
| GET/PUT | `/api/transformations/default-prompt` | `DefaultPromptUpdate` | `DefaultPromptResponse` | Read/update `DefaultPrompts.transformation_instructions`. |

### 3.9 `credentials.py` (prefix `/api/credentials`)

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| GET | `/api/credentials/status` | — | `ApiKeyStatusResponse` | `{configured:{provider:bool}, source:{provider:"database"|"environment"|"none"}, encryption_configured:bool}`. |
| GET | `/api/credentials/env-status` | — | dict | Which providers have env keys. |
| GET | `/api/credentials` | `?provider=` | `list[CredentialResponse]` | List; **never returns api_key** (only `has_api_key`). |
| GET | `/api/credentials/by-provider/{provider}` | — | `list[...]` | Credentials for provider. |
| POST | `/api/credentials` | `CreateCredentialRequest` | `CredentialResponse` | Create; api_key Fernet-encrypted; URL fields SSRF-validated. |
| GET | `/api/credentials/{id}` | — | `CredentialResponse` | Metadata (no key). |
| PUT | `/api/credentials/{id}` | `UpdateCredentialRequest` | `CredentialResponse` | Update; re-validates URLs. |
| DELETE | `/api/credentials/{id}` | — | `CredentialDeleteResponse` | Delete + cascade linked models. |
| POST | `/api/credentials/{id}/test` | — | `TestConnectionResponse` | Test via `connection_tester` (cheapest model per provider). |
| POST | `/api/credentials/{id}/discover` | — | `DiscoverModelsResponse` | Discover provider models. |
| POST | `/api/credentials/{id}/register-models` | `RegisterModelsRequest` | `RegisterModelsResponse` | Persist discovered models as Model records. |
| POST | `/api/credentials/migrate-from-provider-config` | — | `MigrationResult` | Legacy ProviderConfig → Credentials. |
| POST | `/api/credentials/migrate-from-env` | — | `MigrationResult` | Env vars → Credentials. |
| POST | `/api/credentials/detect-osaurus` | — | dict | Auto-detect local Ollama/LM Studio. |

### 3.10 `models.py`

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| GET | `/api/models` | — | `list[ModelResponse]` | List Model records. |
| POST | `/api/models` | `ModelCreate` | `ModelResponse` | Create (name, provider, type, optional credential_id). |
| GET | `/api/models/{id}` | — | `ModelResponse` | Fetch. |
| DELETE | `/api/models/{id}` | — | success | Delete (nulls DefaultModels refs). |
| POST | `/api/models/{id}/test` | — | `ModelTestResponse` | Single-prompt availability test. |
| GET/PUT | `/api/models/defaults` | `DefaultModelsResponse` | `DefaultModelsResponse` | Read/set per-capability defaults. |
| GET | `/api/models/providers` | — | `ProviderAvailabilityResponse` | Providers + supported types. |
| GET | `/api/models/by-provider/{provider}` | — | `list[ModelResponse]` | Models for provider. |
| GET | `/api/models/count/{provider}` | — | `ProviderModelCountResponse` | Count per type. |
| POST | `/api/models/sync/{provider}` · `/api/models/sync` | — | sync responses | Discover + register models. |
| POST | `/api/models/auto-assign` · `/api/models/auto-assign-capability` | — | `AutoAssignResult` | Auto-pick defaults. |

### 3.11 `settings.py`

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| GET | `/api/settings` | — | `SettingsResponse` | `ContentSettings`: doc/url engines, embedding option, auto-delete, YouTube langs, offline_mode, auto_summarize/auto_extract toggles. |
| PUT | `/api/settings` | `SettingsUpdate` | `SettingsResponse` | Update (engine values validated against ContentSettings allowlists). |
| GET | `/api/settings/observability` | — | `ObservabilityResponse` | Logging/metrics settings. |

### 3.12 `system.py` (prefix `/api/system`)

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| POST | `/api/system/env-refresh` | — | dict | Launcher→API env push (e.g. `n_ctx` after hot-swap); auth via `OPEN_NOTEBOOK_LAUNCHER_CONTROL_TOKEN` bearer (bypasses password middleware). |
| GET | `/api/system/db-repair-needed` | — | dict | Corruption/repair-needed detection for the launcher UI. |
| GET | `/api/system/network-status` | — | dict | online / offline / forced-offline. |

### 3.13 `commands.py`

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| POST | `/api/commands/jobs` | `CommandExecutionRequest` | `CommandJobResponse` | Submit a surreal-commands job (embed/podcast/source). |
| GET | `/api/commands/jobs/{job_id}` | — | `CommandJobStatusResponse` | Poll status (new/queued/running/completed/failed). |
| GET | `/api/commands/jobs` | — | `list[dict]` | Recent commands. |
| DELETE | `/api/commands/jobs/{job_id}` | — | success | Cancel job. |
| GET | `/api/commands/registry/debug` | — | dict | List registered commands (diagnostics). |

### 3.14 `insights.py`

| Method | Path | Body | Response | Logic |
|--------|------|------|----------|-------|
| GET | `/api/insights/{id}` | — | `SourceInsightResponse` | Fetch insight. |
| DELETE | `/api/insights/{id}` | — | success | Delete. |
| POST | `/api/insights/{id}/save-as-note` | `SaveAsNoteRequest` | `NoteResponse` | `SourceInsight.save_as_note()` → Note, linked to notebook. |

### 3.15 `context.py` / `config.py`

- `POST /api/notebooks/{id}/context` (`ContextRequest` → `ContextResponse`) —
  build sources+notes context filtered by inclusion levels; returns lists +
  `total_tokens`.
- `GET /api/config` — system config (version, features, DB health); read-only,
  auth-exempt (Setup Wizard polls it).

### 3.16 Secondary routers (summary)

- `auth.py` — `POST /api/auth/password` (validate), `GET /api/auth/status` (auth-exempt).
- `embedding.py` / `embedding_rebuild.py` — sync embed + async full rebuild
  (`POST /api/embeddings/rebuild`, `GET …/rebuild/{job_id}`).
- `exports.py` — `POST /api/notebooks/{id}/export` (markdown/zip; paperless-ready).
- `filesystem.py` — host file-picker (`/api/filesystem/list`, `/mkdir`).
- `languages.py` — `GET /api/languages` (podcast languages via pycountry+babel).
- `onp.py` / `gmail.py` — ONP desktop-wrapper + Gmail digest endpoints.
- `studio.py` — Evidence Studio generation + upload (`/api/studio/*`).
- `mcp.py` — MCP server registry CRUD (`GET/POST/PUT/DELETE/PATCH /api/mcp/*`,
  `POST /api/mcp/{id}/test`; URL fields SSRF-validated). See doc 08.
- `local_models.py` — local sidecar health + GGUF inventory + role routing +
  download/benchmark jobs (`/api/local-models/*`). See doc 08.
- `launcher_prefs.py` / `updates.py` — launcher env-var prefs; in-app update notifier.

---

## 4. Cross-cutting conventions

- **Async everywhere** — routers `await` domain models / graph `ainvoke`.
- **Config override** — per-request model override passed via LangGraph
  `RunnableConfig` to `graph.ainvoke(config=...)`; not persisted.
- **Fire-and-forget jobs** — long work (embeddings, podcasts, insights) goes to
  surreal-commands; the router returns a `command_id`/`job_id` and the client
  polls `/api/commands/jobs/{id}` (or the podcast/source status endpoints).
- **Streaming** — `/api/chat/stream`, `/api/search/ask`, source-chat `…/messages`
  return NDJSON; they are exempt from GZip so tokens flush in real time; handlers
  check `is_disconnected()` and cancel readers on client close.
- **Interactive docs** — Swagger at `/docs`, OpenAPI at `/openapi.json`
  (auth-exempt — disable before any non-local deployment).
