"""ONP v0.6.2 — Unit tests for the Gmail digest scheduler.

Covers the pure decision logic in `_should_send` and `_backoff_for`, and the
failure-recording state machine. Doesn't touch SurrealDB or the network —
the only thing exercised is the scheduler's own bookkeeping.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from deeper_notebook.digest import scheduler


def _make_g(*, enabled=True, connected=True, frequency="daily", last_sent_at=None):
    """Build a fake GmailIntegration-shaped object. We don't need the real
    domain model — only the four attributes `_should_send` reads."""
    return SimpleNamespace(
        enabled=enabled,
        is_connected=connected,
        frequency=frequency,
        last_sent_at=last_sent_at,
        email_address="user@example.com",
    )


@pytest.fixture(autouse=True)
def _reset_failure_state():
    """Each test starts with a clean backoff state."""
    scheduler._failure_state["consecutive_failures"] = 0
    scheduler._failure_state["next_retry_after"] = datetime.fromtimestamp(
        0, tz=timezone.utc
    )
    yield
    # And leaves it clean.
    scheduler._failure_state["consecutive_failures"] = 0
    scheduler._failure_state["next_retry_after"] = datetime.fromtimestamp(
        0, tz=timezone.utc
    )


# -------- _should_send guards --------


@pytest.mark.asyncio
async def test_should_not_send_when_disabled():
    g = _make_g(enabled=False)
    assert await scheduler._should_send(g) is False


@pytest.mark.asyncio
async def test_should_not_send_when_disconnected():
    g = _make_g(connected=False)
    assert await scheduler._should_send(g) is False


@pytest.mark.asyncio
async def test_should_not_send_when_manual():
    g = _make_g(frequency="manual")
    assert await scheduler._should_send(g) is False


@pytest.mark.asyncio
async def test_should_not_send_when_unknown_frequency():
    g = _make_g(frequency="every-blue-moon")
    assert await scheduler._should_send(g) is False


# -------- _should_send timing --------


@pytest.mark.asyncio
async def test_should_send_first_time_when_no_last_sent():
    g = _make_g(last_sent_at=None)
    assert await scheduler._should_send(g) is True


@pytest.mark.asyncio
async def test_should_not_send_daily_too_recent():
    g = _make_g(last_sent_at=datetime.now(timezone.utc) - timedelta(hours=22))
    assert await scheduler._should_send(g) is False


@pytest.mark.asyncio
async def test_should_send_daily_after_23h():
    g = _make_g(
        last_sent_at=datetime.now(timezone.utc) - timedelta(hours=23, minutes=5)
    )
    assert await scheduler._should_send(g) is True


@pytest.mark.asyncio
async def test_should_not_send_weekly_after_6_days():
    g = _make_g(
        frequency="weekly",
        last_sent_at=datetime.now(timezone.utc) - timedelta(days=6, hours=20),
    )
    assert await scheduler._should_send(g) is False


@pytest.mark.asyncio
async def test_should_send_weekly_after_7_days():
    g = _make_g(
        frequency="weekly",
        last_sent_at=datetime.now(timezone.utc) - timedelta(days=7, minutes=5),
    )
    assert await scheduler._should_send(g) is True


# -------- backoff curve --------


def test_backoff_starts_at_minimum():
    assert scheduler._backoff_for(1) == scheduler._FAILURE_BACKOFF_MIN


def test_backoff_doubles_each_failure():
    assert scheduler._backoff_for(2) == scheduler._FAILURE_BACKOFF_MIN * 2
    assert scheduler._backoff_for(3) == scheduler._FAILURE_BACKOFF_MIN * 4


def test_backoff_caps_at_max():
    # After many failures the backoff is clamped to _FAILURE_BACKOFF_MAX.
    assert scheduler._backoff_for(99) == scheduler._FAILURE_BACKOFF_MAX


# -------- backoff respected by _should_send --------


@pytest.mark.asyncio
async def test_should_not_send_during_backoff_window():
    """After a failure, _should_send returns False until backoff elapses,
    even when last_sent_at is None (first send)."""
    g = _make_g(last_sent_at=None)
    # Simulate: just failed, next retry not yet due
    scheduler._record_failure(reason="gmail down")
    assert await scheduler._should_send(g) is False


@pytest.mark.asyncio
async def test_should_send_again_after_backoff_expires():
    g = _make_g(last_sent_at=None)
    # Push next_retry_after into the past to simulate backoff window expired
    scheduler._failure_state["consecutive_failures"] = 1
    scheduler._failure_state["next_retry_after"] = datetime.now(
        timezone.utc
    ) - timedelta(seconds=1)
    assert await scheduler._should_send(g) is True


def test_record_failure_bumps_counter_and_pushes_retry():
    before = scheduler._failure_state["consecutive_failures"]
    scheduler._record_failure(reason="network error")
    assert scheduler._failure_state["consecutive_failures"] == before + 1
    # next_retry_after now in the future
    assert scheduler._failure_state["next_retry_after"] > datetime.now(timezone.utc)
