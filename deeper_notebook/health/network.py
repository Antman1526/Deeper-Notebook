"""v0.8.68 — process-wide network-state service.

Answers "does this machine currently have internet?" for the offline
gate (deeper_notebook/ai/offline_gate.py), the web_search tool, the Gmail
digest scheduler, and GET /api/system/network-status.

Design (spec 2026-06-11):
  - 2s TCP probe to two well-known hosts (override: DEEPER_NOTEBOOK_NET_PROBE_HOSTS),
    run via asyncio.to_thread so the event loop never blocks.
  - TTL cache (default 20s, DEEPER_NOTEBOOK_NETWORK_STATE_TTL_SEC) with a single-flight
    lock — concurrent cache-misses share one probe (same pattern as
    provision.py's _health_cache_lock, v0.8.35).
  - Passive updates: report_network_failure()/report_network_success()
    flip the cache immediately when a real cloud call fails/succeeds —
    this also covers captive portals where the TCP probe lies.
  - "unknown" (probe exception) is treated as ONLINE by consumers: we
    never block cloud calls on a flaky probe; real failures correct it.
  - forced_offline_lookup: callers pass a callable for the user's
    Offline-mode toggle so this module has no settings/DB dependency.
"""

from __future__ import annotations

import asyncio
import os
import socket
import time
from dataclasses import dataclass
from typing import Callable, Literal

from loguru import logger

from deeper_notebook.environment import resolve_env

_DEFAULT_PROBE_TARGETS: list[tuple[str, int]] = [("1.1.1.1", 443), ("8.8.8.8", 443)]
_PROBE_TIMEOUT_S = 2.0
_DEFAULT_TTL_S = 20.0


@dataclass(frozen=True)
class NetworkState:
    status: Literal["online", "offline", "unknown"]
    forced_offline: bool
    checked_at: float  # time.monotonic()
    source: Literal["probe", "call-failure", "call-success", "override", "init"]


_state: NetworkState | None = None
_probe_lock: "asyncio.Lock | None" = None


def _get_probe_lock() -> asyncio.Lock:
    # Lazy init — same rationale as provision.py _get_health_cache_lock:
    # imports stay side-effect-free, no event loop needed at import time.
    global _probe_lock
    if _probe_lock is None:
        _probe_lock = asyncio.Lock()
    return _probe_lock


def _ttl_s() -> float:
    try:
        v = float(
            resolve_env("DEEPER_NOTEBOOK_NETWORK_STATE_TTL_SEC") or _DEFAULT_TTL_S
        )
        return v if v > 0 else _DEFAULT_TTL_S
    except ValueError:
        return _DEFAULT_TTL_S


def _probe_targets() -> list[tuple[str, int]]:
    raw = (resolve_env("DEEPER_NOTEBOOK_NET_PROBE_HOSTS") or "").strip()
    if not raw:
        return _DEFAULT_PROBE_TARGETS
    targets: list[tuple[str, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        host, _, port_s = part.rpartition(":")
        try:
            port = int(port_s)
        except ValueError:
            continue
        if host and 0 < port < 65536:
            targets.append((host, port))
    return targets or _DEFAULT_PROBE_TARGETS


def _probe_once() -> bool:
    """Blocking TCP probe — first target that connects wins. Runs on a
    worker thread (see get_network_state). OSErrors per-target are part
    of the normal "that host is unreachable" flow; only a fully failed
    sweep returns False."""
    for host, port in _probe_targets():
        try:
            with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT_S):
                return True
        except OSError:
            continue
    return False


def report_network_failure() -> None:
    """A real outbound call failed with a network-classified error."""
    global _state
    _state = NetworkState(
        status="offline",
        forced_offline=False,
        checked_at=time.monotonic(),
        source="call-failure",
    )
    logger.info("v0.8.68 network-state: flipped OFFLINE (cloud call failed)")


def report_network_success() -> None:
    """A real outbound call succeeded — we are definitely online."""
    global _state
    _state = NetworkState(
        status="online",
        forced_offline=False,
        checked_at=time.monotonic(),
        source="call-success",
    )


def reset_network_state_for_tests() -> None:
    global _state, _probe_lock, _forced_cache
    _state = None
    _probe_lock = None
    _forced_cache = None


async def get_network_state(
    *,
    forced_offline_lookup: Callable[[], bool] | None = None,
) -> NetworkState:
    """Current network state. Forced-offline check first (no probe), then
    TTL cache, then a single-flight thread-side TCP probe."""
    global _state
    if forced_offline_lookup is not None:
        try:
            forced = bool(forced_offline_lookup())
        except Exception:
            forced = False  # settings hiccup must never brick cloud access
        if forced:
            return NetworkState(
                status="offline",
                forced_offline=True,
                checked_at=time.monotonic(),
                source="override",
            )

    now = time.monotonic()
    if _state is not None and now - _state.checked_at < _ttl_s():
        return _state

    async with _get_probe_lock():
        now = time.monotonic()
        if _state is not None and now - _state.checked_at < _ttl_s():
            return _state
        try:
            up = await asyncio.to_thread(_probe_once)
            status: Literal["online", "offline", "unknown"] = (
                "online" if up else "offline"
            )
        except Exception as exc:
            logger.debug(f"v0.8.68 network probe errored ({exc!r}) → unknown")
            status = "unknown"
        _state = NetworkState(
            status=status,
            forced_offline=False,
            checked_at=time.monotonic(),
            source="probe",
        )
    return _state


# ---------------------------------------------------------------------------
# v0.8.68 — forced-offline (Offline mode toggle) accessor.
# ContentSettings lives in SurrealDB; we cache the boolean for 30s so the
# per-turn gate doesn't add a DB read to every provisioning call. The
# settings PUT handler calls invalidate_forced_offline_cache() on change.
_FORCED_TTL_S = 30.0
_forced_cache: "tuple[float, bool] | None" = None


def invalidate_forced_offline_cache() -> None:
    global _forced_cache
    _forced_cache = None


async def forced_offline_enabled() -> bool:
    global _forced_cache
    now = time.monotonic()
    if _forced_cache is not None and now - _forced_cache[0] < _FORCED_TTL_S:
        return _forced_cache[1]
    try:
        from deeper_notebook.domain.content_settings import ContentSettings

        settings = await ContentSettings.get_instance()
        value = bool(getattr(settings, "offline_mode", False))
    except Exception:
        value = False  # DB hiccup must never brick cloud access (spec table)
    _forced_cache = (now, value)
    return value


async def get_network_state_with_settings() -> NetworkState:
    """get_network_state honoring the persisted Offline-mode toggle.
    The toggle check is async (DB-backed) so it can't be passed as the
    sync forced_offline_lookup callable — resolve it first."""
    if await forced_offline_enabled():
        return NetworkState(
            status="offline",
            forced_offline=True,
            checked_at=time.monotonic(),
            source="override",
        )
    return await get_network_state()
