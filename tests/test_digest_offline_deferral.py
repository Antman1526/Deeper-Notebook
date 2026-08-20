"""v0.8.68 — digest scheduler defers sends while offline instead of silently
failing, retries on the next tick (no backoff escalation for network drops),
and keeps a pending marker for /gmail/status."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from deeper_notebook.digest import scheduler
from deeper_notebook.exceptions import NetworkError


@pytest.fixture(autouse=True)
def _reset():
    scheduler.reset_pending_digest_for_tests()
    scheduler._failure_state["consecutive_failures"] = 0
    scheduler._failure_state["next_retry_after"] = datetime.fromtimestamp(
        0, tz=timezone.utc
    )
    yield
    scheduler.reset_pending_digest_for_tests()
    scheduler._failure_state["consecutive_failures"] = 0
    scheduler._failure_state["next_retry_after"] = datetime.fromtimestamp(
        0, tz=timezone.utc
    )


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _gmail(frequency="daily"):
    return SimpleNamespace(
        enabled=True,
        is_connected=True,
        frequency=frequency,
        last_sent_at=None,  # first-time → due
        email_address="user@example.com",
    )


def _patch_gmail(monkeypatch, g):
    async def _fake_get():
        return g

    monkeypatch.setattr(scheduler.GmailIntegration, "get", _fake_get)


def _patch_offline(monkeypatch, offline: bool):
    async def _fake():
        return offline

    monkeypatch.setattr(scheduler, "_offline_now", _fake)


def _patch_send(monkeypatch, sends, *, ok=True, raises=None):
    import api.routers.gmail as gmail_router

    async def _fake_send(g, label="Digest"):
        if raises is not None:
            raise raises
        sends.append(label)
        return (ok, "ok" if ok else "soft failure", 1)

    monkeypatch.setattr(gmail_router, "_send_digest_now", _fake_send)


def test_offline_defers_without_backoff(monkeypatch):
    _patch_gmail(monkeypatch, _gmail())
    _patch_offline(monkeypatch, True)
    sends: list = []
    _patch_send(monkeypatch, sends)

    _run(scheduler._tick())
    assert sends == []
    assert scheduler.pending_digest_info()["pending"] is True
    # Deferral must NOT escalate the failure backoff — the next tick retries.
    assert scheduler._failure_state["consecutive_failures"] == 0


def test_online_sends_and_clears_pending(monkeypatch):
    _patch_gmail(monkeypatch, _gmail())
    _patch_offline(monkeypatch, False)
    sends: list = []
    _patch_send(monkeypatch, sends)

    # Pre-existing pending marker from an earlier offline tick.
    scheduler._pending_digest_since = datetime.now(timezone.utc)

    _run(scheduler._tick())
    assert sends == ["Daily"]
    assert scheduler.pending_digest_info()["pending"] is False


def test_network_error_defers_without_backoff(monkeypatch):
    _patch_gmail(monkeypatch, _gmail())
    _patch_offline(monkeypatch, False)  # captive-portal case: looks online
    sends: list = []
    _patch_send(monkeypatch, sends, raises=NetworkError("no route to host"))

    _run(scheduler._tick())
    assert sends == []
    assert scheduler.pending_digest_info()["pending"] is True
    assert scheduler._failure_state["consecutive_failures"] == 0


def test_non_network_failure_still_backs_off(monkeypatch):
    _patch_gmail(monkeypatch, _gmail())
    _patch_offline(monkeypatch, False)
    sends: list = []
    _patch_send(monkeypatch, sends, raises=RuntimeError("token revoked"))

    _run(scheduler._tick())
    assert scheduler._failure_state["consecutive_failures"] == 1
    assert scheduler.pending_digest_info()["pending"] is False


def test_stale_pending_marker_clears(monkeypatch):
    _patch_gmail(monkeypatch, _gmail())
    _patch_offline(monkeypatch, True)
    sends: list = []
    _patch_send(monkeypatch, sends)

    scheduler._pending_digest_since = datetime.now(timezone.utc) - timedelta(hours=25)
    _run(scheduler._tick())
    # >24h old: marker resets to "now" semantics — it reports pending with a
    # fresh timestamp rather than claiming a day-old queued digest.
    info = scheduler.pending_digest_info()
    assert info["pending"] is True
    since = datetime.fromisoformat(info["since"])
    assert datetime.now(timezone.utc) - since < timedelta(minutes=1)
