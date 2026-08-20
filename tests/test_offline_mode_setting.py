"""v0.8.68 — Offline-mode toggle: schema field, forced accessor caching."""

from __future__ import annotations

import asyncio

import pytest

from deeper_notebook.health import network


@pytest.fixture(autouse=True)
def _reset():
    network.reset_network_state_for_tests()
    yield
    network.reset_network_state_for_tests()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_content_settings_has_offline_mode_default_false():
    from deeper_notebook.domain.content_settings import ContentSettings

    assert ContentSettings.model_fields["offline_mode"].default is False


def test_settings_schemas_carry_offline_mode():
    from api.models import SettingsResponse, SettingsUpdate

    assert "offline_mode" in SettingsResponse.model_fields
    assert "offline_mode" in SettingsUpdate.model_fields


def test_settings_update_accepts_crawl4ai_engine():
    # v0.8.68 bug fix regression test: "crawl4ai" was valid on
    # ContentSettings (v0.8.67u) but rejected by the PUT request schema.
    from api.models import SettingsUpdate

    upd = SettingsUpdate(default_content_processing_engine_url="crawl4ai")
    assert upd.default_content_processing_engine_url == "crawl4ai"


def test_forced_offline_enabled_reads_settings(monkeypatch):
    class _FakeSettings:
        offline_mode = True

    async def _fake_get_instance():
        return _FakeSettings()

    from deeper_notebook.domain.content_settings import ContentSettings

    monkeypatch.setattr(ContentSettings, "get_instance", _fake_get_instance)
    assert _run(network.forced_offline_enabled()) is True


def test_forced_offline_db_error_defaults_false(monkeypatch):
    async def _boom():
        raise RuntimeError("db down")

    from deeper_notebook.domain.content_settings import ContentSettings

    monkeypatch.setattr(ContentSettings, "get_instance", _boom)
    assert _run(network.forced_offline_enabled()) is False


def test_forced_offline_cached_until_invalidated(monkeypatch):
    calls = []

    class _FakeSettings:
        offline_mode = False

    async def _fake_get_instance():
        calls.append(1)
        return _FakeSettings()

    from deeper_notebook.domain.content_settings import ContentSettings

    monkeypatch.setattr(ContentSettings, "get_instance", _fake_get_instance)

    async def scenario():
        await network.forced_offline_enabled()
        await network.forced_offline_enabled()  # cache hit
        network.invalidate_forced_offline_cache()
        await network.forced_offline_enabled()  # re-read

    _run(scenario())
    assert len(calls) == 2


def test_state_with_settings_forced(monkeypatch):
    class _FakeSettings:
        offline_mode = True

    async def _fake_get_instance():
        return _FakeSettings()

    from deeper_notebook.domain.content_settings import ContentSettings

    monkeypatch.setattr(ContentSettings, "get_instance", _fake_get_instance)
    state = _run(network.get_network_state_with_settings())
    assert state.status == "offline" and state.forced_offline is True
