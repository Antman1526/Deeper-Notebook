"""v0.8.66 — regression tests for the MCP-registry hardening (audit H2/H3/H4)
and the repo_update parameterization (defense-in-depth for H2).

H2 — PATCH /api/mcp/{id} interpolated the raw id into `UPDATE {id} MERGE $data`,
     allowing `mcp_server:x; DELETE notebook; --` to compose a second statement.
H3 — DELETE and /test bound a plain string to `id = $id`; a RecordID never
     equals a string, so DELETE was a silent no-op and Test 404'd real servers.
H4 — POST /api/mcp stored an arbitrary URL with no SSRF validation; it is later
     fetched outbound by /test and the chat tool loop.
"""

from __future__ import annotations

import pytest
from surrealdb import RecordID


# ---------------------------------------------------------------------------
# H2 — repo_update must parameterize the record id (no raw interpolation)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_repo_update_binds_record_id_as_param(monkeypatch):
    import deeper_notebook.database.repository as repo

    captured = {}

    async def _fake_repo_query(query, vars=None):
        captured["query"] = query
        captured["vars"] = vars
        return []

    monkeypatch.setattr(repo, "repo_query", _fake_repo_query)

    # A hostile id that previously composed a second SurrealQL statement.
    await repo.repo_update(
        "mcp_server", "mcp_server:x; DELETE notebook; --", {"enabled": True}
    )

    # The id is NEVER interpolated into the query body — it is bound as $rid.
    assert captured["query"] == "UPDATE $rid MERGE $data;", captured["query"]
    assert "DELETE notebook" not in captured["query"]
    rid = captured["vars"]["rid"]
    assert isinstance(rid, RecordID), f"expected RecordID, got {type(rid)}"
    # RecordID keeps the junk as an opaque id value (angle-escaped), so it can
    # never break out of the value position.
    assert rid.table_name == "mcp_server"


# ---------------------------------------------------------------------------
# H2 — the PATCH endpoint hands repo_update a RecordID, and rejects junk ids
# ---------------------------------------------------------------------------
def test_patch_endpoint_passes_record_id(monkeypatch):
    from fastapi.testclient import TestClient

    import deeper_notebook.database.repository as repo
    from api.main import app

    seen = {}

    async def _fake_repo_update(table, id_, data):
        seen["id"] = id_
        return [{"id": "mcp_server:p1", "priority": 5}]

    monkeypatch.setattr(repo, "repo_update", _fake_repo_update)
    client = TestClient(app)

    r = client.patch("/api/mcp/mcp_server:p1", json={"priority": 5})
    assert r.status_code == 200, r.text
    assert isinstance(seen["id"], RecordID), (
        "router must coerce the path id to a RecordID before repo_update"
    )


def test_patch_endpoint_rejects_malformed_id(monkeypatch):
    from fastapi.testclient import TestClient

    import deeper_notebook.database.repository as repo
    from api.main import app

    async def _should_not_run(*a, **k):  # pragma: no cover
        raise AssertionError("repo_update must not be reached for a bad id")

    monkeypatch.setattr(repo, "repo_update", _should_not_run)
    client = TestClient(app)
    # No colon → RecordID.parse raises → clean 400, never touches the DB.
    r = client.patch("/api/mcp/not-a-valid-id", json={"enabled": True})
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# H3 — DELETE and /test bind a RecordID, not a string
# ---------------------------------------------------------------------------
def test_delete_binds_record_id(monkeypatch):
    from fastapi.testclient import TestClient

    import deeper_notebook.database.repository as repo
    from api.main import app

    seen = {}

    async def _fake_repo_query(query, vars=None):
        seen["query"] = query
        seen["vars"] = vars or {}
        return []

    monkeypatch.setattr(repo, "repo_query", _fake_repo_query)
    client = TestClient(app)

    r = client.delete("/api/mcp/mcp_server:abc123")
    assert r.status_code == 200, r.text
    assert isinstance(seen["vars"].get("id"), RecordID), (
        "DELETE must bind a RecordID — a string never equals the id column, so "
        "the delete would be a silent no-op."
    )


def test_test_endpoint_binds_record_id(monkeypatch):
    from fastapi.testclient import TestClient

    import deeper_notebook.database.repository as repo
    from api.main import app

    seen = {}

    async def _fake_repo_query(query, vars=None):
        seen["vars"] = vars or {}
        return []  # simulate "no row" → 404 (but we assert the bind first)

    monkeypatch.setattr(repo, "repo_query", _fake_repo_query)
    client = TestClient(app)

    r = client.post("/api/mcp/mcp_server:abc123/test")
    # Row not found here, but the important assertion is the bound type.
    assert isinstance(seen["vars"].get("id"), RecordID)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# H4 — POST /api/mcp validates the URL (SSRF). Link-local is blocked; loopback
#       is allowed (self-hosted MCP servers must keep working).
# ---------------------------------------------------------------------------
def test_create_rejects_link_local_url(monkeypatch):
    from fastapi.testclient import TestClient

    import deeper_notebook.database.repository as repo
    from api.main import app

    async def _should_not_create(*a, **k):  # pragma: no cover
        raise AssertionError("repo_create must not run for an SSRF URL")

    monkeypatch.setattr(repo, "repo_create", _should_not_create)
    client = TestClient(app)

    r = client.post(
        "/api/mcp",
        json={
            "name": "evil",
            "url": "http://169.254.169.254/latest/meta-data/",
            "enabled": True,
        },
    )
    assert r.status_code == 400, r.text
    assert "link-local" in r.json()["detail"].lower()


def test_create_allows_loopback_url(monkeypatch):
    from fastapi.testclient import TestClient

    import deeper_notebook.database.repository as repo
    from api.main import app

    async def _fake_create(table, data):
        return {**data, "id": "mcp_server:ok"}

    monkeypatch.setattr(repo, "repo_create", _fake_create)
    client = TestClient(app)

    r = client.post(
        "/api/mcp",
        json={"name": "local", "url": "http://127.0.0.1:8742/mcp", "enabled": True},
    )
    assert r.status_code == 201, r.text
