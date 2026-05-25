"""Phase 1 Task 3 — Aggregated local-model health endpoint.

Frontend's sidebar badge component polls this every 30s; the
launcher also calls it via the in-process function at startup
so launcher.log captures verified-working status.
"""
from __future__ import annotations
from fastapi import APIRouter

router = APIRouter()


async def _load_local_credentials() -> list[dict]:
    """Fetch credentials whose `provider == 'openai_compatible'`
    AND whose `base_url` points to a local sidecar (127.0.0.1
    OR localhost). The local-only filter is load-bearing — we
    don't want this endpoint to probe a user-configured remote
    LM Studio or Ollama on a LAN box. That's a different concern
    and would belong on a different surface.

    v0.8.0 Task 3 refactor — was sync + `asyncio.run`; converted
    to async to eliminate the future-refactor footgun (the
    `asyncio.run` would explode if the caller ever became async).
    Also widened the local-sidecar match to include `localhost`
    so users who registered an openai_compatible credential as
    `http://localhost:PORT/v1` (common LM Studio default) are
    picked up by the probe."""
    from open_notebook.domain.credential import Credential

    creds = await Credential.get_all()
    return [
        {
            "name": c.name,
            "kind": c.provider,
            "base_url": c.base_url or "",
        }
        for c in creds
        if c.provider == "openai_compatible"
        and _is_local_sidecar_url(c.base_url or "")
    ]


def _is_local_sidecar_url(url: str) -> bool:
    """Match `http://127.0.0.1[:PORT]...` or `http://localhost[:PORT]...`.
    https:// is intentionally NOT matched today — none of our
    bundled sidecars use TLS, and a user-configured https endpoint
    is more likely to be a remote service than a local sidecar."""
    return (
        url.startswith("http://127.0.0.1")
        or url.startswith("http://localhost")
    )


@router.get("/api/local-models/health")
async def local_models_health():
    """Active health probe across all local sidecars. Each probe
    has its own ≤9s timeout; total endpoint latency scales with
    the number of registered local credentials (typically 4-5)."""
    from open_notebook.health.local_models import probe_all_local_models

    creds = await _load_local_credentials()
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
