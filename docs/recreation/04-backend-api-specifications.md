# 04 — Backend API Specifications

> FastAPI. **279 route handlers across 47 router modules** (49 `include_router` registrations). All bound to `127.0.0.1` on a dynamic port.
> Base path convention: `/api/*`. The Next.js server rewrites `/api/*` to this backend.

---

## 1. Application assembly

`api/main.py` builds the app, registers routers, installs global exception handlers, and
runs the lifespan (migrations, stale-command reaping, provider registration).

Router inventory (`api/routers/`):

```
auth  capture  chat  commands  config  context  credentials  deeper_notebook
embedding  embedding_rebuild  episode_profiles  evaluations  exports  filesystem
gmail  insights  knowledge_engine  knowledge_navigation  knowledge_workspace
languages  launcher_prefs  local_models  mcp  models  notebooks  notes  onp
overlay  podcasts  research  runtime  search  settings  source_chat
source_visuals  sources  speaker_profiles  study  study_anki  study_assistants
study_exams  study_plans  study_voice  system  transformations  updates  vault
video_overviews
```

## 2. Authentication

Optional, single shared password — appropriate for a local-first desktop app where the
threat model is "another process on this machine", not multi-tenancy.

```python
# api/auth.py
def check_api_password(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> bool:
    """Supports Docker secrets via DEEPER_NOTEBOOK_PASSWORD_FILE.
    Returns True without checking if DEEPER_NOTEBOOK_PASSWORD is not configured."""
    password = resolve_env("DEEPER_NOTEBOOK_PASSWORD", getter=get_secret_from_env)
    if not password:
        return True  # unconfigured → open (desktop default)
    ...  # else compare; 401 on mismatch/absence
```

Used as `_authenticated: bool = Depends(check_api_password)`.

## 3. Representative endpoints

### `GET /api/notebooks`
Query: `archived: bool | None`, `order_by: str = "updated desc"`.
`order_by` is validated against `{name, created, updated}` × `{asc, desc}`; anything else
is a 400. Returns `NotebookResponse[]` with graph-derived `source_count` / `note_count`.

### `GET /api/sources`
Query: `notebook_id`, `source_type`, `sort_by ∈ {created, updated}`,
`sort_order ∈ {asc, desc}`, `limit`, `offset`. When source visuals are enabled, each row
is enriched with `visual` + `visual_status`; when disabled, a **capability sentinel** is
stamped (doc 07).

### `POST /api/notebooks/{notebook_id}/discover-sources`
Guarded web search. Search-only — returns candidates, never ingests.

```json
{ "enabled": true, "provider": "wikipedia",
  "results": [{"title": "...", "url": "...", "snippet": "..."}] }
```

`enabled` is false only when the operator restored key-only gating
(`DEEPER_NOTEBOOK_WEB_SEARCH_KEYLESS=0`) with no key set. Provider/transport errors
degrade to `results: []` — never a 500.

### `GET /api/mcp/web-search`
Availability of the built-in chat tools, for the MCP tool picker:

```json
{ "enabled": true, "provider": "wikipedia", "tool_name": "web_search",
  "scholarly_enabled": true, "scholarly_tool_name": "scholarly_search" }
```

Predicates are read **live per request**, so env/flag changes surface immediately.

### `GET /api/local-models/health`
Concurrent probes (max 4 in flight) of every registered local sidecar.

```json
{ "overall": "healthy",
  "models": [{ "name": "MLX (local)", "status": "healthy",
               "detail": "no models listed", "latency_ms": null,
               "runtime": "MLX", "endpoint": "http://127.0.0.1:58144/v1",
               "probe_path": "/models", "credential_id": "credential:..." }] }
```

`status ∈ {healthy, unhealthy, not_configured, unknown}`.

### `GET /api/runtime/snapshot`
Bounded runtime projection — readiness, startup stages, updates, vault, knowledge,
backup. Never performs actions. `StartupSnapshot.stages[]` carries
`{stage, elapsed_ms}` used by the UI to show launch timings.

### `GET /api/config`
Returns version and update status. **Compares against this fork**
(`Antman1526/Deeper-Notebook`) — comparing against upstream produced a permanent false
"update available" banner because upstream's `pyproject` version (1.14.x) always
outran the fork's (1.8.5).

### Source visuals (`/api/sources/{id}/visual*`)
- `GET  …/visual` → bounded WebP bytes, `private, immutable` ETag
- `POST …/visual:refresh` → queue extraction (idempotent by `request_id`)
- `DELETE …/visual` → remove cached visual

All three are guarded:

```python
def _guard() -> None:
    if not source_visuals_enabled():
        raise HTTPException(status_code=404, detail=_FEATURE_UNAVAILABLE)
```

404 (not 403) so a disabled feature is indistinguishable from a nonexistent route.

### ExamLab (`/api/study/exams/*`, `api/routers/study_exams.py`)
- `POST …/attempts` → `201`, body `{artifact_id, notebook_id, title, duration_sec}`.
  Requires the artifact to be `artifact_type == "quiz"` with a structured document (409
  otherwise — "regenerate it in Evidence Studio first" for pre-structured-document quizzes).
  Snapshots the questions into `study_exam_attempt` at creation.
- `GET …/attempts` → `ExamAttemptSummaryResponse[]` (list view, no question payload).
- `GET …/attempts/{id}` → `ExamAttemptResponse`. **Taking view vs results view is the
  security-relevant contract**: while `submitted_at IS NONE`, the response carries
  `questions` (prompt + options, no `correct_option_id`) and `results: None`. After submit,
  it carries `results` (graded, with the answer key) and `questions: None`. The answer key
  is structurally absent from the taking-view Pydantic model — not filtered at
  serialization time, so there is no code path that can leak it early.
- `POST …/attempts/{id}/submit` → body `{"answers": {"<index>": "<option_id>"}}`. Grades
  deterministically against the snapshot; unanswered and unknown option ids both grade as
  wrong, never as an error. A second submit on an already-submitted attempt is `409`
  (`StudyExamConflict`).
- `POST …/attempts/{id}/seed-misses` → creates FSRS cards only for missed questions not
  already in `seeded_indices`; idempotent — calling twice creates zero cards the second
  time. Response: `{"created": int, "already_seeded": int, "seeded_indices": [int]}`.

## 4. Error handling contract

| Exception | HTTP |
|---|---|
| `NotFoundError` | 404 |
| `InvalidInputError` | 400 |
| `HTTPException` | as raised |
| everything else | 500, detail redacted |

Routers must re-raise typed exceptions before the broad `except Exception`, or 404/400
cases get masked as 500s:

```python
except HTTPException:
    raise
except (NotFoundError, InvalidInputError):
    raise                       # v0.7.179 — let global handlers classify
except Exception as e:
    logger.error(f"Error fetching notebooks: {str(e)}")
    raise HTTPException(status_code=500, detail="Error fetching notebooks")
```

## 5. Background jobs

`surreal-commands` runs a worker process. Jobs are rows in `command`:

```
GET  /api/commands            list (status filter, bounded limit)
POST /api/commands/{id}/cancel
```

Cancellation prefers the library's private service and falls back to a direct
`UPDATE` — the private import is guarded so an upstream rename doesn't silently break
all cancellation:

```python
try:
    from surreal_commands.core.service import get_command_service
except ImportError:
    from deeper_notebook.database.repository import repo_query

    ...  # direct UPDATE fallback on the command table
```

A lifespan reaper marks stale in-flight commands as failed at startup.

## 6. Streaming

Chat streams over SSE. The client must attach an `AbortController` and call
`reader.cancel()` on unmount — orphaned readers leaked generations. The server treats
client disconnect as cancellation.

## 7. Timeouts and budgets

| Setting | Default | Applies to |
|---|---|---|
| `MCP_TOOL_TIMEOUT_SEC` | 30 | one tool call |
| `WEB_SEARCH_TIMEOUT_SEC` | 10 | one search HTTP request |
| `WEB_SEARCH_TOTAL_BUDGET_SEC` | 25 | whole failover chain (< tool timeout) |
| `CHAT_TIMEOUT_SEC` | 30 | chat model call |
| `SEARCH_TIMEOUT_SEC` | — | DB text search |
| `AGENT_MAX_ITERATIONS` | 4 | tool-loop re-invocations |

Nested budgets are deliberate: each inner budget sits strictly below its outer one, so a
slow dependency degrades instead of being hard-killed mid-flight.

## 8. Adding a route — checklist

1. Router module in `api/routers/`, registered in `api/main.py`
2. Pydantic request/response schemas (strict; no bare `dict`)
3. `Depends(check_api_password)` if it exposes data
4. Typed exceptions, re-raised before the broad catch
5. Values bound via `vars=`; identifiers whitelisted
6. Tests in `tests/`, including one failure path
7. Frontend types in `frontend/src/lib/types/api.ts`

---

*Continues in [05 — Frontend Architecture & Components](./05-frontend-architecture-components.md).*
