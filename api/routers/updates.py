"""v0.8.70 — In-app update notifier endpoints.

Thin HTTP layer over ``api.updates_service``. All endpoints are protected by
the same PasswordAuthMiddleware as the rest of the API.

    GET  /api/updates/check         — current update status (refreshes when due)
    POST /api/updates/skip          — remember a version the user skipped
    PUT  /api/updates/settings      — toggle automatic checking on/off
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api import updates_service

router = APIRouter()


class UpdateStatus(BaseModel):
    current: str
    latest: str | None = None
    update_available: bool = False
    skipped: bool = False
    skipped_version: str | None = None
    html_url: str | None = None
    release_url: str | None = None
    verification: Literal["verified", "unverified", "unknown"] = "unknown"
    published_at: str | None = None
    enabled: bool = True
    last_check: str | None = None


class SkipRequest(BaseModel):
    version: str


class SettingsRequest(BaseModel):
    enabled: bool


@router.get("/api/updates/check", response_model=UpdateStatus)
async def check_for_updates(force: bool = Query(False)):
    """Return the current update status.

    Pings GitHub only when checking is enabled and the cached result is stale
    (or ``force=true``). Never errors — failures resolve to "no update".
    """
    return await updates_service.check(force=force)


@router.post("/api/updates/skip", response_model=UpdateStatus)
async def skip_update(body: SkipRequest):
    """Remember a version the user chose to skip so the banner stops showing it."""
    return updates_service.skip_version(body.version)


@router.put("/api/updates/settings", response_model=UpdateStatus)
async def update_settings(body: SettingsRequest):
    """Enable or disable automatic update checking."""
    return updates_service.set_enabled(body.enabled)
