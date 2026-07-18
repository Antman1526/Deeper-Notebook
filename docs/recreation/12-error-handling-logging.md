# 12 — Error Handling & Logging

> Recreation reference for Open Notebook Plus error taxonomy, classification,
> global HTTP handlers, the HTTPException re-raise convention (with its AST
> meta-test), loguru configuration, SSE disconnect handling, DB auto-repair, and
> surreal-commands retry policy. Versions: loguru logging, FastAPI `>=0.136.3`,
> LangGraph `>=1.0.10`, cryptography via `cryptography.fernet`.

The philosophy: **raw provider/driver exceptions never reach the user**. Graph
nodes and SSE handlers convert them to a typed `OpenNotebookError` subclass with a
user-friendly message; global FastAPI handlers map each subclass to an HTTP status.

---

## 1. Exception hierarchy (`open_notebook/exceptions.py`)

All rooted at `OpenNotebookError(Exception)`:

```python
class OpenNotebookError(Exception): ...           # base
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

No custom `__init__` — they carry a message string only. The message is the
user-facing text (already sanitized by `classify_error`).

---

## 2. `classify_error` — keyword → (type, message) (`open_notebook/utils/error_classifier.py`)

A blocklist-of-rules matcher. Each rule is `(keywords, exc_class, message_or_None)`.
The exception's *type name* and *stringified message* are lowercased and joined into
one haystack (`f"{error_type_name}: {error_str}"`), then rules are checked in order;
first keyword hit wins. `None` message ⇒ pass the original (truncated) exception text
through.

```python
_CLASSIFICATION_RULES = [
  (["authentication","unauthorized","invalid api key","invalid_api_key","401"],
     AuthenticationError, "Authentication failed. Please check your API key in Settings -> Credentials."),
  (["rate limit","rate_limit","429","too many requests","quota exceeded"],
     RateLimitError, "Rate limit exceeded. Please wait a moment and try again."),
  (["model not found","does not exist","model_not_found"], ConfigurationError, None),
  (["no model configured","please go to settings"],       ConfigurationError, None),
  (["model not loaded","model is loading","still loading","model loading","model unavailable",
    "no model loaded","not ready","warming up"],
     ExternalServiceError, "The local model is still loading. Please wait a few seconds and try again."),
  (["connecterror","timeoutexception","connection refused","connection error","timed out","timeout"],
     NetworkError, "Could not reach the AI model server. If you're using a local model (llama.cpp / Ollama), make sure it's running. Otherwise check your network connection and provider URL."),
  (["context length","token limit","maximum context","context_length_exceeded","max_tokens"],
     ExternalServiceError, "Content too large for the selected model. Try using a smaller selection or a model with a larger context window."),
  (["413","payload too large","request entity too large"], ExternalServiceError, "The request payload is too large for the AI provider. ..."),
  (["500","502","503","service unavailable","overloaded","internal server error"],
     ExternalServiceError, "The AI provider is temporarily unavailable. Please try again in a few minutes."),
]

def classify_error(exception) -> tuple[type[OpenNotebookError], str]:
    combined = f"{type(exception).__name__.lower()}: {str(exception).lower()}"
    for keywords, exc_class, message in _CLASSIFICATION_RULES:
        for keyword in keywords:
            if keyword in combined:
                return exc_class, (message if message is not None else _truncate(str(exception)))
    logger.warning(f"Unclassified LLM error ({type(exception).__name__}): {exception}")
    return ExternalServiceError, f"AI service error: {_truncate(str(exception))}"
```

`_truncate(text, max_length=200)` caps pass-through messages to avoid leaking verbose
internals. Local-model states ("still loading", "warming up", connection-refused) are
first-class because the desktop fork bundles llama-cpp-python whose cold start can be
10–30s.

**Node usage pattern** (every graph node):

```python
try:
    ...
except OpenNotebookError:
    raise                                  # already-typed → propagate unchanged
except Exception as e:
    error_class, user_message = classify_error(e)
    raise error_class(user_message) from e
```

### 2.1 Sidecar stderr classification

`classify_sidecar_error(tail_text)` maps the last ~50 lines of a sidecar
subprocess's stderr to a user hint via `_SIDECAR_PATTERNS` (ordered, first-match,
case-insensitive substring): `"failed to load model"`, `"out of memory"`,
`"cuda error"`, `"metal error"`, `"address already in use"`, `"segmentation fault"`,
`"killed: 9"`, etc. Returns `None` if nothing matches (UI shows the raw tail). Consumed
by `/healthz/sidecars/{kind}/log`.

---

## 3. Global exception handlers (`api/main.py`)

Each typed exception → status code; all responses carry CORS headers via
`_cors_headers(request)` (reflects allowed Origin, omits it for disallowed origins so
error bodies can't leak cross-origin):

| Handler | Exception | Status |
|---|---|---|
| `custom_http_exception_handler` | `StarletteHTTPException` | passthrough `exc.status_code` |
| `not_found_error_handler` | `NotFoundError` | 404 |
| `invalid_input_error_handler` | `InvalidInputError` | 400 |
| `authentication_error_handler` | `AuthenticationError` | 401 |
| `rate_limit_error_handler` | `RateLimitError` | 429 |
| `configuration_error_handler` | `ConfigurationError` | 422 |
| `network_error_handler` | `NetworkError` | 502 |
| `external_service_error_handler` | `ExternalServiceError` | 502 |
| `open_notebook_error_handler` | `OpenNotebookError` (base) | 500 |

```python
@app.exception_handler(NetworkError)
async def network_error_handler(request: Request, exc: NetworkError):
    return JSONResponse(status_code=502, content={"detail": str(exc)}, headers=_cors_headers(request))
```

Ordering: the base `OpenNotebookError` handler is registered so *any* unmapped subclass
falls back to 500. Frontend `getApiErrorMessage()` (`lib/utils/error-handler.ts`) tries
i18n first, else shows the backend `detail` verbatim.

---

## 4. HTTPException re-raise convention + AST meta-test

### 4.1 The convention

The recurring bug: a broad `except Exception` catches an *intentional*
`HTTPException(404)` and clobbers it to `HTTPException(500)`. The rule for every
function in `api/routers/*.py`:

```python
try:
    thing = await fetch(id)          # may raise HTTPException(404)
    ...
except HTTPException:                # MUST come first
    raise
except Exception as e:
    raise HTTPException(500, detail=str(e))
```

Whitelist escape hatch: append `# noqa: HTTP_RAISE` to the `except Exception:` line.

### 4.2 The enforcing meta-test (`tests/test_v0_7_135_meta.py`)

Parametrized over every `api/routers/*.py` (except `__init__.py`). It parses each file
with `ast`, and for every function walks its `try` blocks:

```python
def _exception_clause_raises_httpexception(handler) -> bool:
    # True if an `except Exception:` body contains `raise HTTPException(...)`
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            func = node.exc.func
            if (isinstance(func, ast.Name) and func.id == "HTTPException") \
               or (isinstance(func, ast.Attribute) and func.attr == "HTTPException"):
                return True
    return False

def _try_block_has_httpexception_before_generic(node) -> bool:
    # True if `except HTTPException:` with a re-raise appears BEFORE any `except Exception:`
    saw_httpexception = False
    for handler in node.handlers:
        if _is_exception_name(handler.type, "HTTPException"):
            for child in ast.walk(handler):
                if isinstance(child, ast.Raise) and child.exc is None:
                    saw_httpexception = True; break
        if _is_exception_name(handler.type, "Exception") and not saw_httpexception:
            return False
    return True
```

A function is flagged when it has a generic `except Exception` that raises
`HTTPException(500)` **and** no `except HTTPException: raise` precedes it **and** no
`# noqa: HTTP_RAISE`. Bare `except:` counts as catching everything. Three self-tests
prove the walker flags a synthetic bug, accepts the correct pattern, and honours the
whitelist. This is what "enforced by tests" means for the reraise convention.

---

## 5. Loguru configuration & sinks (`open_notebook/logging.py`)

`configure_logging(component)` is called first in the API lifespan (before migrations)
so startup errors land in a file:

- Rotated **file sink** at `~/.open-notebook-plus/logs/<component>.log` (e.g. `api.log`).
- **Rotation**: 20 MB per file. **Retention**: 14 days.
- **Level**: `ONP_LOG_LEVEL` (default `INFO`).
- **stderr sink** preserved (`keep_stderr=True`) so docker/systemd users still see logs.
- Optional parallel **JSON sink** (`.jsonl`, `serialize=True`) via `ONP_LOG_JSON=1` for
  aggregators.
- Log dir overridable via `ONP_LOG_DIR`.
- The colored console format uses `<level>` tags; the file sink strips ANSI automatically
  (non-TTY).

Cross-cutting middleware: `RequestIDMiddleware` binds a UUID4 per request into loguru
context and emits `X-Request-ID`, so one request is greppable across log files.
`loguru.logger.opt(lazy=True)` is used in hot paths (e.g. embedding size metrics) so the
expensive metric computation only runs when the level is enabled.

---

## 6. SSE disconnect handling — `is_disconnected` + reader cancel

Both streaming endpoints (`/chat/stream`, `/search/ask`) poll `is_disconnected()` and
cancel the in-flight LLM task so a closed browser tab doesn't pin a local model.

### 6.1 Ask stream (`api/routers/search.py`)

```python
while True:
    next_task = asyncio.ensure_future(event_iter.__anext__())
    while not next_task.done():
        if fastapi_request is not None and await fastapi_request.is_disconnected():
            logger.info("ask stream: client disconnected mid-stream; cancelling in-flight graph + LLM call")
            next_task.cancel()
            try: await next_task
            except (asyncio.CancelledError, Exception): pass
            try: await event_iter.aclose()         # best-effort close underlying iterator
            except Exception: pass
            return
        await asyncio.sleep(0.2)                     # 200ms poll — cheap vs token latency
    event = next_task.result()
```

`/chat/stream` uses the same `await fastapi_request.is_disconnected()` gate
(`api/routers/chat.py`). Streaming endpoints are explicitly excluded from GZip
(`SelectiveGZipMiddleware`, `_NO_GZIP_PREFIXES`) because per-chunk gzip buffering would
hold back token deltas and delay disconnect detection.

---

## 7. DB-repair flag + auto-heal (`desktop/db_repair.py`)

Self-healing for SurrealDB live-query corruption (a class of failure that bricks source
processing until the DB is repaired). Two-phase, flag-driven:

```python
def looks_like_lq_corruption(log_text: str) -> bool: ...      # scans worker.log for LQ-corruption markers
def flag_path(data_home): return Path(data_home) / ".needs_db_repair"
def needs_repair(data_home): return flag_path(data_home).exists()
def set_needs_repair(data_home): ...       # best-effort touch; a missed flag → manual repair, never a crash
def clear_needs_repair(data_home): ...     # cleared after exactly ONE attempt
```

- **Detection**: a log watcher scans `worker.log`; on a corruption match it sets the
  one-shot flag file. It does *not* repair inline.
- **Heal**: on next launch, once SurrealDB is up, the launcher calls `auto_repair(...)`
  which mirrors `scripts/repair_desktop_db.sh`: **export → physical copy backup → move
  aside → re-import**. Backup-first and abort-safe: if the export step fails or comes out
  empty, *no changes are made* (`"export step failed — no changes made"` /
  `"export came out empty — aborting"`).
- The flag is cleared after exactly one attempt, so a repair that doesn't fix it won't
  loop.

---

## 8. surreal-commands retry policy

Retry is a **blocklist** (`stop_on`) — retry everything *except* the listed permanent
error types. This is more resilient than an allowlist (new exception types auto-retry).

| Command | max_attempts | wait | stop_on |
|---|---|---|---|
| `process_source_command` | 15 | exp-jitter 1–120s | `[ValueError, ConfigurationError]` |
| `embed_source_command` | 5 | exp-jitter 1–60s | `[ValueError]` |
| `embed_note_command` / `embed_insight_command` | 5 | exp-jitter 1–60s | `[ValueError]` |
| `create_insight_command` | 5 | exp-jitter 1–60s | `[ValueError]` |
| `run_transformation_command` | 5 | exp-jitter 1–60s | `[ValueError]` |
| `rebuild_embeddings_command` | none | — | coordinator only |
| `generate_podcast_command` | 1 | — | prevents duplicate episode rows |

```python
@command("process_source", app="open_notebook", retry={
    "max_attempts": 15, "wait_strategy": "exponential_jitter",
    "wait_min": 1, "wait_max": 120,
    "stop_on": [ValueError, ConfigurationError],
    "retry_log_level": "debug",
})
async def process_source_command(input_data): ...
```

`process_source_command` deliberately **re-raises** `ValueError` (permanent) so the job
is marked `failed` and the source becomes retryable from the UI — rather than completing
with a "success=False" payload. `max_attempts: 15` handles SurrealDB v2 transaction
conflicts under deep queues; `retry_log_level: "debug"` suppresses noise from those
conflict retries.

### 8.1 Stale-command reapers (`api/main.py`)

Because a crashed worker leaves command rows in `new`/`queued`/`running` forever (and the
frontend polls them every 2s), the lifespan does:

- A **startup pass** marking any row in a non-terminal state older than 30m as `failed`.
- A **periodic reaper loop** (every 5 minutes) running the same UPDATE, cancelled cleanly
  at shutdown. The loop never crashes on a bad tick (log + retry next iteration).

Both are anchored via `_track_task` (module-level strong-ref set) so the asyncio event
loop's weak-ref tracking can't GC them mid-run.

---

## Key files

| Concern | Path |
|---|---|
| Exception hierarchy | `open_notebook/exceptions.py` |
| Error classifier + sidecar classifier | `open_notebook/utils/error_classifier.py` |
| Global HTTP handlers + reapers | `api/main.py` |
| HTTPException reraise meta-test | `tests/test_v0_7_135_meta.py` |
| Loguru config | `open_notebook/logging.py` |
| SSE disconnect (ask) | `api/routers/search.py` |
| SSE disconnect (chat) | `api/routers/chat.py` |
| DB auto-repair | `desktop/db_repair.py` |
| Retry configs | `commands/source_commands.py`, `commands/embedding_commands.py`, `commands/podcast_commands.py` |
