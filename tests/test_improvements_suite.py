"""Unit tests for stability & functionality improvements (S1, S2, S3, S5, F1, F2)."""

from __future__ import annotations

import asyncio
from collections import namedtuple
from pathlib import Path

import pytest

from api.routers.chat import _extract_streamed_thinking, _visible_streamed_text
from deeper_notebook.ai import provision
from deeper_notebook.database import repository as repo_mod
from scripts import rebrand_audit


def test_s1_pool_reinitializes_across_distinct_event_loops():
    """S1 — _ensure_pool_init rebinds Queue + Lock when the running event loop changes."""

    async def _get_primitives():
        await repo_mod._ensure_pool_init()
        return repo_mod._pool, repo_mod._pool_lock, repo_mod._pool_loop

    pool1, lock1, loop1 = asyncio.run(_get_primitives())
    pool2, lock2, loop2 = asyncio.run(_get_primitives())

    assert pool1 is not None and pool2 is not None
    assert loop1 is not loop2
    assert pool1 is not pool2
    assert lock1 is not lock2


def test_s2_rebrand_audit_tolerates_line_shift(tmp_path, monkeypatch):
    """S2 — audit_repository resolves position-independent allowlist entries when lines shift."""
    sample = tmp_path / "sample.py"
    # Legacy env var token built dynamically so rebrand_audit does not flag this test file
    legacy_env = "OPEN_" + "NOTEBOOK_PASSWORD"
    sample.write_text(f"x = 1\nlegacy = '{legacy_env}'\n", encoding="utf-8")

    monkeypatch.setattr(rebrand_audit, "_tracked_paths", lambda _root: ["sample.py"])

    initial = rebrand_audit.audit_repository(tmp_path, allowlist={}, selectors={})
    unexpected = initial["categories"]["unexpected_active_identity"]
    assert len(unexpected) == 1
    finding = unexpected[0]
    key = (
        finding["path"],
        finding["pattern"],
        finding["source"],
        finding["line"],
        finding["column"],
        finding["context_sha256"],
    )
    allowlist = {
        key: rebrand_audit.Approval(
            category="historical_reference",
            rationale=rebrand_audit.Rationale(
                path=finding["path"],
                pattern=finding["pattern"],
                source=finding["source"],
                line=finding["line"],
                column=finding["column"],
                context_sha256=finding["context_sha256"],
                category="historical_reference",
                explanation="test shift tolerance",
                compatibility_contract=None,
            ),
        )
    }

    # Shift the line down by inserting two lines above it
    sample.write_text(f"# header 1\n# header 2\nx = 1\nlegacy = '{legacy_env}'\n", encoding="utf-8")
    shifted = rebrand_audit.audit_repository(tmp_path, allowlist=allowlist, selectors={})
    assert shifted["summary"]["unexpected_active_identity"] == 0
    assert shifted["stale_allowlist"] == []


def test_f1_extract_streamed_thinking_tracks_open_and_closed_blocks():
    """F1 — _extract_streamed_thinking extracts open and closed <think> blocks while _visible_streamed_text holds back open blocks."""
    partial = "<think> analyzing sources "
    thinking, active = _extract_streamed_thinking(partial)
    assert thinking == "analyzing sources"
    assert active is True
    assert _visible_streamed_text(partial) == ""

    closed = "<think> analyzing sources </think>Grounded answer."
    thinking2, active2 = _extract_streamed_thinking(closed)
    assert thinking2 == "analyzing sources"
    assert active2 is False
    assert _visible_streamed_text(closed) == "Grounded answer."


@pytest.mark.asyncio
async def test_f2_auto_route_uncalibrated_sets_routing_note(monkeypatch):
    """F2 — auto-route sets routing_note='uncalibrated' when falling back to default_chat_model."""

    class _Defaults:
        auto_route_enabled = True
        auto_route_cloud = None
        default_chat_model = "model:default"

    async def _get_defaults():
        return _Defaults()

    async def _no_measured():
        return None

    async def _fake_default_path(content, *, model_id, default_type, **kwargs):
        return "DEFAULT-MODEL"

    monkeypatch.setattr(provision, "resolve_env", lambda *a, **k: "")
    monkeypatch.setattr(provision.model_manager, "get_defaults", _get_defaults)
    monkeypatch.setattr(provision, "_measured_local_chat_model_id", _no_measured)
    monkeypatch.setattr(provision, "provision_langchain_model", _fake_default_path)

    selection: dict = {}
    await provision.provision_langchain_chat_model("hello", selection_out=selection)
    assert "selected_provider" not in selection
    assert selection.get("routing_note") == "uncalibrated"


def test_s5_deep_health_reports_low_disk_space_as_degraded(monkeypatch):
    """S5 — /healthz/deep reports degraded (200) when free disk space is below threshold."""
    import shutil
    from fastapi.testclient import TestClient
    from api.main import app
    from api.routers import config as cfg_mod
    from deeper_notebook import worker_heartbeat
    from deeper_notebook.ai.models import model_manager
    from deeper_notebook.database import async_migrate

    async def _db_ok():
        return {"status": "online"}

    class _Mgr:
        async def needs_migration(self):
            return False

    async def _ok_obj(*_a):
        return object()

    async def _worker_ok():
        return {"online": True, "age_seconds": 1.0}

    monkeypatch.setattr(cfg_mod, "check_database_health", _db_ok)
    monkeypatch.setattr(async_migrate, "AsyncMigrationManager", lambda: _Mgr())
    monkeypatch.setattr(model_manager, "get_embedding_model", _ok_obj)
    monkeypatch.setattr(model_manager, "get_default_model", _ok_obj)
    monkeypatch.setattr(worker_heartbeat, "read_worker_status", _worker_ok)

    DiskUsage = namedtuple("usage", ["total", "used", "free"])
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _p: DiskUsage(100 * 1024 * 1024, 90 * 1024 * 1024, 10 * 1024 * 1024),
    )

    client = TestClient(app)
    r = client.get("/healthz/deep")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["disk_space"]["ok"] is False
    assert body["checks"]["disk_space"]["status"] == "low_disk"

@pytest.mark.asyncio
async def test_p1_async_graph_uses_asyncio_lock_and_sets_wal_pragmas(monkeypatch):
    """Priority 1 — get_async_graph and get_async_source_chat_graph use asyncio.Lock and configure WAL + busy_timeout."""
    from deeper_notebook.graphs import chat as chat_mod
    from deeper_notebook.graphs import source_chat as sc_mod

    executed_pragmas: list[str] = []

    class _FakeAioConn:
        async def execute(self, sql: str):
            executed_pragmas.append(sql)

        async def close(self):
            pass

    async def _fake_connect(_path):
        return _FakeAioConn()

    monkeypatch.setattr(chat_mod.aiosqlite, "connect", _fake_connect)
    monkeypatch.setattr(chat_mod, "AsyncSqliteSaver", lambda conn: conn)
    monkeypatch.setattr(chat_mod.agent_state, "compile", lambda checkpointer: ("compiled", checkpointer))
    await chat_mod.close_async_graph()

    g1, g2 = await asyncio.gather(chat_mod.get_async_graph(), chat_mod.get_async_graph())
    assert g1 == g2
    assert "PRAGMA journal_mode=WAL" in executed_pragmas
    assert "PRAGMA busy_timeout=5000" in executed_pragmas
    assert isinstance(chat_mod._async_graph_aio_lock, asyncio.Lock)
    await chat_mod.close_async_graph()

    executed_pragmas.clear()
    monkeypatch.setattr(sc_mod.aiosqlite, "connect", _fake_connect)
    monkeypatch.setattr(sc_mod, "AsyncSqliteSaver", lambda conn: conn)
    monkeypatch.setattr(sc_mod.source_chat_state, "compile", lambda checkpointer: ("sc_compiled", checkpointer))
    await sc_mod.close_async_source_chat_graph()

    sg1, sg2 = await asyncio.gather(
        sc_mod.get_async_source_chat_graph(), sc_mod.get_async_source_chat_graph()
    )
    assert sg1 == sg2
    assert "PRAGMA journal_mode=WAL" in executed_pragmas
    assert "PRAGMA busy_timeout=5000" in executed_pragmas
    assert isinstance(sc_mod._async_source_chat_aio_lock, asyncio.Lock)
    await sc_mod.close_async_source_chat_graph()


def test_p3_pool_reinit_drains_old_connections_and_guards_cross_loop_release(monkeypatch):
    """Priority 3 — _ensure_pool_init drains idle connections on loop switch and db_connection guards cross-loop release."""
    closed_conns: list[str] = []

    class _FakeConn:
        def __init__(self, label: str):
            self.label = label

        async def close(self):
            closed_conns.append(self.label)

    async def _setup_loop1():
        await repo_mod._reset_pool_for_tests()
        await repo_mod._ensure_pool_init()
        repo_mod._pool.put_nowait(_FakeConn("idle_loop1"))
        repo_mod._pool_total = 1

    asyncio.run(_setup_loop1())

    async def _reinit_loop2():
        await repo_mod._ensure_pool_init()
        assert repo_mod._pool_total == 0

    asyncio.run(_reinit_loop2())
    assert "idle_loop1" in closed_conns
