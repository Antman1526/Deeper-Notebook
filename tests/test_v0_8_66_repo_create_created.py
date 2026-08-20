"""v0.8.66 (audit D-M1) — repo_create must preserve a caller-supplied `created`
timestamp instead of clobbering it with import-time. Normal creates (no
`created`) still get the auto-stamp.
"""

from __future__ import annotations

import datetime
from contextlib import asynccontextmanager

import pytest

from deeper_notebook.database import repository as repo


class _Conn:
    def __init__(self, captured):
        self._captured = captured

    async def insert(self, table, data):
        self._captured["data"] = dict(data)
        return {**data, "id": f"{table}:x"}


def _patch_conn(monkeypatch, captured):
    @asynccontextmanager
    async def _fake_conn():
        yield _Conn(captured)

    monkeypatch.setattr(repo, "db_connection", _fake_conn)


@pytest.mark.asyncio
async def test_repo_create_preserves_caller_created(monkeypatch):
    captured = {}
    _patch_conn(monkeypatch, captured)

    orig = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    await repo.repo_create("notebook", {"name": "x", "created": orig})

    assert captured["data"]["created"] == orig, (
        "repo_create clobbered the caller's `created` — reimport/restore would "
        "lose the original timestamp."
    )
    # `updated` is always stamped fresh.
    assert captured["data"]["updated"] != orig


@pytest.mark.asyncio
async def test_repo_create_autostamps_created_when_absent(monkeypatch):
    captured = {}
    _patch_conn(monkeypatch, captured)

    await repo.repo_create("notebook", {"name": "x"})
    assert "created" in captured["data"]
    assert isinstance(captured["data"]["created"], datetime.datetime)
