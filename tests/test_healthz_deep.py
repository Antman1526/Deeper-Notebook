"""v0.7.112 — tests for /healthz/deep deep healthcheck endpoint.

Verifies the endpoint reports per-subsystem status independently and
chooses the right overall status:
  - "healthy" when everything is up
  - "degraded" when optional subsystems are missing (embedding model,
    chat model, command registry)
  - "not_ready" → 503 when must-have subsystems fail (DB, migrations)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    # api.main imports trigger lifespan setup; build a TestClient and
    # let it manage startup/shutdown.
    from api.main import app
    return TestClient(app)


def _patch_all_healthy(monkeypatch):
    """Stub every subsystem to look healthy. Individual tests then
    selectively break one subsystem to assert the response."""
    async def _db_ok():
        return {"status": "online"}

    class _Mgr:
        async def needs_migration(self):
            return False

    async def _has_emb():
        return object()  # any truthy value

    async def _has_chat(_type):
        return object()

    from api.routers import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "check_database_health", _db_ok)
    from deeper_notebook.database import async_migrate
    monkeypatch.setattr(
        async_migrate, "AsyncMigrationManager", lambda: _Mgr(),
    )
    from deeper_notebook.ai.models import model_manager
    monkeypatch.setattr(
        model_manager, "get_embedding_model", _has_emb,
    )
    monkeypatch.setattr(
        model_manager, "get_default_model", _has_chat,
    )


def test_deep_healthy_when_all_subsystems_up(client, monkeypatch):
    _patch_all_healthy(monkeypatch)
    r = client.get("/healthz/deep")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "healthy"
    for name in (
        "database", "migrations", "embedding_model",
        "chat_model", "command_registry",
    ):
        assert body["checks"][name]["ok"] is True, body["checks"][name]


def test_deep_returns_503_when_database_offline(client, monkeypatch):
    _patch_all_healthy(monkeypatch)

    async def _db_off():
        return {"status": "offline", "error": "Connection refused"}

    from api.routers import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "check_database_health", _db_off)

    r = client.get("/healthz/deep")
    assert r.status_code == 503, r.text
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"]["ok"] is False
    assert "Connection refused" in body["checks"]["database"]["error"]


def test_deep_returns_503_when_migrations_pending(client, monkeypatch):
    _patch_all_healthy(monkeypatch)

    class _PendingMgr:
        async def needs_migration(self):
            return True

    from deeper_notebook.database import async_migrate
    monkeypatch.setattr(
        async_migrate, "AsyncMigrationManager", lambda: _PendingMgr(),
    )

    r = client.get("/healthz/deep")
    assert r.status_code == 503, r.text
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["migrations"]["status"] == "pending"


def test_deep_degraded_200_when_embedding_model_missing(client, monkeypatch):
    """v0.7.112 — missing embedding model is a degraded state, NOT
    not_ready. Chat-only deployments are valid (the user just doesn't
    get vector search)."""
    _patch_all_healthy(monkeypatch)

    async def _no_emb():
        return None

    from deeper_notebook.ai.models import model_manager
    monkeypatch.setattr(
        model_manager, "get_embedding_model", _no_emb,
    )

    r = client.get("/healthz/deep")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["embedding_model"]["ok"] is False
    assert "vector search" in body["checks"]["embedding_model"]["error"]
    # Must-have subsystems still report ok
    assert body["checks"]["database"]["ok"] is True
    assert body["checks"]["migrations"]["ok"] is True


def test_deep_degraded_when_chat_model_missing(client, monkeypatch):
    _patch_all_healthy(monkeypatch)

    async def _no_chat(_type):
        return None

    from deeper_notebook.ai.models import model_manager
    monkeypatch.setattr(
        model_manager, "get_default_model", _no_chat,
    )

    r = client.get("/healthz/deep")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["chat_model"]["ok"] is False
    # Error message names the actually-affected endpoints
    err = body["checks"]["chat_model"]["error"]
    assert "/chat" in err
    assert "/studio" in err


def test_deep_endpoint_is_exempt_from_auth(client, monkeypatch):
    """Monitoring tools polling /healthz/deep can't be expected to
    provide the DEEPER_NOTEBOOK_PASSWORD header. This test verifies the
    endpoint is in the middleware's excluded_paths list."""
    _patch_all_healthy(monkeypatch)
    # Even WITHOUT an Authorization header, the request must succeed.
    r = client.get("/healthz/deep", headers={})
    assert r.status_code in (200, 503)  # 200 healthy or 503 not_ready
    # NOT 401/403 — that'd mean middleware blocked it
    assert r.status_code != 401
    assert r.status_code != 403


def test_readyz_api_alias_returns_same_payload_and_is_auth_exempt(client, monkeypatch):
    """The desktop apiClient reaches readiness through the `/api` base URL."""
    _patch_all_healthy(monkeypatch)

    r_root = client.get("/readyz")
    r_api = client.get("/api/readyz", headers={})

    assert r_root.status_code == r_api.status_code == 200
    assert r_root.json() == r_api.json()
    assert r_api.status_code not in (401, 403)


def test_api_alias_returns_same_payload(client, monkeypatch):
    """v0.7.148 regression.

    Frontend's Setup Wizard hits `/api/healthz/deep` (not `/healthz/deep`)
    because the `apiClient` interceptor / Next.js rewrite chain ends up
    routing the request through `/api/*` regardless of `health.ts`'s
    `baseURL` override. Without this alias the wizard sees 404 and hangs
    on "Loading..." forever.

    The alias MUST be registered AND auth-exempt AND return the exact
    same payload shape as the root path.
    """
    _patch_all_healthy(monkeypatch)
    r_root = client.get("/healthz/deep")
    r_api = client.get("/api/healthz/deep")
    assert r_root.status_code == r_api.status_code == 200
    # Byte-for-byte payload equivalence: both must call the same handler.
    assert r_root.json() == r_api.json()
    # Auth-exempt: no header → must NOT be 401/403.
    r_no_auth = client.get("/api/healthz/deep", headers={})
    assert r_no_auth.status_code in (200, 503), r_no_auth.text
    assert r_no_auth.status_code != 401
    assert r_no_auth.status_code != 403


def test_api_alias_passes_probe_providers_query(client, monkeypatch):
    """The alias must forward `?probe_providers=true` to the same code
    path so monitoring tools that hit the aliased URL get the full
    response. Regression guard against the alias dropping query args.
    """
    _patch_all_healthy(monkeypatch)
    r_root = client.get("/healthz/deep?probe_providers=false")
    r_api = client.get("/api/healthz/deep?probe_providers=false")
    assert r_root.status_code == r_api.status_code
    # `upstream_providers` only appears when probe_providers=true; both
    # paths must agree on this behavior.
    assert ("upstream_providers" in r_root.json()["checks"]) == \
        ("upstream_providers" in r_api.json()["checks"])
