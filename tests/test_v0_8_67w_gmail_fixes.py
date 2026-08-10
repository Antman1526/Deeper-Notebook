"""v0.8.67w — unit tests for GmailIntegration copy isolation and single-flight send serialization.

This verifies:
1. `GmailIntegration.get()` returns a `.model_copy()` of the cached instance
   to prevent mutation aliasing (E-3).
2. `_send_digest_now` reload and check-under-lock behavior correctly suppresses
   duplicate scheduled sends (E-4).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from api.routers import gmail as gmail_router
from deeper_notebook.domain import gmail as gmail_mod
from deeper_notebook.domain.gmail import GmailIntegration


@pytest.fixture(autouse=True)
def _reset_gmail_state():
    gmail_mod._invalidate_cache()
    gmail_mod._CACHE_LOCK = None
    gmail_router._SEND_LOCK = None
    yield
    gmail_mod._invalidate_cache()
    gmail_mod._CACHE_LOCK = None
    gmail_router._SEND_LOCK = None


@pytest.mark.asyncio
async def test_gmail_get_returns_isolated_copy():
    """Assert that modifying the returned instance of GmailIntegration.get()
    does not mutate the cached instance (preventing cache poisoning/aliasing).
    """
    # 1. Mock DB row response
    db_row = {
        "client_id_enc": None,
        "client_secret_enc": None,
        "access_token_enc": None,
        "refresh_token_enc": None,
        "token_expires_at": None,
        "email_address": "original@example.com",
        "enabled": True,
        "frequency": "daily",
    }

    async def _mock_repo_query(q, vars=None):
        return [db_row]

    with patch("deeper_notebook.domain.gmail.repo_query", _mock_repo_query):
        # First call gets the object from DB and caches it
        g1 = await GmailIntegration.get()
        assert g1.email_address == "original@example.com"

        # Mutate the retrieved instance
        g1.email_address = "mutated@example.com"

        # Second call should fetch the copy of cached instance, preserving original value
        g2 = await GmailIntegration.get()
        assert g2.email_address == "original@example.com"
        assert g1.email_address == "mutated@example.com"
        assert id(g1) != id(g2)


@pytest.mark.asyncio
async def test_gmail_send_digest_single_flight_under_lock():
    """Assert that if two scheduled sends are triggered concurrently,
    only the first one sends the digest, and the second one exits early
    because the configuration was reloaded and re-checked under the lock.
    """
    # In-memory "database" state
    now_utc = datetime.now(timezone.utc)
    db_state = {
        "email_address": "user@example.com",
        "enabled": True,
        "frequency": "daily",
        # Set last_sent_at to yesterday so it is due
        "last_sent_at": now_utc - timedelta(days=1),
        "access_token_enc": None,
        "refresh_token_enc": "dummy_refresh",
        "client_id_enc": "dummy_client",
        "client_secret_enc": "dummy_secret",
    }

    async def _mock_repo_query(q, vars=None):
        # Simulate decrypter/decryption helper
        return [{
            **db_state,
            "last_sent_at": db_state["last_sent_at"].isoformat() if db_state["last_sent_at"] else None
        }]

    async def _mock_repo_upsert(table, rid, data, add_timestamp=True):
        if "last_sent_at" in data:
            db_state["last_sent_at"] = datetime.fromisoformat(data["last_sent_at"])
        return {}

    inner_call_count = 0

    async def _mock_send_digest_now_inner(g, label):
        nonlocal inner_call_count
        inner_call_count += 1
        # Simulate database update within the send flow
        g.last_sent_at = datetime.now(timezone.utc)
        await g.save()
        return True, "Sent successfully", 5

    # Stub the encrypt/decrypt routines to pass values through
    with patch("deeper_notebook.domain.gmail.repo_query", _mock_repo_query), \
         patch("deeper_notebook.domain.gmail.repo_upsert", _mock_repo_upsert), \
         patch("deeper_notebook.domain.gmail._dec", lambda x: x), \
         patch("deeper_notebook.domain.gmail._enc", lambda x: x), \
         patch("api.routers.gmail._send_digest_now_inner", _mock_send_digest_now_inner):

        # Prepare two initial integration references (mimicking concurrent callers)
        g_caller1 = await GmailIntegration.get()
        g_caller2 = await GmailIntegration.get()

        # Execute concurrently
        res1, res2 = await asyncio.gather(
            gmail_router._send_digest_now(g_caller1, label="daily"),
            gmail_router._send_digest_now(g_caller2, label="daily"),
        )

        # Assert only ONE send actually executed the inner logic
        assert inner_call_count == 1

        # One should have succeeded with actual sending, the other should have exited early
        results = [res1, res2]
        sent_result = next(r for r in results if r[1] == "Sent successfully")
        skipped_result = next(r for r in results if r[1] == "Already sent recently")

        assert sent_result == (True, "Sent successfully", 5)
        assert skipped_result == (True, "Already sent recently", 0)
