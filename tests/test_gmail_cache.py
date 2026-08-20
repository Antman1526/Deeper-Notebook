"""v0.7.157 — Tests for GmailIntegration TTL cache + bounded-wait query.

Background: the singleton SurrealDB query (`SELECT * FROM ONLY $rid`)
was observed taking 4-8 seconds on cold-start. Two concurrent
frontend pollers (sidebar button + setup panel) each blocked for 8s
on every fresh launch — the perceived "frozen API after wizard"
experience.

These tests guard four behaviors of the v0.7.157 fix:

1. The first `.get()` populates the cache.
2. A subsequent `.get()` within the TTL is a free in-memory hit
   (DB query not re-executed).
3. `.save()` invalidates the cache (next read sees fresh data).
4. A SurrealDB call that exceeds the timeout returns a default
   instance instead of blocking the caller indefinitely.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from deeper_notebook.domain import gmail as gmail_mod
from deeper_notebook.domain.gmail import GmailIntegration


@pytest.fixture(autouse=True)
def _reset_cache():
    """Every test starts with an empty cache."""
    gmail_mod._invalidate_cache()
    yield
    gmail_mod._invalidate_cache()


@pytest.mark.asyncio
async def test_cache_hit_skips_db_query_within_ttl():
    """v0.7.157: a second .get() within the TTL window MUST NOT re-query.

    The previous code hit SurrealDB on every call; with adaptive 60s
    polling that meant 8-second cold-start delays compounding on every
    page navigation. The cache guarantees at most one DB roundtrip
    per 30-second window.
    """
    fake_row = {
        "client_id_enc": None,
        "client_secret_enc": None,
        "access_token_enc": None,
        "refresh_token_enc": None,
        "token_expires_at": None,
        "email_address": "user@example.com",
        "enabled": True,
        "frequency": "daily",
    }
    with patch(
        "deeper_notebook.domain.gmail.repo_query",
        new=AsyncMock(return_value=[fake_row]),
    ) as mock_query:
        first = await GmailIntegration.get()
        second = await GmailIntegration.get()
        third = await GmailIntegration.get()

    assert first.email_address == "user@example.com"
    assert second.email_address == "user@example.com"
    # DB hit ONCE — subsequent calls served from cache.
    assert mock_query.call_count == 1, (
        f"v0.7.157 cache should serve repeated .get() from memory; "
        f"got {mock_query.call_count} DB calls instead of 1"
    )
    # v0.8.66 (audit E-3) — the cache still serves all three WITHOUT re-querying
    # (asserted by call_count == 1 above), but get() now returns an independent
    # COPY each time rather than the shared cached instance, so callers that
    # mutate the result (disconnect/forget/send) can't alias the cache. So the
    # three are value-equal but distinct objects.
    assert first.email_address == second.email_address == third.email_address
    assert first.enabled == second.enabled == third.enabled
    assert first is not second and second is not third


@pytest.mark.asyncio
async def test_save_invalidates_cache():
    """v0.7.157: after a write, the next read MUST hit the DB so the
    user sees their latest changes (OAuth connect, settings toggle,
    disconnect) reflected immediately. Otherwise the UI lags 30s
    behind every settings change."""
    fake_row_before = {"email_address": "old@example.com", "enabled": False}
    fake_row_after = {"email_address": "new@example.com", "enabled": True}

    with (
        patch(
            "deeper_notebook.domain.gmail.repo_query",
            new=AsyncMock(side_effect=[[fake_row_before], [fake_row_after]]),
        ) as mock_query,
        patch(
            "deeper_notebook.domain.gmail.repo_upsert",
            new=AsyncMock(return_value=None),
        ),
    ):
        first = await GmailIntegration.get()
        assert first.email_address == "old@example.com"

        # User does an OAuth flow — save() must invalidate the cache
        first.email_address = "new@example.com"
        await first.save()

        # Next read should hit DB again, returning the post-save state
        second = await GmailIntegration.get()

    assert mock_query.call_count == 2
    assert second.email_address == "new@example.com"


@pytest.mark.asyncio
async def test_timeout_returns_default_instance():
    """v0.7.157: a SurrealDB query that exceeds the 3s timeout must NOT
    hold the HTTP request line indefinitely. Caller receives a default-
    constructed instance and a warning is logged so operators can see
    the underlying SurrealDB problem."""

    async def _slow_query(*a, **kw):
        # Simulate a SurrealDB call that exceeds the timeout
        await asyncio.sleep(10.0)
        return [{"email_address": "would_have_returned"}]

    with (
        patch("deeper_notebook.domain.gmail.repo_query", new=_slow_query),
        patch.object(gmail_mod, "_QUERY_TIMEOUT_S", 0.05),
    ):
        result = await GmailIntegration.get()

    # Default-constructed instance: empty / inactive
    assert result.email_address is None
    assert result.enabled is False
    assert result.is_connected is False


@pytest.mark.asyncio
async def test_empty_db_result_is_still_cached():
    """v0.7.157: when the singleton record doesn't exist yet (fresh
    install), .get() returns a default instance. That default MUST be
    cached too — otherwise the user hits the slow query on every page
    load until they actually OAuth-connect Gmail."""
    with patch(
        "deeper_notebook.domain.gmail.repo_query",
        new=AsyncMock(return_value=None),
    ) as mock_query:
        first = await GmailIntegration.get()
        second = await GmailIntegration.get()

    assert first.is_connected is False
    assert second.is_connected is False
    # Cache hit on the second call even when DB returned empty.
    assert mock_query.call_count == 1
