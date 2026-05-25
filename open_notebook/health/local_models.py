"""Phase 1 — Active health probes for each local-model sidecar.

Distinct from /healthz/deep (which is the API's own readiness):
this module probes the local llama-cpp / whisper / piper / memory
shims to verify they actually respond, not just that their port
is bound.
"""
from __future__ import annotations
from typing import Literal, TypedDict
import time
import httpx


class HealthResult(TypedDict):
    name: str
    status: Literal["healthy", "unhealthy", "not_configured", "unknown"]
    detail: str | None
    latency_ms: float | None


# Phase 1 Task 2 — bounded probe budgets so a wedged sidecar can't
# hang the launch-time health sweep. Same structured-Timeout shape
# as credentials_service uses for discovery probes.
_PROBE_TIMEOUT = httpx.Timeout(
    connect=2.0, read=5.0, write=2.0, pool=2.0,
)


def probe_local_model(
    *, name: str, kind: str, base_url: str,
) -> HealthResult:
    """Probe a single local sidecar. Returns a HealthResult dict.

    Phase 1 Task 1: detects port-0 placeholders.
    Phase 1 Task 2: live HTTP probe for openai_compatible kind.
    """
    if ":0/" in base_url or base_url.endswith(":0"):
        return {
            "name": name, "status": "not_configured",
            "detail": "port not allocated this session",
            "latency_ms": None,
        }
    if kind == "openai_compatible":
        return _probe_openai_compatible(name=name, base_url=base_url)
    return {
        "name": name, "status": "unknown",
        "detail": f"no probe for kind={kind!r}",
        "latency_ms": None,
    }


def _probe_openai_compatible(*, name: str, base_url: str) -> HealthResult:
    """Hit `{base_url}/models` — the standard OpenAI-compatible
    discovery endpoint. Returns healthy with latency + first few
    model names on 200; unhealthy with the status code or
    connect-error detail otherwise."""
    url = f"{base_url.rstrip('/')}/models"
    start = time.monotonic()
    try:
        with httpx.Client(timeout=_PROBE_TIMEOUT) as client:
            resp = client.get(url)
            latency_ms = (time.monotonic() - start) * 1000
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id", "?") for m in data.get("data", [])]
                detail = ", ".join(models[:3]) if models else "no models listed"
                return {
                    "name": name, "status": "healthy",
                    "detail": detail, "latency_ms": latency_ms,
                }
            return {
                "name": name, "status": "unhealthy",
                "detail": f"HTTP {resp.status_code}",
                "latency_ms": latency_ms,
            }
    except httpx.ConnectError as exc:
        return {
            "name": name, "status": "unhealthy",
            "detail": f"connect refused: {exc}",
            "latency_ms": None,
        }
    except Exception as exc:
        return {
            "name": name, "status": "unhealthy",
            "detail": f"{type(exc).__name__}: {exc}",
            "latency_ms": None,
        }
