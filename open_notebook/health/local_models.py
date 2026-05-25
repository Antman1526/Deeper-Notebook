"""Phase 1 — Active health probes for each local-model sidecar.

Distinct from /healthz/deep (which is the API's own readiness):
this module probes the local llama-cpp / whisper / piper / memory
shims to verify they actually respond, not just that their port
is bound.
"""
from __future__ import annotations
from typing import Literal, TypedDict


class HealthResult(TypedDict):
    name: str
    status: Literal["healthy", "unhealthy", "not_configured", "unknown"]
    detail: str | None
    latency_ms: float | None


def probe_local_model(
    *, name: str, kind: str, base_url: str,
) -> HealthResult:
    """Probe a single local sidecar. Returns a HealthResult dict.

    Phase 1 — only returns `not_configured` when the URL is
    clearly a placeholder (port 0). Future tasks add live HTTP probes.
    """
    if ":0/" in base_url or base_url.endswith(":0"):
        return {
            "name": name, "status": "not_configured",
            "detail": "port not allocated this session",
            "latency_ms": None,
        }
    return {
        "name": name, "status": "unknown",
        "detail": "no probe implemented yet",
        "latency_ms": None,
    }
