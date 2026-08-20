"""v0.8.68 — podcast submit fails fast offline when profiles use cloud
models, instead of hanging the worker against an unreachable provider."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from api.podcast_service import PodcastService
from deeper_notebook.exceptions import ConfigurationError
from deeper_notebook.health import network
from deeper_notebook.health.network import NetworkState


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _reset():
    network.reset_network_state_for_tests()
    yield
    network.reset_network_state_for_tests()


def _profiles(
    *,
    tts_provider,
    outline_provider="openai_compatible",
    transcript_provider="openai_compatible",
):
    async def _tts():
        return (tts_provider, "voice-model", {})

    async def _outline():
        return (outline_provider, "outline-model", {})

    async def _transcript():
        return (transcript_provider, "transcript-model", {})

    speaker = SimpleNamespace(resolve_tts_config=_tts)
    episode = SimpleNamespace(
        resolve_outline_config=_outline,
        resolve_transcript_config=_transcript,
    )
    return episode, speaker


def _patch_state(monkeypatch, status, forced=False):
    async def _fake():
        return NetworkState(
            status=status, forced_offline=forced, checked_at=0.0, source="probe"
        )

    monkeypatch.setattr(network, "get_network_state_with_settings", _fake)


def test_offline_cloud_tts_raises_fast(monkeypatch):
    _patch_state(monkeypatch, "offline")
    episode, speaker = _profiles(tts_provider="elevenlabs")
    with pytest.raises(ConfigurationError) as exc:
        _run(PodcastService._gate_offline_cloud_models(episode, speaker))
    assert "elevenlabs" in str(exc.value)
    assert "offline" in str(exc.value).lower()


def test_forced_offline_names_the_toggle(monkeypatch):
    _patch_state(monkeypatch, "offline", forced=True)
    episode, speaker = _profiles(tts_provider="openai")
    with pytest.raises(ConfigurationError) as exc:
        _run(PodcastService._gate_offline_cloud_models(episode, speaker))
    assert "Offline mode" in str(exc.value)


def test_offline_all_local_passes(monkeypatch):
    _patch_state(monkeypatch, "offline")
    episode, speaker = _profiles(tts_provider="openai_compatible")
    _run(PodcastService._gate_offline_cloud_models(episode, speaker))  # no raise


def test_online_cloud_passes(monkeypatch):
    _patch_state(monkeypatch, "online")
    episode, speaker = _profiles(tts_provider="elevenlabs")
    _run(PodcastService._gate_offline_cloud_models(episode, speaker))  # no raise


def test_unresolvable_profile_fails_open(monkeypatch):
    _patch_state(monkeypatch, "offline")

    async def _boom():
        raise ValueError("no voice model configured")

    speaker = SimpleNamespace(resolve_tts_config=_boom)
    episode, _ = _profiles(tts_provider="openai_compatible")
    # Unresolvable → gate skips it; existing downstream error path applies.
    _run(PodcastService._gate_offline_cloud_models(episode, speaker))
