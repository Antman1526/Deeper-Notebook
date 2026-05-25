"""Phase 1 Task 3 — Aggregated local-model health endpoint.

Frontend's sidebar badge component polls this every 30s; the
launcher also calls it via the in-process function at startup
so launcher.log captures verified-working status.
"""
from __future__ import annotations
from fastapi import APIRouter

router = APIRouter()


def _load_local_credentials() -> list[dict]:
    """Fetch credentials whose `provider == 'openai_compatible'`
    AND whose `base_url` is a 127.0.0.1 URL (i.e., a local sidecar
    spawned by our supervisor — NOT a user-configured external
    openai_compatible endpoint like LM Studio on a remote box)."""
    import asyncio
    from open_notebook.domain.credential import Credential

    async def _fetch():
        creds = await Credential.get_all()
        return [
            {
                "name": c.name,
                "kind": c.provider,
                "base_url": c.base_url or "",
            }
            for c in creds
            if c.provider == "openai_compatible"
            and (c.base_url or "").startswith("http://127.0.0.1")
        ]
    # We're called from a sync FastAPI endpoint that's wrapped in
    # an executor; we can spin a fresh loop safely here. If you
    # change this endpoint to `async def`, swap to direct `await`.
    return asyncio.run(_fetch())


@router.get("/api/local-models/health")
def local_models_health():
    """Active health probe across all local sidecars. Each probe
    has its own ≤9s timeout; total endpoint latency scales with
    the number of registered local credentials (typically 4-5)."""
    from open_notebook.health.local_models import probe_all_local_models

    creds = _load_local_credentials()
    results = probe_all_local_models(creds)
    healthy = sum(1 for r in results if r["status"] == "healthy")
    total_configured = sum(
        1 for r in results if r["status"] != "not_configured"
    )
    if total_configured == 0:
        overall = "down"
    elif healthy == total_configured:
        overall = "healthy"
    else:
        overall = "degraded"
    return {"overall": overall, "models": results}
