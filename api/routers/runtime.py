"""Authenticated, read-only runtime snapshot endpoint."""

from __future__ import annotations

import re
import time
from typing import Any

from fastapi import APIRouter, Depends, Request

from api.auth import check_api_password
from api.runtime_snapshot import (
    RuntimeSnapshot,
    RuntimeSnapshotProviders,
    build_runtime_snapshot,
)
from deeper_notebook.environment import resolve_env
from deeper_notebook.knowledge_engine.service import enabled_setting

router = APIRouter()
# v0.8.130 — captured at import as a stand-in for "when this API process
# started". Monotonic so a wall-clock change cannot fake or cancel the
# auto-export startup grace.
_PROCESS_STARTED = time.monotonic()
MAX_VAULT_SUMMARY_MOUNTS = 256
_SOURCE_FINGERPRINT_RE = re.compile(r"^[a-f0-9]{64}$")


def _bounded_mounts(mounts: Any):
    iterator = iter(mounts)
    for _ in range(MAX_VAULT_SUMMARY_MOUNTS):
        try:
            yield next(iterator)
        except StopIteration:
            return


async def _vault_summary(request: Request) -> list[dict[str, Any]] | None:
    service = getattr(request.app.state, "vault_service", None)
    repository = getattr(service, "_repository", None)
    list_mounts = getattr(repository, "list_mounts", None)
    if not callable(list_mounts):
        return None
    mounts = await list_mounts()
    summary: list[dict[str, Any]] = []
    for mount in _bounded_mounts(mounts):
        try:
            mount_status = getattr(mount, "status", None)
            write_policy = getattr(mount, "write_policy", None)
        except Exception:
            mount_status = None
            write_policy = None
        item: dict[str, Any] = {
            "status": mount_status,
            "write_policy": write_policy,
        }
        # A source fingerprint is only an internal provenance signal. The
        # snapshot normalizer projects it to availability and never returns
        # the hash itself on the wire.
        try:
            fingerprint = getattr(mount, "source_fingerprint", None)
        except Exception:
            fingerprint = None
        if isinstance(fingerprint, str) and _SOURCE_FINGERPRINT_RE.fullmatch(
            fingerprint
        ):
            item["source_fingerprint"] = fingerprint
        summary.append(item)
    return summary


async def _knowledge_summary(request: Request) -> dict[str, Any] | None:
    service = getattr(request.app.state, "knowledge_engine_service", None)
    status = getattr(service, "status", None)
    if not callable(status):
        # v0.8.130 — no service has two very different causes. The engine is
        # off by default, and "switched off" must not surface as a fault, so
        # say so explicitly. If the flag is on (the service failed to start)
        # or cannot be read, keep returning None, which stays "unknown".
        try:
            switched_off = not enabled_setting(
                "DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_SHADOW_ENABLED"
            )
        except Exception:
            return None
        return {"enabled": False} if switched_off else None
    projection = await status()
    if isinstance(projection, dict):
        return projection
    return {
        "projected": getattr(projection, "projected", None),
        "unchanged": getattr(projection, "unchanged", None),
        "failed": getattr(projection, "failed", None),
    }


def _process_uptime_seconds() -> float:
    return time.monotonic() - _PROCESS_STARTED


def _auto_export_expected() -> bool:
    """Whether a desktop launcher is scheduled to take exports for this API."""
    # v0.8.130 — exports are taken only by the desktop launcher's background
    # thread (Launcher._start_periodic_export). Without a launcher, or with
    # exports switched off, a missing or old export is not a fault. The
    # launcher always sets the control-URL key for its children (empty when
    # its control server failed, in which case exports still run), so the
    # test is presence, not truthiness.
    if resolve_env("DEEPER_NOTEBOOK_LAUNCHER_CONTROL_URL") is None:
        return False
    # The two switches below mirror the launcher's own parsing exactly; the
    # API process inherits the launcher's environment, so it sees the same
    # values.
    if resolve_env("DEEPER_NOTEBOOK_DISABLE_DB_AUTOREPAIR"):
        return False
    try:
        hours = float(resolve_env("DEEPER_NOTEBOOK_AUTO_EXPORT_HOURS", "24") or 24)
    except ValueError:
        hours = 24.0
    return not hours <= 0


def _providers_for_request(request: Request) -> RuntimeSnapshotProviders:
    configured = getattr(request.app.state, "runtime_snapshot_providers", None)
    if isinstance(configured, RuntimeSnapshotProviders):
        return configured
    vault_provider = getattr(request.app.state, "runtime_vault_summary_provider", None)
    knowledge_provider = getattr(
        request.app.state, "runtime_knowledge_summary_provider", None
    )
    auto_export_provider = getattr(
        request.app.state, "runtime_auto_export_directory_provider", None
    )
    uptime_provider = getattr(
        request.app.state, "runtime_uptime_seconds_provider", None
    )
    expected_provider = getattr(
        request.app.state, "runtime_auto_export_expected_provider", None
    )
    return RuntimeSnapshotProviders(
        readiness=getattr(request.app.state, "runtime_readiness_provider", None),
        startup_receipts=getattr(
            request.app.state, "runtime_startup_receipt_provider", None
        ),
        update_status=getattr(
            request.app.state, "runtime_update_status_provider", None
        ),
        vault_summary=vault_provider or (lambda: _vault_summary(request)),
        knowledge_summary=knowledge_provider or (lambda: _knowledge_summary(request)),
        auto_export_directory=auto_export_provider,
        uptime_seconds=uptime_provider or _process_uptime_seconds,
        auto_export_expected=expected_provider or _auto_export_expected,
    )


@router.get(
    "/api/runtime/snapshot",
    response_model=RuntimeSnapshot,
    tags=["runtime"],
)
async def get_runtime_snapshot(
    request: Request,
    _authenticated: bool = Depends(check_api_password),
) -> RuntimeSnapshot:
    """Return a bounded runtime projection; never perform runtime actions."""

    return await build_runtime_snapshot(_providers_for_request(request))


__all__ = ["MAX_VAULT_SUMMARY_MOUNTS", "get_runtime_snapshot", "router"]
