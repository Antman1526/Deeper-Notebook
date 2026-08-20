"""v0.8.66 (audit C2) — regression tests for Gmail credential clearing.

The bug: `GmailIntegration.save()` filtered out every None value before
calling `repo_upsert`, which issues `UPSERT … MERGE $data`. SurrealDB's MERGE
only overwrites keys PRESENT in the payload and silently preserves omitted
keys, so `disconnect()` / `forget_credentials()` — which set the token and
client-credential fields to None and then call save() — were DB-level no-ops:
the old encrypted refresh_token survived, leaving the account effectively
connected and "forgotten" credentials still on disk.

The fix force-writes the six credential/token keys even when None, so MERGE
nulls them. These tests assert the exact payload handed to repo_upsert.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from deeper_notebook.domain import gmail as gmail_mod
from deeper_notebook.domain.gmail import GmailIntegration

# The six keys that represent the clearable credential/token surface. If a
# disconnect/forget can't null these, the account stays connected.
_CREDENTIAL_KEYS = {
    "client_id_enc",
    "client_secret_enc",
    "access_token_enc",
    "refresh_token_enc",
    "token_expires_at",
    "email_address",
}


@pytest.mark.asyncio
async def test_disconnect_save_force_writes_null_credential_keys():
    """After clearing tokens (the disconnect path), save() MUST include every
    credential/token key in the MERGE payload with a None value, so SurrealDB
    actually nulls them instead of preserving the stale ciphertext."""
    g = GmailIntegration()  # fresh — all credential/token fields default None
    g.access_token = None
    g.refresh_token = None
    g.token_expires_at = None
    g.email_address = None
    g.enabled = False

    captured = {}

    async def _fake_upsert(table, _id, data, add_timestamp=False):
        captured["table"] = table
        captured["data"] = dict(data)
        return [{}]

    with patch.object(gmail_mod, "repo_upsert", AsyncMock(side_effect=_fake_upsert)):
        await g.save()

    data = captured["data"]
    # Every credential key is present (force-written) and explicitly None.
    for key in _CREDENTIAL_KEYS:
        assert key in data, (
            f"{key} missing from MERGE payload → SurrealDB would PRESERVE the "
            f"stale value and the disconnect would be a no-op."
        )
        assert data[key] is None, f"{key} should be None on a disconnect save"


@pytest.mark.asyncio
async def test_connected_save_writes_encrypted_credentials():
    """The happy path still works: when tokens are present they are encrypted
    and written. (Patch _enc to a passthrough so the test needs no real key.)"""
    g = GmailIntegration()
    g.client_id = "client-abc"
    g.client_secret = "secret-xyz"
    g.access_token = "at-123"
    g.refresh_token = "rt-456"
    g.email_address = "alice@example.com"
    g.enabled = True

    captured = {}

    async def _fake_upsert(table, _id, data, add_timestamp=False):
        captured["data"] = dict(data)
        return [{}]

    def _fake_enc(v):
        return f"enc({v})" if v else None

    with (
        patch.object(gmail_mod, "repo_upsert", AsyncMock(side_effect=_fake_upsert)),
        patch.object(gmail_mod, "_enc", _fake_enc),
    ):
        await g.save()

    data = captured["data"]
    assert data["refresh_token_enc"] == "enc(rt-456)"
    assert data["access_token_enc"] == "enc(at-123)"
    assert data["client_id_enc"] == "enc(client-abc)"
    assert data["email_address"] == "alice@example.com"
    # Config fields ride along.
    assert data["enabled"] is True


@pytest.mark.asyncio
async def test_non_credential_none_fields_are_still_dropped():
    """`last_sent_at` is NOT in the force-write set; when None it should still
    be omitted so a partial save can't wipe a previously-recorded send time."""
    g = GmailIntegration()
    g.last_sent_at = None

    captured = {}

    async def _fake_upsert(table, _id, data, add_timestamp=False):
        captured["data"] = dict(data)
        return [{}]

    with patch.object(gmail_mod, "repo_upsert", AsyncMock(side_effect=_fake_upsert)):
        await g.save()

    assert "last_sent_at" not in captured["data"], (
        "last_sent_at is None and not a credential key → must be omitted so "
        "MERGE preserves any prior value."
    )
