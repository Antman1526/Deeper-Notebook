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


async def _should_send(g: GmailIntegration) -> bool:
    """Decide whether to fire a send right now."""
    if not g.enabled or not g.is_connected:
        return False
    if g.frequency == "manual":
        return False
    interval = _INTERVAL_BY_FREQ.get(g.frequency)
    if interval is None:
        return False  # unknown frequency = no auto-send
    if g.last_sent_at is None:
        return True  # first time
    return datetime.now(timezone.utc) - g.last_sent_at >= interval


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
    except Exception as exc:
        log.warning("digest-scheduler tick failed (non-fatal): %s", exc)


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
