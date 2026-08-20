"""v0.8.66 (audit follow-up) — Gmail persistence id-form regression.

Two pre-existing bugs (found by validating repo_update against a live SurrealDB,
then validating the gmail round-trip) made Gmail settings/tokens never persist
to the row get() reads:
  * get() bound SINGLETON_ID as a STRING in `SELECT * FROM ONLY $rid` →
    SurrealDB treats a bound string as a string value, returning [] every time.
  * save() passed the BARE id "singleton" to repo_upsert → `UPSERT singleton`
    parsed it as a TABLE, writing a new orphan `singleton:<random>` row.

Both are the same ensure_record_id-missing / bare-id class as the H3 MCP fix.
These tests pin the corrected id-form at the (mocked) repo boundary so it can't
regress without standing up a live DB.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from surrealdb import RecordID

from deeper_notebook.domain import gmail as gmail_mod
from deeper_notebook.domain.gmail import SINGLETON_ID, GmailIntegration


@pytest.mark.asyncio
async def test_get_binds_recordid_not_string():
    gmail_mod._invalidate_cache()
    captured = {}

    async def _fake_query(sql, vars=None):
        captured["vars"] = vars or {}
        return [{"email_address": "u@x.com", "enabled": True}]

    with patch.object(gmail_mod, "repo_query", AsyncMock(side_effect=_fake_query)):
        await GmailIntegration.get()

    rid = captured["vars"].get("rid")
    assert isinstance(rid, RecordID), (
        f"get() must bind a RecordID (a bound STRING makes FROM ONLY $rid "
        f"return [] on SurrealDB 2.x); got {type(rid)}"
    )
    assert str(rid) == SINGLETON_ID
    gmail_mod._invalidate_cache()


@pytest.mark.asyncio
async def test_save_passes_full_record_id_not_bare():
    g = GmailIntegration()
    g.email_address = "u@x.com"
    captured = {}

    async def _fake_upsert(table, id_, data, add_timestamp=False):
        captured["table"] = table
        captured["id"] = id_
        return [{}]

    with patch.object(gmail_mod, "repo_upsert", AsyncMock(side_effect=_fake_upsert)):
        await g.save()

    assert captured["id"] == SINGLETON_ID, (
        f"save() must pass the FULL record id {SINGLETON_ID!r}; a bare 'singleton' "
        f"makes `UPSERT singleton` write to a TABLE, not the singleton row. "
        f"Got {captured['id']!r}"
    )
