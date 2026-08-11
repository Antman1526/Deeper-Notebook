"""Authenticated, read-only runtime snapshot endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from api.auth import check_api_password
from api.runtime_snapshot import (
    RuntimeSnapshot,
    RuntimeSnapshotProviders,
    build_runtime_snapshot,
)

router = APIRouter()


async def _vault_summary(request: Request) -> list[dict[str, Any]] | None:
    service = getattr(request.app.state, "vault_service", None)
    repository = getattr(service, "_repository", None)
    list_mounts = getattr(repository, "list_mounts", None)
    if not callable(list_mounts):
        return None
    mounts = await list_mounts()
    return [
        {
            "status": getattr(mount, "status", None),
            "write_policy": getattr(mount, "write_policy", None),
        }
        for mount in mounts
    ]


async def _knowledge_summary(request: Request) -> dict[str, Any] | None:
    service = getattr(request.app.state, "knowledge_engine_service", None)
    status = getattr(service, "status", None)
    if not callable(status):
        return None
    projection = await status()
    if isinstance(projection, dict):
        return projection
    return {
        "projected": getattr(projection, "projected", None),
        "unchanged": getattr(projection, "unchanged", None),
        "failed": getattr(projection, "failed", None),
    }


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
    return RuntimeSnapshotProviders(
        readiness=getattr(request.app.state, "runtime_readiness_provider", None),
        startup_receipts=getattr(request.app.state, "runtime_startup_receipt_provider", None),
        update_status=getattr(request.app.state, "runtime_update_status_provider", None),
        vault_summary=vault_provider or (lambda: _vault_summary(request)),
        knowledge_summary=knowledge_provider or (lambda: _knowledge_summary(request)),
        auto_export_directory=auto_export_provider,
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


__all__ = ["get_runtime_snapshot", "router"]
