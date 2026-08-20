"""ONP v0.6.1 — Background scheduler for periodic digest sends.

Runs as a single asyncio task started by api/main.py's lifespan handler.
Wakes every 5 minutes (cheap), checks if it's time to send, and dispatches
the send to `gmail._send_digest_now`. The scheduler is intentionally simple
— no cron expressions, just frequency tags ("daily" | "weekly" | "manual").

State of the world it manages:
  - Read GmailIntegration.frequency + last_sent_at
  - If frequency == "manual": never auto-send
  - If frequency == "daily":  send if 23h+ since last_sent_at
  - If frequency == "weekly": send if 6d23h+ since last_sent_at
  - First-time: send if connected + enabled and last_sent_at is None
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from deeper_notebook.domain.gmail import GmailIntegration

log = logging.getLogger(__name__)

# Wake interval: short enough that "send at midnight" feels responsive,
# long enough that we're not hammering the DB.
_TICK_INTERVAL_SEC = 300  # 5 minutes

# Per-frequency minimum delta between sends.
_INTERVAL_BY_FREQ = {
    "daily": timedelta(hours=23),
    "weekly": timedelta(days=6, hours=23),
}

# v0.6.2 — Failure backoff. A persistent gmail error (token revoked,
# network unreachable, etc) would otherwise retry every tick (5 min)
# forever. After a failure, wait at least this long before trying again;
# doubles up to a cap on consecutive failures.
_FAILURE_BACKOFF_MIN = timedelta(minutes=15)
_FAILURE_BACKOFF_MAX = timedelta(hours=6)

# Module-level mutable state: tracks consecutive failures and last attempt.
# We accept losing this state on API restart — a restart is itself a
# reasonable retry trigger.
_failure_state: dict[str, datetime | int] = {
    "consecutive_failures": 0,
    "next_retry_after": datetime.fromtimestamp(0, tz=timezone.utc),
}

# v0.8.68 — offline deferral (spec §5). A digest due while offline is
# deferred WITHOUT escalating the failure backoff: the digest stays "due"
# (last_sent_at unchanged) so the regular 5-minute tick retries it as soon
# as connectivity returns. This marker only powers the /gmail/status
# "pending_digest" indicator; clearing it never suppresses a send.
_pending_digest_since: datetime | None = None
_PENDING_MAX_AGE = timedelta(hours=24)


def reset_pending_digest_for_tests() -> None:
    global _pending_digest_since
    _pending_digest_since = None


def pending_digest_info() -> dict:
    """Read-only view for the canonical Gmail status endpoint."""
    if _pending_digest_since is None:
        return {"pending": False, "since": None}
    return {"pending": True, "since": _pending_digest_since.isoformat()}


async def _offline_now() -> bool:
    """Network-state check, fail-open: a broken probe must never stop
    digests from sending."""
    try:
        from deeper_notebook.health.network import get_network_state_with_settings

        return (await get_network_state_with_settings()).status == "offline"
    except Exception:
        return False


def _mark_pending() -> None:
    global _pending_digest_since
    now = datetime.now(timezone.utc)
    if _pending_digest_since is None or now - _pending_digest_since > _PENDING_MAX_AGE:
        # Fresh deferral, or a stale (>24h) marker — re-stamp. With the
        # daily/weekly last_sent_at semantics an old pending digest simply
        # merges into the next due one, so the timestamp is informational.
        _pending_digest_since = now


def _backoff_for(consecutive: int) -> timedelta:
    """15min → 30min → 1h → 2h → 4h → 6h (cap). Pure for testability.

    The exponent is clamped to 16 first so we never multiply by a huge int
    (timedelta multiplication overflows C int well before that). The cap is
    enforced afterwards regardless.
    """
    exp = min(max(0, consecutive - 1), 16)
    delay = _FAILURE_BACKOFF_MIN * (2**exp)
    return min(delay, _FAILURE_BACKOFF_MAX)


async def _should_send(g: GmailIntegration) -> bool:
    """Decide whether to fire a send right now."""
    if not g.enabled or not g.is_connected:
        return False
    if g.frequency == "manual":
        return False
    interval = _INTERVAL_BY_FREQ.get(g.frequency)
    if interval is None:
        return False  # unknown frequency = no auto-send
    # Respect failure backoff (set by _tick on previous failed attempts).
    now = datetime.now(timezone.utc)
    next_retry = _failure_state["next_retry_after"]
    if isinstance(next_retry, datetime) and now < next_retry:
        return False
    if g.last_sent_at is None:
        return True  # first time
    return now - g.last_sent_at >= interval


async def _tick() -> None:
    """One iteration: check + send if due. Never raises; logs on error."""
    global _pending_digest_since
    try:
        g = await GmailIntegration.get()
        if not await _should_send(g):
            return
        # v0.8.68 — offline deferral: a due digest on an offline machine
        # previously burned a real send attempt (20s httpx timeout) and
        # escalated the failure backoff up to 6h — so the digest often
        # never went out even after connectivity returned. Now we defer
        # cheaply: the digest stays due, the next tick (5 min) retries,
        # and the backoff state is untouched.
        if await _offline_now():
            _mark_pending()
            log.info(
                "digest-scheduler: offline — digest deferred (will retry next tick)"
            )
            return
        # Lazy import to avoid circular (router imports digest module)
        from api.routers.gmail import _send_digest_now

        log.info(
            "digest-scheduler: firing %s send for %s", g.frequency, g.email_address
        )
        ok, msg, n = await _send_digest_now(g, label=g.frequency.title())
        log.info("digest-scheduler: result ok=%s items=%d msg=%r", ok, n, msg)
        if ok:
            # Success — clear backoff state and the pending marker.
            _pending_digest_since = None
            _failure_state["consecutive_failures"] = 0
            _failure_state["next_retry_after"] = datetime.fromtimestamp(
                0, tz=timezone.utc
            )
        else:
            # Soft failure (HTTP non-200 from Gmail, refresh failed, etc).
            _record_failure(reason=msg)
    except Exception as exc:
        # v0.8.68 — a network-classified failure (captive portal / drop the
        # TCP probe missed) defers like the offline branch above instead of
        # escalating backoff, and flips the shared network state so the
        # rest of the app (chat gate, web search) reacts immediately.
        try:
            from deeper_notebook.exceptions import NetworkError
            from deeper_notebook.health.network import report_network_failure
            from deeper_notebook.utils.error_classifier import classify_error

            error_class, _ = classify_error(exc)
            if error_class is NetworkError or isinstance(exc, NetworkError):
                report_network_failure()
                _mark_pending()
                log.warning(
                    "digest-scheduler: send failed with a network error — "
                    "digest deferred (no backoff escalation)"
                )
                return
        except Exception:
            pass  # classification problems fall through to the generic path
        log.warning("digest-scheduler tick failed (non-fatal): %s", exc)
        _record_failure(reason=str(exc))


def _record_failure(reason: str) -> None:
    """Bump the consecutive-failure counter and push back next retry."""
    n = int(_failure_state["consecutive_failures"]) + 1
    delay = _backoff_for(n)
    _failure_state["consecutive_failures"] = n
    _failure_state["next_retry_after"] = datetime.now(timezone.utc) + delay
    log.warning(
        "digest-scheduler: failure #%d (%s) — backing off %s",
        n,
        reason,
        delay,
    )


async def run_forever(stop_event: asyncio.Event | None = None) -> None:
    """Loop until stop_event is set (or forever if None).

    Called by api/main.py's lifespan handler as a background task. Tolerant
    of all errors — a single failed tick should never break the API process.
    """
    log.info("digest-scheduler started (tick=%ds)", _TICK_INTERVAL_SEC)
    while True:
        await _tick()
        if stop_event is not None:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=_TICK_INTERVAL_SEC)
                # If we reach here without TimeoutError, stop was signalled
                log.info("digest-scheduler stop signalled")
                return
            except asyncio.TimeoutError:
                pass  # normal — continue loop
        else:
            await asyncio.sleep(_TICK_INTERVAL_SEC)
