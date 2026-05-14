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

from open_notebook.domain.gmail import GmailIntegration

log = logging.getLogger(__name__)

# Wake interval: short enough that "send at midnight" feels responsive,
# long enough that we're not hammering the DB.
_TICK_INTERVAL_SEC = 300  # 5 minutes

# Per-frequency minimum delta between sends.
_INTERVAL_BY_FREQ = {
    "daily":  timedelta(hours=23),
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


def _backoff_for(consecutive: int) -> timedelta:
    """15min → 30min → 1h → 2h → 4h → 6h (cap). Pure for testability.

    The exponent is clamped to 16 first so we never multiply by a huge int
    (timedelta multiplication overflows C int well before that). The cap is
    enforced afterwards regardless.
    """
    exp = min(max(0, consecutive - 1), 16)
    delay = _FAILURE_BACKOFF_MIN * (2 ** exp)
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
    try:
        g = await GmailIntegration.get()
        if not await _should_send(g):
            return
        # Lazy import to avoid circular (router imports digest module)
        from api.routers.gmail import _send_digest_now
        log.info("digest-scheduler: firing %s send for %s",
                 g.frequency, g.email_address)
        ok, msg, n = await _send_digest_now(g, label=g.frequency.title())
        log.info("digest-scheduler: result ok=%s items=%d msg=%r", ok, n, msg)
        if ok:
            # Success — clear backoff state.
            _failure_state["consecutive_failures"] = 0
            _failure_state["next_retry_after"] = datetime.fromtimestamp(0, tz=timezone.utc)
        else:
            # Soft failure (HTTP non-200 from Gmail, refresh failed, etc).
            _record_failure(reason=msg)
    except Exception as exc:
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
        n, reason, delay,
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
