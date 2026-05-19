# Load environment variables
from dotenv import load_dotenv

load_dotenv()

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.auth import PasswordAuthMiddleware

# v0.7.120 — cross-cutting middlewares split into api/middleware/.
from api.middleware.metrics import PrometheusMetricsMiddleware
from api.middleware.request_id import RequestIDMiddleware
from api.middleware.security_headers import SecurityHeadersMiddleware
from api.routers import (
    auth,
    chat,
    config,
    context,
    credentials,
    embedding,
    embedding_rebuild,
    episode_profiles,
    exports,  # v0.7.90 — notebook/note export to host filesystem
    filesystem,  # v0.7.90 — host filesystem listing/mkdir for picker UI
    insights,
    languages,
    models,
    notebooks,
    notes,
    onp,
    podcasts,
    search,
    settings,
    source_chat,
    sources,
    speaker_profiles,
    studio,
    transformations,
)
from api.routers import commands as commands_router
from api.routers import (
    gmail as gmail_router,
)
from open_notebook.database.async_migrate import AsyncMigrationManager
from open_notebook.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ExternalServiceError,
    InvalidInputError,
    NetworkError,
    NotFoundError,
    OpenNotebookError,
    RateLimitError,
)
from open_notebook.logging import configure_logging
from open_notebook.utils.encryption import get_secret_from_env


def _parse_cors_origins(raw: str) -> list[str]:
    """Parse CORS_ORIGINS env value into a list of origins."""
    value = raw.strip()
    if value == "*":
        return ["*"]
    return [origin.strip() for origin in value.split(",") if origin.strip()]


# Parsed once at module load; CORS_ORIGINS changes require a restart.
_cors_origins_raw = os.getenv("CORS_ORIGINS")
CORS_ALLOWED_ORIGINS = _parse_cors_origins(_cors_origins_raw or "*")
CORS_IS_DEFAULT_WILDCARD = _cors_origins_raw is None


def _cors_headers(request: Request) -> dict[str, str]:
    """
    Build CORS headers for error responses.

    Mirrors Starlette CORSMiddleware behavior: reflects the request Origin
    when the origin is allowed (or when wildcard is configured, since
    browsers reject `Access-Control-Allow-Origin: *` combined with
    credentials). Omits `Access-Control-Allow-Origin` for disallowed
    origins so the browser blocks the error body from leaking cross-origin.
    """
    origin = request.headers.get("origin")
    headers: dict[str, str] = {
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }

    if origin and ("*" in CORS_ALLOWED_ORIGINS or origin in CORS_ALLOWED_ORIGINS):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"

    return headers


# Import commands to register them in the API process
try:
    logger.info("Commands imported in API process")
except Exception as e:
    logger.error(f"Failed to import commands in API process: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler for the FastAPI application.
    Runs database migrations automatically on startup.
    """
    # v0.7.14 — configure rotated file logging before anything else, so
    # startup errors (migrations, encryption checks) land in a file the
    # user can `tail`. Default sink: ~/.open-notebook-plus/logs/api.log
    # Honors ONP_LOG_DIR, ONP_LOG_LEVEL, ONP_LOG_JSON.
    log_dir = configure_logging("api")

    # Startup: Security checks
    logger.info("Starting API initialization — logs at {}", log_dir)

    # Security check: Encryption key
    # v0.7.24 — also honor the v0.7.17 plural rotation env var. A user
    # who has finished rotation and only has OPEN_NOTEBOOK_ENCRYPTION_KEYS
    # set was getting a spurious "encryption will fail" warning pointing
    # at the wrong variable.
    has_singular = bool(get_secret_from_env("OPEN_NOTEBOOK_ENCRYPTION_KEY"))
    has_plural = bool(get_secret_from_env("OPEN_NOTEBOOK_ENCRYPTION_KEYS"))
    if not (has_singular or has_plural):
        logger.warning(
            "Neither OPEN_NOTEBOOK_ENCRYPTION_KEY nor "
            "OPEN_NOTEBOOK_ENCRYPTION_KEYS is set. "
            "API key encryption will fail until one is configured. "
            "Set OPEN_NOTEBOOK_ENCRYPTION_KEY=<secret> for a single "
            "key, or OPEN_NOTEBOOK_ENCRYPTION_KEYS=<new>,<old> for "
            "rotation."
        )

    # Run database migrations

    try:
        migration_manager = AsyncMigrationManager()
        current_version = await migration_manager.get_current_version()
        logger.info(f"Current database version: {current_version}")

        if await migration_manager.needs_migration():
            logger.warning("Database migrations are pending. Running migrations...")
            await migration_manager.run_migration_up()
            new_version = await migration_manager.get_current_version()
            logger.success(
                f"Migrations completed successfully. Database is now at version {new_version}"
            )
        else:
            logger.info(
                "Database is already at the latest version. No migrations needed."
            )
    except Exception as e:
        logger.error(f"CRITICAL: Database migration failed: {str(e)}")
        logger.exception(e)
        # Fail fast - don't start the API with an outdated database schema
        raise RuntimeError(f"Failed to run database migrations: {str(e)}") from e

    # Run podcast profile data migration (legacy strings -> Model registry)
    try:
        from open_notebook.podcasts.migration import migrate_podcast_profiles

        await migrate_podcast_profiles()
    except Exception as e:
        logger.warning(f"Podcast profile migration encountered errors: {e}")
        # Non-fatal: profiles can be migrated manually via UI

    # v0.7.85 — one-shot legacy edge deduplicator. New duplicate edges are
    # already impossible to create thanks to the v0.7.60 + v0.7.73
    # idempotency fixes, but databases that ran older versions still
    # carry orphan duplicates that inflate source_count/note_count and
    # require multiple unlink clicks to actually remove a source. This
    # runs once per startup, is idempotent (clean DB → no-op), and is
    # non-fatal if it fails (we'll retry next boot).
    try:
        from open_notebook.database.dedup_edges import dedupe_legacy_edges

        await dedupe_legacy_edges()
    except Exception as e:
        logger.warning(f"Edge deduplication encountered errors (non-fatal): {e}")

    # ONP v0.6.1 — Start Gmail digest scheduler background task.
    # The scheduler wakes every 5 minutes, checks GmailIntegration state, and
    # fires daily/weekly digests when due. Non-fatal if it fails to start —
    # users can still trigger digests manually from the UI.
    digest_stop_event: asyncio.Event = asyncio.Event()
    digest_scheduler_task: asyncio.Task | None = None
    try:
        from open_notebook.digest.scheduler import run_forever as _digest_run_forever

        digest_scheduler_task = asyncio.create_task(
            _digest_run_forever(digest_stop_event),
            name="onp-digest-scheduler",
        )
        logger.info("Digest scheduler task started")
    except Exception as e:
        logger.warning(f"Failed to start digest scheduler (non-fatal): {e}")

    # v0.7.44 — warm the DB connection pool before serving traffic.
    # The pool grows lazily on first `_acquire`, so the FIRST chat turn
    # after launch pays a ~150-300ms SurrealDB WS handshake before the
    # graph even runs. ContextBuilder then fans out to dozens of repo
    # queries; with 4 cold slots, the first 4 concurrent calls each
    # pay the handshake too. Prefilling 2 slots eliminates this on the
    # critical first-impression path. Further growth stays lazy.
    #
    # v0.7.52 — bound each acquire with asyncio.wait_for(timeout=10).
    # Previously a SurrealDB that came up cold or got stuck mid-handshake
    # could block the lifespan handler indefinitely — the API would
    # appear "starting" forever with no /readyz reachability. 10 s is
    # generous: a healthy SurrealDB handshake takes ~200 ms; anything
    # past 5 s already indicates trouble. We log the timeout and move
    # on (degrades to lazy-warmup, same as the pre-0.7.44 behavior).
    try:
        from open_notebook.database.repository import (
            _acquire,
            _db_pool_size,
            _release,
        )

        warmup_n = min(2, _db_pool_size())
        warm_conns = []
        for _ in range(warmup_n):
            try:
                warm_conns.append(
                    await asyncio.wait_for(_acquire(), timeout=10.0)
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "DB pool warmup acquire timed out after 10s — "
                    "skipping remaining warmup, falling back to lazy "
                    "initialization on first request"
                )
                break
            except Exception as exc:
                # Pool warmup is best-effort — a failure here shouldn't
                # prevent boot. The user can still recover via the
                # /readyz probe + a manual retry.
                logger.warning("DB pool warmup acquire failed: {}", exc)
                break
        for c in warm_conns:
            await _release(c)
        if warm_conns:
            logger.info(
                "DB pool pre-warmed with {} idle connection(s)",
                len(warm_conns),
            )
    except Exception as exc:
        logger.warning("DB pool warmup encountered an error: {}", exc)

    # v0.7.125 — LangGraph SQLite checkpoint pruning. Without this,
    # ~/.open-notebook-plus/data/sqlite-db/checkpoints.sqlite grows
    # unbounded — every chat turn appends rows that LangGraph never
    # reads again (it only queries the latest checkpoint per thread
    # when resuming). After a year of moderate use on a single-user
    # install, the file is hundreds of MB. The prune loop keeps the
    # N most recent checkpoints per thread (default 50) and runs
    # every ONP_CHECKPOINT_PRUNE_INTERVAL_HOURS (default 24).
    # Non-fatal if it fails to start — chat still works, just grows.
    checkpoint_prune_stop_event: asyncio.Event = asyncio.Event()
    checkpoint_prune_task: asyncio.Task | None = None
    try:
        from open_notebook.utils.checkpoint_prune import (
            run_prune_loop as _checkpoint_prune_loop,
        )

        checkpoint_prune_task = asyncio.create_task(
            _checkpoint_prune_loop(checkpoint_prune_stop_event),
            name="onp-checkpoint-prune",
        )
        logger.info("LangGraph checkpoint-prune task started")
    except Exception as e:
        logger.warning(
            f"Failed to start checkpoint-prune task (non-fatal): {e}",
        )

    logger.success("API initialization completed successfully")

    # Yield control to the application
    yield

    # v0.7.125 — Stop the checkpoint-prune task FIRST (it's the most
    # likely to be mid-sleep so cancelling is quick), then the digest
    # scheduler. Both use the same wait_for(timeout=10) + cancel
    # fallback pattern as v0.6.1.
    if checkpoint_prune_task is not None:
        logger.info("Signalling checkpoint-prune task to stop...")
        checkpoint_prune_stop_event.set()
        try:
            await asyncio.wait_for(checkpoint_prune_task, timeout=10)
            logger.info("Checkpoint-prune task stopped cleanly")
        except asyncio.TimeoutError:
            logger.warning(
                "Checkpoint-prune task did not stop in 10s — cancelling"
            )
            checkpoint_prune_task.cancel()
            try:
                await checkpoint_prune_task
            except (asyncio.CancelledError, Exception):
                pass

    # Shutdown: signal the digest scheduler to stop and wait for it briefly.
    if digest_scheduler_task is not None:
        logger.info("Signalling digest scheduler to stop...")
        digest_stop_event.set()
        try:
            await asyncio.wait_for(digest_scheduler_task, timeout=10)
            logger.info("Digest scheduler stopped cleanly")
        except asyncio.TimeoutError:
            logger.warning("Digest scheduler did not stop in 10s — cancelling")
            digest_scheduler_task.cancel()
            try:
                await digest_scheduler_task
            except (asyncio.CancelledError, Exception):
                pass
        except Exception as e:
            logger.warning(f"Digest scheduler exit raised: {e}")

    # v0.7.18 — close pooled SurrealDB connections so we exit clean
    # (avoids "task pending" warnings and leaves the DB free).
    try:
        from open_notebook.database.repository import close_pool

        await close_pool()
        logger.info("SurrealDB pool closed")
    except Exception as e:
        logger.warning(f"Closing DB pool raised: {e}")

    logger.info("API shutdown complete")


app = FastAPI(
    title="Open Notebook API",
    description="API for Open Notebook - Research Assistant",
    lifespan=lifespan,
)

if CORS_IS_DEFAULT_WILDCARD:
    logger.warning(
        "CORS_ORIGINS is not set — API accepts cross-origin requests from any "
        "origin (default: '*'). For production deployments, set CORS_ORIGINS to "
        "your frontend origin(s), e.g. "
        "CORS_ORIGINS=https://notebook.example.com"
    )
else:
    logger.info(f"CORS allowed origins: {CORS_ALLOWED_ORIGINS}")

# v0.7.121 — Escalate from WARNING to ERROR-level log when the user has
# the DANGEROUS combination: CORS=* AND no password set. In that state
# *any* origin on the internet can hit the API with credential-less
# requests and read every notebook/source/note. The password
# middleware short-circuits at startup if `OPEN_NOTEBOOK_PASSWORD` is
# unset (auth becomes a no-op), so CORS=* + no-password = open API
# wide open to the world. This is a foot-gun the README warns about
# but it's worth surfacing at process boot too — operators tail logs.
_password_is_set = bool(get_secret_from_env("OPEN_NOTEBOOK_PASSWORD"))
if CORS_IS_DEFAULT_WILDCARD and not _password_is_set:
    logger.error(
        "⚠️ DANGEROUS CONFIG: CORS_ORIGINS='*' AND OPEN_NOTEBOOK_PASSWORD is "
        "unset. Any origin can call this API without credentials. ANYONE "
        "with the API URL can read/write every notebook. This is fine ONLY "
        "for local development. For ANY exposed deployment (Docker, "
        "Kubernetes, public IP), set BOTH: "
        "CORS_ORIGINS=https://your-frontend.example.com AND "
        "OPEN_NOTEBOOK_PASSWORD=<strong-password>."
    )

# Middleware order matters — Starlette wraps in REVERSE order of registration.
# The OUTERMOST middleware (first to see request, last to see response) is
# the one added LAST. So the call chain on a request looks like:
#
#   request → CORS → RequestID → SecurityHeaders → GZip → PasswordAuth → handler
#                                                                              ↓
#   response ← CORS ← RequestID ← SecurityHeaders ← GZip ← PasswordAuth ← handler
#
# Rationale:
#  - PasswordAuth FIRST registered → innermost → only authenticated requests
#    flow through the rest. Saves CPU on unauthed traffic.
#  - GZip wraps PasswordAuth so 401 / 403 bodies also compress.
#  - SecurityHeaders wraps GZip so headers land on every response including
#    GZip's pre-encoded ones.
#  - RequestID wraps SecurityHeaders so every log line + the
#    `X-Request-ID` response header carries the same id even when an
#    auth failure short-circuits early.
#  - CORS is registered LAST → outermost → processes preflight OPTIONS
#    requests before they hit PasswordAuth (which would 401 them).

app.add_middleware(
    PasswordAuthMiddleware,
    excluded_paths=[
        "/",
        "/health",
        "/livez",
        "/readyz",
        "/healthz/deep",   # v0.7.112 — operators need to poll without auth
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/auth/status",
        "/api/config",
        "/metrics",   # v0.7.124 — Prometheus scrapes without auth
    ],
)

# v0.7.120 — gzip compression. Bodies ≥ 1000 bytes get compressed when
# the client sends `Accept-Encoding: gzip` (every modern browser + httpx
# does). Smaller bodies skip compression — the overhead exceeds the
# savings for short payloads.
app.add_middleware(GZipMiddleware, minimum_size=1000)

# v0.7.120 — defense-in-depth security headers. X-Content-Type-Options,
# X-Frame-Options, Referrer-Policy, CSP (skipped on /docs paths).
app.add_middleware(SecurityHeadersMiddleware)

# v0.7.124 — Prometheus request-timing capture. Records every request's
# method + route + status_code + duration into the metrics module's
# counter + histogram, exposed at /metrics. /metrics itself is
# excluded from capture so scrapes don't show up as user traffic.
app.add_middleware(PrometheusMetricsMiddleware)

# v0.7.120 — request-ID correlation. Generates (or accepts) a UUID4
# per request, binds it into loguru context, surfaces as
# X-Request-ID response header. Lets operators grep a single request
# across the codebase's log files.
app.add_middleware(RequestIDMiddleware)

# CORS is OUTERMOST so it sees preflight OPTIONS before any other
# middleware short-circuits them.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Custom exception handler to ensure CORS headers are included in error responses
# This helps when errors occur before the CORS middleware can process them
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    Custom exception handler that ensures CORS headers are included in error responses.
    This is particularly important for 413 (Payload Too Large) errors during file uploads.

    Note: If a reverse proxy (nginx, traefik) returns 413 before the request reaches
    FastAPI, this handler won't be called. In that case, configure your reverse proxy
    to add CORS headers to error responses.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={**(exc.headers or {}), **_cors_headers(request)},
    )


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request: Request, exc: NotFoundError):
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(InvalidInputError)
async def invalid_input_error_handler(request: Request, exc: InvalidInputError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(
        status_code=401,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(RateLimitError)
async def rate_limit_error_handler(request: Request, exc: RateLimitError):
    return JSONResponse(
        status_code=429,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(ConfigurationError)
async def configuration_error_handler(request: Request, exc: ConfigurationError):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(NetworkError)
async def network_error_handler(request: Request, exc: NetworkError):
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(ExternalServiceError)
async def external_service_error_handler(request: Request, exc: ExternalServiceError):
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(OpenNotebookError)
async def open_notebook_error_handler(request: Request, exc: OpenNotebookError):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


# Include routers
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(config.router, prefix="/api", tags=["config"])
app.include_router(notebooks.router, prefix="/api", tags=["notebooks"])
app.include_router(search.router, prefix="/api", tags=["search"])
app.include_router(models.router, prefix="/api", tags=["models"])
app.include_router(transformations.router, prefix="/api", tags=["transformations"])
app.include_router(notes.router, prefix="/api", tags=["notes"])
app.include_router(onp.router, prefix="/api", tags=["onp"])  # ONP desktop-wrapper endpoints
app.include_router(gmail_router.router, prefix="/api", tags=["onp-gmail"])  # Gmail digest integration
app.include_router(embedding.router, prefix="/api", tags=["embedding"])
app.include_router(
    embedding_rebuild.router, prefix="/api/embeddings", tags=["embeddings"]
)
app.include_router(settings.router, prefix="/api", tags=["settings"])
app.include_router(context.router, prefix="/api", tags=["context"])
app.include_router(sources.router, prefix="/api", tags=["sources"])
app.include_router(insights.router, prefix="/api", tags=["insights"])
app.include_router(commands_router.router, prefix="/api", tags=["commands"])
app.include_router(podcasts.router, prefix="/api", tags=["podcasts"])
# ONP v0.7.0 — Studio: one-shot upload + mode → notebook/podcast workflow
app.include_router(studio.router, prefix="/api", tags=["studio"])
app.include_router(episode_profiles.router, prefix="/api", tags=["episode-profiles"])
app.include_router(speaker_profiles.router, prefix="/api", tags=["speaker-profiles"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(source_chat.router, prefix="/api", tags=["source-chat"])
app.include_router(credentials.router, prefix="/api", tags=["credentials"])
app.include_router(languages.router, prefix="/api", tags=["languages"])
# v0.7.90 — Host filesystem listing/mkdir + notebook/note export endpoints.
# These let the frontend present a directory-picker UI and write notebook
# contents out to disk as markdown (folder or .zip).
app.include_router(filesystem.router, prefix="/api", tags=["filesystem"])
app.include_router(exports.router, prefix="/api", tags=["exports"])


@app.get("/")
async def root():
    return {"message": "Open Notebook API is running"}


@app.get("/health")
async def health():
    """Kept for backward compatibility — returns 200 if the process is up.

    Same shape as /livez. Existing dashboards and the launcher's wait
    loop point at /health; new code should use /livez (cheap) or
    /readyz (full dependency check)."""
    return {"status": "healthy"}


# v0.7.15 — split liveness vs readiness so the user can actually
# diagnose "is the API up but stuck?" vs "is the DB unreachable?"
# without grepping logs. /livez: process is responding. /readyz:
# DB reachable + migrations applied. The launcher's progress UI and
# any external uptime checker should poll /readyz.
@app.get("/livez")
async def livez():
    """Liveness probe — the process is alive and serving HTTP.

    Intentionally trivial. Should return < 1ms. No DB call. If this
    fails, the process is wedged and needs a restart.
    """
    return {"status": "alive"}


@app.get("/readyz")
async def readyz():
    """Readiness probe — the API can serve real traffic.

    Checks:
      - SurrealDB reachable (2s timeout, via check_database_health)
      - Migrations applied (via AsyncMigrationManager)

    Returns 200 with detail on success, 503 on any failure so external
    pollers can distinguish "starting up" from "fully ready". The
    detail body always includes the same fields so a grep-friendly
    response shape stays consistent.
    """
    # Late-binding the imports keeps tests cheap (they can monkeypatch
    # without importing the whole api.main side-effect chain).
    from api.routers.config import check_database_health
    from open_notebook.database import async_migrate

    db_health = await check_database_health()
    db_status = db_health.get("status", "unknown")

    migrations_ok = False
    migrations_error: str | None = None
    pending_migrations = False
    try:
        manager = async_migrate.AsyncMigrationManager()
        pending_migrations = await manager.needs_migration()
        migrations_ok = not pending_migrations
    except Exception as exc:
        migrations_error = str(exc)
        logger.warning("readyz: migration check failed: {}", exc)

    ready = db_status == "online" and migrations_ok
    body = {
        "status": "ready" if ready else "not_ready",
        "checks": {
            "database": db_status,
            "database_error": db_health.get("error"),
            "migrations_applied": migrations_ok,
            "migrations_pending": pending_migrations,
            "migrations_error": migrations_error,
        },
    }
    status_code = 200 if ready else 503
    return JSONResponse(content=body, status_code=status_code)


# v0.7.112 — Deep healthcheck. /readyz checks only the must-have-to-serve-
# anything dependencies (DB + migrations); /healthz/deep additionally
# probes feature-tier dependencies (embedding model, chat model
# defaults, command worker) so an operator can answer "is search broken
# right now?" without grepping logs.
#
# Each subsystem reports independently — vector search being broken
# (no embedding model) doesn't make /healthz/deep itself return 503,
# because chat-only deployments are valid. The overall status is
# "healthy" if must-haves pass and "degraded" if any optional subsystem
# is missing/broken. Returns 200 unless a must-have fails (DB or
# migrations).
# v0.7.124 — Prometheus metrics endpoint. Returns the registry in
# the standard exposition format. Auth-exempt (operators / Prometheus
# scrapers poll without credentials). Excluded from the request-
# timing histogram itself (we don't want scrapes appearing as user
# traffic).
@app.get("/metrics")
async def metrics(request: Request):
    """v0.7.124 — Prometheus metrics exposition endpoint.

    Returns the global metric registry in the standard text format
    consumed by Prometheus / Grafana / Victoria Metrics / any
    OpenMetrics-compatible scraper.

    Metrics surfaced:
      - onp_http_requests_total{method, route, status_code}
      - onp_http_request_duration_seconds{method, route}
      - onp_db_query_duration_seconds
      - onp_db_slow_queries_total
      - onp_memory_recall_fallthrough_total{reason}
      - onp_memory_recall_duration_seconds
      - onp_studio_generations_total{mode, outcome}                  (v0.7.130)
      - onp_studio_outline_parse_failures_total{reason}              (v0.7.130)
      - onp_studio_single_note_fallbacks_total                       (v0.7.130)
      - (plus the default process_* + python_gc_* metrics from
        prometheus-client)

    Auth (v0.7.131 — Area for Review #19):
      - By default the endpoint is auth-exempt (still in
        PasswordAuthMiddleware excluded_paths) so a default install
        works with Prometheus out of the box.
      - Set ONP_METRICS_AUTH_TOKEN=<random-secret> to require a
        bearer token: scrapers must send `Authorization: Bearer
        <token>`. The token is compared with `secrets.compare_digest`
        to keep timing-attacks out. The Authorization header is
        validated HERE inside the handler rather than via the
        general PasswordAuthMiddleware so the password ≠ the metrics
        scrape token (different rotation cadences, different
        operational owners).
      - Unset (the default) → no token check, behavior identical to
        v0.7.130 and earlier.

    Recommended scrape interval: 15s for high-traffic deployments,
    60s for single-user desktop installs.
    """
    import os
    import secrets

    from fastapi import HTTPException
    from fastapi.responses import Response

    from api.metrics import render_prometheus

    # v0.7.131 — optional token gate. Read at request time (not
    # startup) so operators can rotate the token via .env reload
    # without restarting the API. Cost is a single dict lookup;
    # negligible vs the actual metric rendering.
    expected_token = os.environ.get("ONP_METRICS_AUTH_TOKEN", "").strip()
    if expected_token:
        # Authorization parsing is intentionally strict — no
        # case-insensitive 'bearer ' match, no fallback to a query
        # string, no chained header. Prometheus + standard scrapers
        # all send the canonical form.
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="Missing or malformed Authorization header",
                headers={"WWW-Authenticate": 'Bearer realm="metrics"'},
            )
        provided = auth_header[len("Bearer ") :].strip()
        # Constant-time compare guards against timing-based oracle
        # attacks on the token value. compare_digest also handles
        # the length-mismatch case safely.
        if not secrets.compare_digest(provided, expected_token):
            raise HTTPException(
                status_code=401,
                detail="Invalid metrics token",
                headers={"WWW-Authenticate": 'Bearer realm="metrics"'},
            )

    body, content_type = render_prometheus()
    return Response(content=body, media_type=content_type)


@app.get("/healthz/deep")
async def healthz_deep():
    """v0.7.112 — Deep dependency check.

    Probes each subsystem independently with a short timeout and
    reports per-feature status. Useful for:
      - Operators answering "is search broken?" / "is chat broken?"
      - First-launch wizards verifying setup before showing the
        notebook UI
      - Monitoring dashboards that need to differentiate "down" from
        "missing optional config"

    Response shape:
      {
        "status": "healthy" | "degraded" | "not_ready",
        "checks": {
          "database": {...},
          "migrations": {...},
          "embedding_model": {...},
          "chat_model": {...},
          "command_registry": {...},
        }
      }

    Status codes:
      200 → healthy or degraded (some optional features unavailable)
      503 → not_ready (DB or migrations failed — nothing works)
    """
    from api.routers.config import check_database_health
    from open_notebook.database import async_migrate

    checks: dict[str, dict] = {}

    # MUST-HAVE: Database
    db_health = await check_database_health()
    db_status = db_health.get("status", "unknown")
    checks["database"] = {
        "status": db_status,
        "ok": db_status == "online",
        "error": db_health.get("error"),
    }

    # MUST-HAVE: Migrations
    try:
        manager = async_migrate.AsyncMigrationManager()
        pending = await asyncio.wait_for(manager.needs_migration(), timeout=3.0)
        checks["migrations"] = {
            "status": "applied" if not pending else "pending",
            "ok": not pending,
            "error": None,
        }
    except asyncio.TimeoutError:
        checks["migrations"] = {
            "status": "timeout", "ok": False,
            "error": "needs_migration() took longer than 3s",
        }
    except Exception as exc:
        checks["migrations"] = {
            "status": "error", "ok": False, "error": str(exc),
        }

    # OPTIONAL: Embedding model (required for vector search + chat-with-sources)
    try:
        from open_notebook.ai.models import model_manager
        emb = await asyncio.wait_for(
            model_manager.get_embedding_model(), timeout=2.0,
        )
        checks["embedding_model"] = {
            "status": "configured" if emb else "missing",
            "ok": bool(emb),
            "error": None if emb else (
                "No default embedding model. Configure one in "
                "Settings → Models to enable vector search."
            ),
        }
    except asyncio.TimeoutError:
        checks["embedding_model"] = {
            "status": "timeout", "ok": False,
            "error": "embedding model lookup took longer than 2s",
        }
    except Exception as exc:
        checks["embedding_model"] = {
            "status": "error", "ok": False, "error": str(exc),
        }

    # OPTIONAL: Default chat model (required for /chat, /studio, /ask, etc.)
    try:
        from open_notebook.ai.models import model_manager
        chat = await asyncio.wait_for(
            model_manager.get_default_model("chat"), timeout=2.0,
        )
        checks["chat_model"] = {
            "status": "configured" if chat else "missing",
            "ok": bool(chat),
            "error": None if chat else (
                "No default chat model. Configure one in "
                "Settings → Models — without it, /chat, /studio, and "
                "/search/ask cannot generate responses."
            ),
        }
    except asyncio.TimeoutError:
        checks["chat_model"] = {
            "status": "timeout", "ok": False,
            "error": "chat model lookup took longer than 2s",
        }
    except Exception as exc:
        checks["chat_model"] = {
            "status": "error", "ok": False, "error": str(exc),
        }

    # OPTIONAL: Command registry (required for async embedding +
    # podcast generation + Studio extract). Importing the command
    # modules is the same check the routers do before submitting jobs;
    # if these imports fail, async jobs can't be queued.
    try:
        import commands.embedding_commands  # noqa: F401
        import commands.podcast_commands  # noqa: F401
        import commands.source_commands  # noqa: F401
        checks["command_registry"] = {
            "status": "loaded", "ok": True, "error": None,
        }
    except Exception as exc:
        checks["command_registry"] = {
            "status": "error", "ok": False,
            "error": (
                f"Failed to import command modules: {exc}. Async jobs "
                "(podcast generation, embeddings) will fail to queue. "
                "Check that the worker process is running."
            ),
        }

    must_have_ok = (
        checks["database"]["ok"] and checks["migrations"]["ok"]
    )
    all_ok = all(c["ok"] for c in checks.values())
    if not must_have_ok:
        overall = "not_ready"
        status_code = 503
    elif not all_ok:
        overall = "degraded"
        status_code = 200
    else:
        overall = "healthy"
        status_code = 200

    return JSONResponse(
        content={"status": overall, "checks": checks},
        status_code=status_code,
    )
