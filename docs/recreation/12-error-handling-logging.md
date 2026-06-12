# 12 — Error Handling & Logging

Recreation reference for how Open Notebook Plus classifies, surfaces, and logs
errors across the FastAPI backend, the surreal-commands worker, the SSE
streaming paths, and the desktop launcher.

All paths repo-relative to `/Users/Antman/Desktop/OpenNotebook/open-notebook-Plus`.

> **Secrets note:** error messages are deliberately truncated/redacted to avoid
> leaking provider internals or credentials; all credential/key values shown
> below are placeholders (`<...>`).

---

## 1. The exception hierarchy (`open_notebook/exceptions.py`)

A flat hierarchy rooted at `OpenNotebookError`. Every typed subclass exists so a
single FastAPI handler can map it to the right HTTP status:

```python
# open_notebook/exceptions.py
class OpenNotebookError(Exception):
    """Base exception class for Open Notebook errors."""

class DatabaseOperationError(OpenNotebookError): ...   # DB op failed
class UnsupportedTypeException(OpenNotebookError): ...  # unsupported type
class InvalidInputError(OpenNotebookError): ...         # bad input → 400
class NotFoundError(OpenNotebookError): ...             # missing resource → 404
class AuthenticationError(OpenNotebookError): ...       # auth problem → 401
class ConfigurationError(OpenNotebookError): ...        # config problem → 422
class ExternalServiceError(OpenNotebookError): ...      # provider/model failed → 502
class RateLimitError(OpenNotebookError): ...            # rate limit → 429
class FileOperationError(OpenNotebookError): ...        # file op failed
class NetworkError(OpenNotebookError): ...              # network failed → 502
class NoTranscriptFound(OpenNotebookError): ...         # no transcript for video
```

Convention: raise the **most specific** typed exception. Anything that escapes
as the base `OpenNotebookError` becomes a generic 500.

---

## 2. `classify_error` (`open_notebook/utils/error_classifier.py`)

Raw exceptions from LLM providers / Esperanto / LangChain are unpredictable
(different classes, vendor-specific strings). `classify_error()` normalizes them
into `(ExceptionClass, user_message)` via ordered keyword matching against a
combined `"{type_name}: {str}"` (both lowercased):

```python
def classify_error(exception: BaseException) -> tuple[type[OpenNotebookError], str]:
    error_str = str(exception).lower()
    error_type_name = type(exception).__name__.lower()
    combined = f"{error_type_name}: {error_str}"
    for keywords, exc_class, message in _CLASSIFICATION_RULES:
        for keyword in keywords:
            if keyword in combined:
                user_message = message if message is not None else _truncate(str(exception))
                return exc_class, user_message
    logger.warning(f"Unclassified LLM error ({type(exception).__name__}): {exception}")
    return ExternalServiceError, f"AI service error: {_truncate(str(exception))}"
```

The rule table (`_CLASSIFICATION_RULES`) — order matters, first match wins:

| Keywords (sample) | Class | Message behavior |
|---|---|---|
| `authentication`, `401`, `invalid_api_key` | `AuthenticationError` | "Authentication failed. Check your API key…" |
| `rate limit`, `429`, `quota exceeded` | `RateLimitError` | "Rate limit exceeded. Wait and try again." |
| `model not found`, `does not exist` | `ConfigurationError` | pass-through original |
| `no model configured`, `please go to settings` | `ConfigurationError` | pass-through |
| `model is loading`, `not ready`, `warming up` | `ExternalServiceError` | "The local model is still loading…" |
| `connection refused`, `timed out`, `connecterror` | `NetworkError` | "Could not reach the AI model server (local llama.cpp/Ollama)…" |
| `context length`, `max_tokens` | `ExternalServiceError` | "Content too large for the selected model…" |
| `413`, `payload too large` | `ExternalServiceError` | "Request payload too large…" |
| `500/502/503`, `overloaded` | `ExternalServiceError` | "AI provider temporarily unavailable…" |
| *(no match)* | `ExternalServiceError` | "AI service error: …" + logged warning |

Two design points:

- **`_truncate(text, 200)`** caps pass-through messages so verbose provider
  tracebacks don't leak into the UI.
- The local-LLM rules (`model is loading`, `connection refused`) were added so a
  cold-starting bundled `llama-cpp-python` server (HTTP 503 during a 10–30s 14B
  Q4 load) reads as a clear, transient, user-actionable state instead of a
  generic "AI service error".

### 2.1 Sidecar stderr classification (`classify_sidecar_error`)

A companion that maps the **last ~50 lines of a sidecar's stderr** (captured by
the launcher's `_start_tail_drainer`) to a one-line hint, rendered by the API's
`GET /healthz/sidecars/{kind}/log` popover:

```python
_SIDECAR_PATTERNS = [
    ("failed to load model", "Model file could not be loaded — check the GGUF path…"),
    ("out of memory",        "Out of memory — try a smaller/more-quantized model, or lower n_ctx."),
    ("metal error",          "Apple GPU (Metal) error — restart the app or try a smaller model."),
    ("address already in use","Port already in use — another process is holding it…"),
    ("modulenotfounderror",  "Sidecar Python dependency missing — reinstall the desktop bundle."),
    ("segmentation fault",   "Sidecar crashed (segfault) — possible model-file corruption."),
    ("killed: 9",            "Sidecar was killed (likely by the OS for OOM)."),
    # …narrower patterns first; catch-all returns None → UI shows raw tail only
]

def classify_sidecar_error(tail_text: str) -> str | None:
    if not tail_text: return None
    haystack = tail_text.lower()
    for needle, hint in _SIDECAR_PATTERNS:
        if needle in haystack:
            return hint
    return None
```

---

## 3. FastAPI global handlers (`api/main.py`)

One handler per typed exception converts it to a JSON response with the right
status code, and — importantly — **re-attaches CORS headers** so error responses
aren't blocked by the browser (errors can occur before CORS middleware runs):

```python
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": exc.detail},
                        headers={**(exc.headers or {}), **_cors_headers(request)})

@app.exception_handler(NotFoundError)        # → 404
@app.exception_handler(InvalidInputError)    # → 400
@app.exception_handler(AuthenticationError)  # → 401
@app.exception_handler(RateLimitError)       # → 429
@app.exception_handler(ConfigurationError)   # → 422
@app.exception_handler(NetworkError)         # → 502
@app.exception_handler(ExternalServiceError) # → 502
@app.exception_handler(OpenNotebookError)    # → 500  (base catch-all)
```

Each handler is uniform:

```python
@app.exception_handler(RateLimitError)
async def rate_limit_error_handler(request: Request, exc: RateLimitError):
    return JSONResponse(status_code=429, content={"detail": str(exc)},
                        headers=_cors_headers(request))
```

**End-to-end flow:** raw provider error → `classify_error()` (in a graph node or
SSE handler) → `raise ExcClass(user_message)` → matching `@app.exception_handler`
→ `{"detail": "<user_message>"}` at the mapped status. The frontend's
`getApiErrorMessage()` (`frontend/src/lib/utils/error-handler.ts`) tries i18n
mapping first, then falls back to displaying `detail` verbatim — which is why the
classifier's messages are written to be user-facing.

The base-class handler ordering is load-bearing: because `OpenNotebookError` is
registered, more specific subclasses must each have their own handler to avoid
collapsing to 500 (they do).

---

## 4. Loguru config (`open_notebook/logging.py`)

Every long-lived process calls `configure_logging("<component>")` at startup.
The API does this first thing in its lifespan (`api/main.py:212`) so even
migration/encryption errors land in a tailable file.

Defaults:

```python
_DEFAULT_ROTATION    = "20 MB"
_DEFAULT_RETENTION   = "14 days"
_DEFAULT_LEVEL       = "INFO"      # override via ONP_LOG_LEVEL
_DEFAULT_COMPRESSION = "gz"
```

Log directory resolution (`default_log_dir()`): `ONP_LOG_DIR` →
`~/.open-notebook-plus/logs/` → (container fallback)
`/var/log/open-notebook-plus`.

Format carries a **request-id column** for correlation:

```python
_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<yellow>req={extra[request_id]:<8}</yellow> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)
```

`configure_logging` is **idempotent** (calls `logger.remove()` first — safe
across uvicorn reloads), sets a process-wide default `extra={"request_id": "-"}`
so non-request code never `KeyError`s on the format, and adds up to three sinks:

```python
logger.remove()
logger.configure(extra={"request_id": "-"})
if keep_stderr:                                  # live output for docker/systemd
    logger.add(sys.stderr, level=level, format=_LOG_FORMAT,
               backtrace=False, diagnose=False)  # diagnose=False → no local-var leakage
logger.add(log_dir/f"{component}.log", level=level, format=_LOG_FORMAT,
           rotation="20 MB", retention="14 days", compression="gz",
           enqueue=True,                          # non-blocking, multiprocess-safe
           backtrace=False, diagnose=False, encoding="utf-8")
if json_sink:                                     # ONP_LOG_JSON=1 → structured .jsonl
    logger.add(log_dir/f"{component}.jsonl", serialize=True, ...)
```

The `RequestIDMiddleware` (`api/middleware/request_id.py`) wraps each HTTP
request in `logger.contextualize(request_id=...)` so every log line emitted
during the request carries that id; startup/worker/scheduled-task lines show the
default `-`.

Components in practice: `api`, `launcher`, `worker` — each writing its own
rotated file under `~/.open-notebook-plus/logs/`.

---

## 5. surreal-commands retry semantics (`commands/*.py`)

Commands declare retry policy on the `@command` decorator. The contract is a
**blocklist** (`stop_on`) rather than an allowlist — new exception types
auto-retry, which is the more resilient default:

```python
# commands/embedding_commands.py / source_commands.py
@command("embed_note", app="open_notebook", retry={
    "max_attempts": 5,
    "wait_strategy": "exponential_jitter",
    "stop_on": [ValueError, ConfigurationError],  # validation/config = permanent
})
```

Rules of the convention:

- **`ValueError` and `ConfigurationError` are permanent** — pathological inputs
  (empty/whitespace content) and misconfiguration should never be retried.
- **Everything else retries** with exponential jitter (transaction conflicts on
  SurrealDB v2 are the common transient; `process_source` raises `max_attempts`
  to 15 to absorb deep queues).
- **Podcast commands pin `max_attempts: 1`** to prevent duplicate episode
  records:

```python
# commands/podcast_commands.py
@command("generate_podcast", app="open_notebook", retry={"max_attempts": 1})
@command("resume_podcast",   app="open_notebook", retry={"max_attempts": 1})
@command("optimize_prompt",  app="open_notebook", retry={"max_attempts": 1})
```

A generation timeout is deliberately re-raised as `asyncio.TimeoutError`, **not**
`ValueError`, so it isn't treated as permanent even though retries are disabled
(`commands/podcast_commands.py:410`), and the empty-output-dir cleanup still
fires. A cancel raises `CancelledByUser` → `RuntimeError` after stamping
`generation_stage = STAGE_CANCELLED`.

> Async-submission gotcha (enforced in CLAUDE.md + audit tests): the **sync**
> `surreal_commands.submit_command` must be wrapped in `asyncio.to_thread` when
> called from `async def`, or it blocks the event loop.

---

## 6. SSE disconnect handling

Both streaming endpoints stop work the moment the client gives up, so a local
LLM doesn't churn out tokens nobody reads.

### 6.1 Notebook chat (`api/routers/chat.py`)

```python
async for event in _chat_graph_async.astream_events(input=state_values, config=..., version="v2"):
    if await fastapi_request.is_disconnected():
        logger.info("chat stream: client disconnected for session {}; halting", full_session_id)
        # v0.8.66 — if the turn already COMPLETED (final_result captured) but the
        # client dropped during the done phase, still fire the fire-and-forget
        # memory extraction so a checkpoint-committed turn isn't left unextracted.
        if final_result and "messages" in final_result:
            _ai_text = next((_extract_text(m) for m in reversed(final_result["messages"])
                             if getattr(m, "type", None) == "ai"), "")
            if _ai_text:
                await _fire_memory_extract_turn(chat_session_id=full_session_id, ...)
        return
```

The endpoint returns a `StreamingResponse(_stream_chat_events(...))`. When the
client disconnects, FastAPI closes the generator (GeneratorExit), which reaches
the `finally` that releases the per-session lock.

### 6.2 Source chat (`api/routers/source_chat.py`)

Mirror of the chat path, plus **per-session serialization** so concurrent calls
to the same `session_id` don't each read the same checkpoint and silently lose
turns:

```python
from api.utils.session_locks import get_session_lock
session_lock = await get_session_lock(session_id)
await session_lock.acquire()
try:
    ...
    async for event in _source_chat_graph_async.astream_events(...):
        if fastapi_request is not None and await fastapi_request.is_disconnected():
            logger.info("source chat stream: client disconnected for session {}; halting", session_id)
            return
        ...
finally:
    session_lock.release()   # reached via GeneratorExit on client disconnect
```

Both use the **async** graph twin (`get_async_graph()` /
`get_async_source_chat_graph()`) because newer LangGraph raises
`NotImplementedError` if `astream_events`' internal `aget_tuple()` hits the sync
`SqliteSaver`; state is shared via the underlying SQLite checkpoint file.

> Reader-cancel gotcha (CLAUDE.md): SSE readers must be `cancel()`'d before
> release; the `is_disconnected()` + `return` pattern above lets FastAPI's
> generator-close machinery do that cleanly.

---

## 7. Health endpoints as error surfaces (`api/main.py`)

- `GET /livez` — process is up (cheap liveness).
- `GET /readyz` — returns 200 only when migrations are done and the DB pool is
  reachable; otherwise **503**:

```python
status_code = 200 if ready else 503
return JSONResponse(content=body, status_code=status_code)
```

- `GET /healthz/deep` (and `/api/healthz/deep`) — aggregates DB + sidecar health;
  returns 503 when a critical dependency is down, 200 otherwise.
- `GET /healthz/sidecars/{kind}/log` — serves the per-sidecar `.tail` plus the
  `classify_sidecar_error()` hint.

The launcher's `_wait_http("…/readyz", proc=…)` gates the supervisor on `/readyz`
and early-exits if the uvicorn child dies, so a crashed API surfaces fast instead
of timing out.

---

## 8. Desktop progress bus + per-child logs

### 8.1 ProgressBus (`desktop/progress.py`)

A thread-safe pub-sub channel for the startup phase. The launcher's main thread
publishes; the wizard server's SSE handler subscribes from its request thread.
Events are written to `~/.open-notebook-plus/logs/progress.jsonl` (rotated at
2 MB) **and** fanned out to in-process subscribers:

```python
class ProgressEvent(TypedDict):
    ts: str; step: str; status: str   # "running" | "done" | "error"
    message: str

def publish(self, step, status, message=""):
    evt = {"ts": datetime.now(timezone.utc).isoformat(),
           "step": step, "status": status, "message": message}
    with self._lock:
        self._history.append(evt)
        with self.log_path.open("a") as f:
            f.write(json.dumps(evt) + "\n")
        for q in self._subscribers:
            try: q.put_nowait(evt)
            except queue.Full: pass
```

`subscribe(timeout, replay=False)` yields history-then-live events and terminates
on the `("ready", "done")` event or idle timeout. The supervisor emits
`supervisor.<kind>` running/done/error events (`surreal`, `api`, `worker`,
`next`, `llamacpp_chat`, …) so the splash/wizard renders live boot state, and a
crash leaves an `error` event on disk for post-mortem.

### 8.2 Per-child logs (`desktop/launcher.py`)

Every spawned child gets its stderr drained (PIPE without a reader deadlocks
long-running children once the OS pipe buffer fills):

- **debug mode** — `_start_drainers` writes full `{name}.log` (`[out]`/`[err]`
  prefixed).
- **normal mode** — `_start_tail_drainer` keeps a `deque(maxlen=50)` and
  atomically rewrites `{name}.tail` on each line (write-to-sibling-then-rename so
  readers never see a half-written file).

Both run a **secret scrubber** over output so a child echoing its CLI flags
(e.g. SurrealDB printing `--pass=...`) never lands plaintext on disk:

```python
secret_pat = re.compile(
    rb"(?i)(--pass=|password[=:]|surreal_password[=:]|encryption_key[=:])([^\s\"']+)")
def _redact(b: bytes) -> bytes:
    return secret_pat.sub(rb"\1[REDACTED]", b)
```

### 8.3 Bootstrap subprocess log (`desktop/bootstrap.py`)

First-launch `venv` provisioning runs with no terminal attached, so every
subprocess is captured to `bootstrap-subprocess.log` (rotated at 5 MB). A
non-zero exit raises a `RuntimeError` carrying the **last 25 lines** of that log
so the failure is actionable in the frozen launcher's traceback handler instead
of vanishing into DEVNULL.

---

## 9. Recreation checklist

1. Define the flat `OpenNotebookError` hierarchy with the typed subclasses in §1.
2. Implement `classify_error()` + `_CLASSIFICATION_RULES` (ordered, first-match,
   `_truncate` pass-throughs) and `classify_sidecar_error()`.
3. Register one `@app.exception_handler` per typed class mapping to the §3 status
   codes, each re-attaching `_cors_headers(request)`.
4. Call `configure_logging("<component>")` at every process start; wire
   `ONP_LOG_DIR / ONP_LOG_LEVEL / ONP_LOG_JSON`; add the request-id middleware.
5. Put `stop_on: [ValueError, ConfigurationError]` on retryable commands;
   `max_attempts: 1` on podcast/optimizer commands; re-raise timeouts as
   `asyncio.TimeoutError`, not `ValueError`.
6. Guard every SSE loop with `await request.is_disconnected(): return`, use the
   async graph twin, and release per-session locks in `finally`.
7. Implement the `ProgressBus`, per-child tail drainers with secret redaction,
   and the bootstrap subprocess log with tail-on-failure.
