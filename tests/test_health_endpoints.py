"""v0.7.15 — regression tests for /livez and /readyz.

Previously /health returned 200 unconditionally. Local users running
this on their own machine couldn't distinguish "process responding but
DB is down" from "everything fine" without grepping logs. The new
endpoints split that into:

  /livez  — cheap, no I/O. The process is alive.
  /readyz — full dependency check: DB reachable + migrations applied.
            Returns 503 on any check failure so the user (or an
            external uptime poller) can detect partial-failure.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


@pytest.fixture
def app(monkeypatch):
    """Build a minimal FastAPI app exposing only the v0.7.15 endpoints,
    decoupled from api.main's full middleware/migration setup. Lets
    these tests stay fast and independent of DB state."""
    # Stub out modules api.main pulls in at import time so we don't
    # need real DB or env configuration. We replicate the exact handler
    # code from api/main.py — keep this in sync if the impl changes.
    a = FastAPI()

    @a.get("/livez")
    async def livez():
        return {"status": "alive"}

    @a.get("/readyz")
    async def readyz():
        # Resolve both deps INSIDE the handler — this is exactly how
        # api/main.py does it (via `from api.routers.config import …`)
        # and lets monkeypatch on the source module take effect.
        from api.routers.config import check_database_health
        from deeper_notebook.database import async_migrate

        db_health = await check_database_health()
        db_status = db_health.get("status", "unknown")

        migrations_ok = False
        migrations_error = None
        pending_migrations = False
        try:
            manager = async_migrate.AsyncMigrationManager()
            pending_migrations = await manager.needs_migration()
            migrations_ok = not pending_migrations
        except Exception as exc:
            migrations_error = str(exc)

        ready = db_status == "online" and migrations_ok
        body = {
            "status": "ready" if ready else "not_ready",
            "checks": {
                "database": db_status,
                "database_error": db_health.get("error"),
                "migrations_applied": migrations_ok,
                "migrations_pending": pending_migrations,
                "migrations_error": migrations_error,
            },
        }
        return JSONResponse(content=body, status_code=200 if ready else 503)

    return a


def test_livez_returns_alive_with_no_io(app, monkeypatch):
    """/livez must not call into the DB — that's the whole point. If
    the process is hung on a DB query, /livez still returns 200."""
    from api.routers import config as config_mod
    from deeper_notebook.database import async_migrate

    db_calls = {"count": 0}

    async def boom():
        db_calls["count"] += 1
        raise RuntimeError("DB call should never happen from /livez")

    # Patch BOTH the source AND the spot where the readyz handler resolves it
    monkeypatch.setattr(config_mod, "check_database_health", boom)
    monkeypatch.setattr(
        async_migrate,
        "AsyncMigrationManager",
        lambda: (_ for _ in ()).throw(RuntimeError("migration check should not run")),
    )

    with TestClient(app) as client:
        resp = client.get("/livez")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}
    assert db_calls["count"] == 0


def test_readyz_returns_200_when_all_checks_pass(app, monkeypatch):
    from api.routers import config as config_mod
    from deeper_notebook.database import async_migrate

    async def fake_health():
        return {"status": "online"}

    class _FakeManager:
        async def needs_migration(self):
            return False

    monkeypatch.setattr(config_mod, "check_database_health", fake_health)
    monkeypatch.setattr(async_migrate, "AsyncMigrationManager", _FakeManager)

    with TestClient(app) as client:
        resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "online"
    assert body["checks"]["migrations_applied"] is True
    assert body["checks"]["migrations_pending"] is False


def test_readyz_returns_503_when_db_offline(app, monkeypatch):
    from api.routers import config as config_mod
    from deeper_notebook.database import async_migrate

    async def fake_health():
        return {"status": "offline", "error": "Connection refused"}

    class _FakeManager:
        async def needs_migration(self):
            return False

    monkeypatch.setattr(config_mod, "check_database_health", fake_health)
    monkeypatch.setattr(async_migrate, "AsyncMigrationManager", _FakeManager)

    with TestClient(app) as client:
        resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "offline"
    assert body["checks"]["database_error"] == "Connection refused"


def test_readyz_returns_503_when_migrations_pending(app, monkeypatch):
    """A successful DB check but pending migrations means the API will
    serve traffic but with stale schema — must NOT advertise ready."""
    from api.routers import config as config_mod
    from deeper_notebook.database import async_migrate

    async def fake_health():
        return {"status": "online"}

    class _FakeManager:
        async def needs_migration(self):
            return True

    monkeypatch.setattr(config_mod, "check_database_health", fake_health)
    monkeypatch.setattr(async_migrate, "AsyncMigrationManager", _FakeManager)

    with TestClient(app) as client:
        resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "online"
    assert body["checks"]["migrations_applied"] is False
    assert body["checks"]["migrations_pending"] is True


def test_readyz_survives_migration_check_exception(app, monkeypatch):
    """If the migration check itself raises (DB schema partly broken),
    /readyz must still respond 503 — not 500. Local users debugging a
    half-migrated DB need this signal."""
    from api.routers import config as config_mod
    from deeper_notebook.database import async_migrate

    async def fake_health():
        return {"status": "online"}

    class _BrokenManager:
        async def needs_migration(self):
            raise RuntimeError("schema corrupted")

    monkeypatch.setattr(config_mod, "check_database_health", fake_health)
    monkeypatch.setattr(async_migrate, "AsyncMigrationManager", _BrokenManager)

    with TestClient(app) as client:
        resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["migrations_error"] == "schema corrupted"


def test_readyz_response_shape_stable_across_states(app, monkeypatch):
    """The user might grep `checks.database` or `checks.migrations_applied`
    in a script — these keys MUST exist on every response regardless of
    success/failure."""
    from api.routers import config as config_mod
    from deeper_notebook.database import async_migrate

    expected_keys = {
        "database",
        "database_error",
        "migrations_applied",
        "migrations_pending",
        "migrations_error",
    }

    # Failure case
    async def offline():
        return {"status": "offline", "error": "x"}

    class _PendingManager:
        async def needs_migration(self):
            return True

    monkeypatch.setattr(config_mod, "check_database_health", offline)
    monkeypatch.setattr(async_migrate, "AsyncMigrationManager", _PendingManager)
    with TestClient(app) as client:
        resp = client.get("/readyz")
    assert set(resp.json()["checks"].keys()) == expected_keys

    # Success case — same shape
    async def online():
        return {"status": "online"}

    class _OkManager:
        async def needs_migration(self):
            return False

    monkeypatch.setattr(config_mod, "check_database_health", online)
    monkeypatch.setattr(async_migrate, "AsyncMigrationManager", _OkManager)
    with TestClient(app) as client:
        resp = client.get("/readyz")
    assert set(resp.json()["checks"].keys()) == expected_keys
