"""v0.8.6 Item D — API tests for GET/PUT /api/launcher-prefs.

Three test cases (hermetic — no live SurrealDB or real filesystem needed):
1. GET returns empty when the file does not exist.
2. PUT writes and GET reflects the new values.
3. PUT with None removes the key.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def prefs_dir(tmp_path, monkeypatch):
    """Redirect desktop.launcher_prefs to a temp directory."""
    prefs_path = tmp_path / ".open-notebook-plus" / "launcher.env"

    import desktop.launcher_prefs as lp
    monkeypatch.setattr(lp, "_prefs_path", lambda: prefs_path)
    return prefs_path


@pytest.fixture()
def api_app(monkeypatch):
    """Return a minimal FastAPI app with just the launcher-prefs router."""
    from fastapi import FastAPI

    from api.routers.launcher_prefs import router

    app = FastAPI()
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_returns_empty_when_no_file(prefs_dir, api_app):
    """Case 1: GET /api/launcher-prefs returns empty prefs dict when the
    launcher.env file doesn't exist yet."""
    assert not prefs_dir.exists()
    async with AsyncClient(
        transport=ASGITransport(app=api_app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/launcher-prefs")
    assert resp.status_code == 200
    assert resp.json() == {"prefs": {}}


@pytest.mark.asyncio
async def test_put_writes_and_get_reflects(prefs_dir, api_app):
    """Case 2: PUT with a whitelisted key, then GET must return it."""
    async with AsyncClient(
        transport=ASGITransport(app=api_app), base_url="http://test"
    ) as client:
        put_resp = await client.put(
            "/api/launcher-prefs",
            json={"prefs": {"DEEPER_NOTEBOOK_CHAT_LLM_CTX": "8192"}},
        )
        assert put_resp.status_code == 200
        assert (
            put_resp.json()["prefs"]["DEEPER_NOTEBOOK_CHAT_LLM_CTX"]
            == "8192"
        )

        get_resp = await client.get("/api/launcher-prefs")
    assert get_resp.status_code == 200
    assert (
        get_resp.json()["prefs"]["DEEPER_NOTEBOOK_CHAT_LLM_CTX"]
        == "8192"
    )


@pytest.mark.asyncio
async def test_put_with_none_removes_key(prefs_dir, api_app):
    """Case 3: PUT with null value removes the key from the file."""
    # Seed with two keys.
    prefs_dir.parent.mkdir(parents=True, exist_ok=True)
    prefs_dir.write_text("DEEPER_NOTEBOOK_CHAT_LLM_CTX=8192\nDEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX=32768\n")

    async with AsyncClient(
        transport=ASGITransport(app=api_app), base_url="http://test"
    ) as client:
        put_resp = await client.put(
            "/api/launcher-prefs",
            json={"prefs": {"DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX": None}},
        )
    assert put_resp.status_code == 200
    result = put_resp.json()["prefs"]
    assert "DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX" not in result
    assert result.get("DEEPER_NOTEBOOK_CHAT_LLM_CTX") == "8192"


@pytest.mark.asyncio
async def test_put_rejects_non_whitelisted_key(prefs_dir, api_app):
    """Reject a PUT that includes a key outside the whitelist."""
    async with AsyncClient(
        transport=ASGITransport(app=api_app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/api/launcher-prefs",
            json={"prefs": {"SECRET_API_KEY": "hunter2"}},
        )
    assert resp.status_code == 400
    assert "whitelist" in resp.json()["detail"].lower()
