"""v0.8.68 — network-state service tests. No live network: the TCP probe is
injected. Each test resets the module cache via the public reset helper."""

from __future__ import annotations

import asyncio

import pytest

from deeper_notebook.health import network


@pytest.fixture(autouse=True)
def _reset_state():
    network.reset_network_state_for_tests()
    yield
    network.reset_network_state_for_tests()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_online_when_probe_succeeds(monkeypatch):
    monkeypatch.setattr(network, "_probe_once", lambda: True)
    state = _run(network.get_network_state(forced_offline_lookup=lambda: False))
    assert state.status == "online"
    assert state.forced_offline is False


def test_offline_when_probe_fails(monkeypatch):
    monkeypatch.setattr(network, "_probe_once", lambda: False)
    state = _run(network.get_network_state(forced_offline_lookup=lambda: False))
    assert state.status == "offline"


def test_unknown_on_probe_exception(monkeypatch):
    def _boom():
        raise OSError("probe broke")

    monkeypatch.setattr(network, "_probe_once", _boom)
    state = _run(network.get_network_state(forced_offline_lookup=lambda: False))
    assert state.status == "unknown"


def test_cache_hit_skips_probe(monkeypatch):
    calls = []
    monkeypatch.setattr(network, "_probe_once", lambda: calls.append(1) or True)

    async def scenario():
        await network.get_network_state(forced_offline_lookup=lambda: False)
        await network.get_network_state(forced_offline_lookup=lambda: False)

    _run(scenario())
    assert len(calls) == 1  # second call served from TTL cache


def test_report_failure_flips_state_immediately(monkeypatch):
    monkeypatch.setattr(network, "_probe_once", lambda: True)

    async def scenario():
        first = await network.get_network_state(forced_offline_lookup=lambda: False)
        assert first.status == "online"
        network.report_network_failure()
        second = await network.get_network_state(forced_offline_lookup=lambda: False)
        return second

    state = _run(scenario())
    assert state.status == "offline"
    assert state.source == "call-failure"


def test_report_success_flips_back(monkeypatch):
    monkeypatch.setattr(network, "_probe_once", lambda: False)

    async def scenario():
        await network.get_network_state(forced_offline_lookup=lambda: False)
        network.report_network_success()
        return await network.get_network_state(forced_offline_lookup=lambda: False)

    assert _run(scenario()).status == "online"


def test_forced_offline_wins_without_probe(monkeypatch):
    calls = []
    monkeypatch.setattr(network, "_probe_once", lambda: calls.append(1) or True)
    state = _run(network.get_network_state(forced_offline_lookup=lambda: True))
    assert state.status == "offline"
    assert state.forced_offline is True
    assert calls == []  # probe never ran


def test_probe_host_env_parsing(monkeypatch):
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_NET_PROBE_HOSTS", "example.com:443, 10.0.0.1:8443"
    )
    assert network._probe_targets() == [("example.com", 443), ("10.0.0.1", 8443)]


def test_probe_host_env_malformed_falls_back(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_NET_PROBE_HOSTS", "garbage,:,nohost:notaport")
    assert network._probe_targets() == network._DEFAULT_PROBE_TARGETS
