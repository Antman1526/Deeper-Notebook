"""Settings router — application-level configuration.

v0.7.130 cleanup:
  - Lifted four duplicated `from typing import Literal, cast` imports
    out of the function body to module level. Re-importing inside a
    PUT handler runs on every request — small but pointless.
  - Removed the redundant `cast()` calls on each Optional[Literal[…]]
    field. Pydantic v2 already coerces the request body to the
    declared Literal types via the SettingsUpdate model; the cast
    was double-bookkeeping that masked the real type at the call site.
  - Added GET /settings/observability — a read-only view exposing the
    current observability/security env knobs so the UI can show the
    operator their actual config without re-implementing the env-var
    parsing client-side. Pairs with the Prometheus /metrics endpoint.
"""

# v0.7.130 — module-level imports replace the inline `from typing import
# Literal, cast` that used to live inside update_settings(). One import
# per process; no per-request re-resolution.
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from api.models import SettingsResponse, SettingsUpdate
from deeper_notebook.domain.content_settings import ContentSettings
from deeper_notebook.environment import resolve_env
from deeper_notebook.exceptions import InvalidInputError

router = APIRouter()


@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    """Get all application settings."""
    try:
        settings: ContentSettings = await ContentSettings.get_instance()  # type: ignore[assignment]

        return SettingsResponse(
            default_content_processing_engine_doc=settings.default_content_processing_engine_doc,
            default_content_processing_engine_url=settings.default_content_processing_engine_url,
            default_embedding_option=settings.default_embedding_option,
            auto_delete_files=settings.auto_delete_files,
            youtube_preferred_languages=settings.youtube_preferred_languages,
            offline_mode=settings.offline_mode,
            auto_summarize_on_ingest=settings.auto_summarize_on_ingest,
            auto_extract_topics_on_ingest=settings.auto_extract_topics_on_ingest,
        )
    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Error fetching settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching settings")


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(settings_update: SettingsUpdate):
    """Update application settings.

    v0.7.130 — Pydantic v2 already validates each field against its
    Optional[Literal[…]] declaration in SettingsUpdate, so we can
    assign the value directly. The previous code wrapped each
    assignment in `cast(Literal[…], settings_update.field)` plus a
    duplicate `from typing import Literal, cast` import every loop
    iteration. The cast does NOTHING at runtime (it's a static-type
    hint only); the duplicate import was per-request overhead. Both
    are gone now — same behavior, cleaner.
    """
    try:
        settings: ContentSettings = await ContentSettings.get_instance()  # type: ignore[assignment]

        if settings_update.default_content_processing_engine_doc is not None:
            settings.default_content_processing_engine_doc = (
                settings_update.default_content_processing_engine_doc
            )
        if settings_update.default_content_processing_engine_url is not None:
            settings.default_content_processing_engine_url = (
                settings_update.default_content_processing_engine_url
            )
        if settings_update.default_embedding_option is not None:
            settings.default_embedding_option = settings_update.default_embedding_option
        if settings_update.auto_delete_files is not None:
            settings.auto_delete_files = settings_update.auto_delete_files
        if settings_update.youtube_preferred_languages is not None:
            settings.youtube_preferred_languages = (
                settings_update.youtube_preferred_languages
            )
        if settings_update.offline_mode is not None:
            settings.offline_mode = settings_update.offline_mode
            # v0.8.68 — bust the network-state cache so the toggle takes
            # effect on the next chat turn, not after the 30s accessor TTL.
            from deeper_notebook.health.network import invalidate_forced_offline_cache

            invalidate_forced_offline_cache()
        # v0.8.88 — opt-in source auto-summary on ingest.
        if settings_update.auto_summarize_on_ingest is not None:
            settings.auto_summarize_on_ingest = settings_update.auto_summarize_on_ingest
        # v0.8.91 — opt-in source key-topics extraction on ingest.
        if settings_update.auto_extract_topics_on_ingest is not None:
            settings.auto_extract_topics_on_ingest = (
                settings_update.auto_extract_topics_on_ingest
            )

        await settings.update()

        return SettingsResponse(
            default_content_processing_engine_doc=settings.default_content_processing_engine_doc,
            default_content_processing_engine_url=settings.default_content_processing_engine_url,
            default_embedding_option=settings.default_embedding_option,
            auto_delete_files=settings.auto_delete_files,
            youtube_preferred_languages=settings.youtube_preferred_languages,
            offline_mode=settings.offline_mode,
            auto_summarize_on_ingest=settings.auto_summarize_on_ingest,
            auto_extract_topics_on_ingest=settings.auto_extract_topics_on_ingest,
        )
    except HTTPException:
        raise
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating settings")


# -------------------------------------------------------------------- #
# v0.7.130 — Observability read-only view
#
# Exposes the current DEEPER_NOTEBOOK_* env-derived configuration so the UI can
# show "your install is running with these flags" without parsing
# environment variables client-side. All values are read-only at the
# API level — operators flip them by editing .env + restarting, the
# same pattern the rest of the system uses.
#
# Why this isn't part of /settings: the ContentSettings model writes
# to SurrealDB and represents *user-mutable* preferences (content
# engine, YouTube langs, etc.). Observability/security env vars are
# *operator-controlled* config that doesn't belong in the same record
# (would be conceptual mixing + would surprise operators who'd then
# see DB-written values overriding their .env).
# -------------------------------------------------------------------- #


class ObservabilityResponse(BaseModel):
    """Read-only snapshot of the current observability/security config.

    Each field reflects the env var read at request time. UIs should
    refresh on demand rather than caching — operators can change env
    between requests (rare but real).
    """

    slow_query_log_ms: Optional[int] = Field(
        default=None,
        description="DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS — queries exceeding this duration "
        "are logged at WARNING and increment db_slow_queries_total. "
        "None / unset = disabled.",
    )
    encryption_kdf: str = Field(
        default="raw",
        description="DEEPER_NOTEBOOK_ENCRYPTION_KDF — 'raw' (legacy direct-Fernet) or "
        "'pbkdf2' (PBKDF2-HMAC-SHA256 600k iterations with deterministic "
        "salt). New credentials use this; old credentials decrypt under "
        "whichever KDF they were saved with via MultiFernet matrix.",
    )
    checkpoint_keep_per_thread: int = Field(
        default=50,
        description="DEEPER_NOTEBOOK_CHECKPOINT_KEEP_PER_THREAD — most-recent checkpoints "
        "to retain per LangGraph thread on the periodic prune.",
    )
    checkpoint_prune_interval_hours: int = Field(
        default=24,
        description="DEEPER_NOTEBOOK_CHECKPOINT_PRUNE_INTERVAL_HOURS — how often the "
        "background prune loop fires.",
    )
    db_pool_size: int = Field(
        default=4,
        description="DEEPER_NOTEBOOK_DB_POOL_SIZE — max concurrent SurrealDB connections.",
    )
    db_pool_disabled: bool = Field(
        default=False,
        description="DEEPER_NOTEBOOK_DB_POOL_DISABLED — bypasses pool, opens fresh "
        "connection per query (debugging only).",
    )
    metrics_endpoint_path: str = Field(
        default="/metrics",
        description="Prometheus exposition endpoint. Auth-exempt by design "
        "so scrapers without credentials can hit it; put nginx/Caddy in "
        "front with auth_basic if exposed publicly.",
    )


def _env_int(name: str, default: Optional[int] = None) -> Optional[int]:
    """v0.7.130 — Parse an int env var, returning `default` on missing
    or unparseable value. Unlike `int(os.environ.get(name, default))`
    this doesn't crash if the value is a non-numeric string (a typo
    in .env shouldn't bring down /settings/observability)."""
    raw = resolve_env(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Settings: env var {} value {!r} is not an int; reporting as {}",
            name,
            raw,
            default,
        )
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    """v0.7.130 — Conservative truthy parsing matching the rest of the
    codebase: '1', 'true', 'yes', 'on' (case-insensitive) are truthy.
    Everything else (including missing) is `default`."""
    raw = resolve_env(name, "").lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@router.get("/settings/observability", response_model=ObservabilityResponse)
async def get_observability_settings() -> ObservabilityResponse:
    """Return the current observability/security env-derived config.

    v0.7.130 — read-only. Operators change these via .env (a UI form
    that wrote to env wouldn't survive process restart, so we don't
    pretend the option exists at the API level)."""
    return ObservabilityResponse(
        slow_query_log_ms=_env_int("DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS"),
        encryption_kdf=resolve_env("DEEPER_NOTEBOOK_ENCRYPTION_KDF", "raw").lower(),
        checkpoint_keep_per_thread=_env_int(
            "DEEPER_NOTEBOOK_CHECKPOINT_KEEP_PER_THREAD", 50
        )
        or 50,
        checkpoint_prune_interval_hours=_env_int(
            "DEEPER_NOTEBOOK_CHECKPOINT_PRUNE_INTERVAL_HOURS", 24
        )
        or 24,
        db_pool_size=_env_int("DEEPER_NOTEBOOK_DB_POOL_SIZE", 4) or 4,
        db_pool_disabled=_env_bool("DEEPER_NOTEBOOK_DB_POOL_DISABLED"),
        metrics_endpoint_path="/metrics",
    )
