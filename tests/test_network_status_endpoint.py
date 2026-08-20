"""v0.8.68 — /api/system/network-status: never 500s, reports gate state."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import system as system_router
from deeper_notebook.health import network
from deeper_notebook.health.network import NetworkState


@pytest.fixture(autouse=True)
def _reset():
    network.reset_network_state_for_tests()
    yield
    network.reset_network_state_for_tests()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(system_router.router)
    return TestClient(app)


def test_online_payload(client, monkeypatch):
    async def _fake():
        return NetworkState(
            status="online", forced_offline=False, checked_at=1.0, source="probe"
        )

    monkeypatch.setattr(system_router, "get_network_state_with_settings", _fake)
    body = client.get("/api/system/network-status").json()
    assert body["status"] == "online"
    assert body["forced_offline"] is False


def test_offline_includes_fallback_model(client, monkeypatch):
    async def _fake():
        return NetworkState(
            status="offline",
            forced_offline=False,
            checked_at=1.0,
            source="call-failure",
        )

    class _Rec:
        name = "gemma-4-E4B"

    async def _fake_find():
        return _Rec()

    monkeypatch.setattr(system_router, "get_network_state_with_settings", _fake)
    monkeypatch.setattr(system_router, "find_local_language_model", _fake_find)
    body = client.get("/api/system/network-status").json()
    assert body["status"] == "offline"
    assert body["local_fallback_model"] == "gemma-4-E4B"


def test_internal_error_returns_unknown_not_500(client, monkeypatch):
    async def _boom():
        raise RuntimeError("probe machinery exploded")

    monkeypatch.setattr(system_router, "get_network_state_with_settings", _boom)
    r = client.get("/api/system/network-status")
    assert r.status_code == 200
    assert r.json()["status"] == "unknown"
