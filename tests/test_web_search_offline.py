"""v0.8.68 — run_web_search returns empty immediately when offline (no 25s
provider budget burn, no HTTP attempts)."""

from __future__ import annotations

import asyncio

import pytest

from deeper_notebook.health import network
from deeper_notebook.health.network import NetworkState
from deeper_notebook.tools import web_search as ws


@pytest.fixture(autouse=True)
def _reset():
    network.reset_network_state_for_tests()
    yield
    network.reset_network_state_for_tests()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_offline_short_circuits(monkeypatch):
    # Configure a provider so the chain is non-empty (conftest strips these).
    monkeypatch.setenv("SERPER_API_KEY", "test-key")

    async def _offline():
        return NetworkState(
            status="offline", forced_offline=False, checked_at=0.0, source="probe"
        )

    monkeypatch.setattr(network, "get_network_state_with_settings", _offline)

    attempts = []

    async def _no_attempt(*args, **kwargs):
        attempts.append(1)
        return []

    monkeypatch.setattr(ws, "_do_attempt", _no_attempt)

    assert _run(ws.run_web_search("test query")) == []
    assert attempts == []  # never reached a provider


def test_online_still_walks_the_chain(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-key")

    async def _online():
        return NetworkState(
            status="online", forced_offline=False, checked_at=0.0, source="probe"
        )

    monkeypatch.setattr(network, "get_network_state_with_settings", _online)

    async def _fake_attempt(client, provider, target, query, n, timeout):
        return [{"title": "t", "url": "https://x", "snippet": "s"}]

    monkeypatch.setattr(ws, "_do_attempt", _fake_attempt)

    results = _run(ws.run_web_search("test query"))
    assert results and results[0]["url"] == "https://x"
