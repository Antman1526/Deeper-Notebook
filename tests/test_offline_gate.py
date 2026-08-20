"""v0.8.68 — offline gate: cloud language models substitute local offline."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from deeper_notebook.ai import offline_gate
from deeper_notebook.exceptions import ConfigurationError
from deeper_notebook.health import network
from deeper_notebook.health.network import NetworkState


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _state(status):
    return NetworkState(
        status=status, forced_offline=False, checked_at=0.0, source="probe"
    )


def _model(id, provider, type="language", name="m"):
    return SimpleNamespace(id=id, provider=provider, type=type, name=name)


@pytest.fixture(autouse=True)
def _reset():
    network.reset_network_state_for_tests()
    yield
    network.reset_network_state_for_tests()


def _patch_state(monkeypatch, status):
    async def _fake():
        return _state(status)

    monkeypatch.setattr(offline_gate, "get_network_state_with_settings", _fake)


def _patch_model_get(monkeypatch, table):
    async def _fake_get(model_id):
        return table.get(model_id)

    monkeypatch.setattr(offline_gate, "_get_model_record", _fake_get)


def test_none_candidate_passes_through(monkeypatch):
    _patch_state(monkeypatch, "offline")
    assert _run(offline_gate.gate_language_model_id(None)) is None


def test_local_candidate_never_gated(monkeypatch):
    _patch_state(monkeypatch, "offline")
    _patch_model_get(
        monkeypatch, {"model:local": _model("model:local", "openai_compatible")}
    )
    assert _run(offline_gate.gate_language_model_id("model:local")) == "model:local"


def test_cloud_candidate_online_passes(monkeypatch):
    _patch_state(monkeypatch, "online")
    _patch_model_get(monkeypatch, {"model:gpt": _model("model:gpt", "openai")})
    assert _run(offline_gate.gate_language_model_id("model:gpt")) == "model:gpt"


def test_unknown_treated_as_online(monkeypatch):
    _patch_state(monkeypatch, "unknown")
    _patch_model_get(monkeypatch, {"model:gpt": _model("model:gpt", "openai")})
    assert _run(offline_gate.gate_language_model_id("model:gpt")) == "model:gpt"


def test_cloud_offline_substitutes_local(monkeypatch):
    _patch_state(monkeypatch, "offline")
    _patch_model_get(
        monkeypatch, {"model:gpt": _model("model:gpt", "openai", name="gpt-4o")}
    )

    async def _fake_find():
        return _model("model:gemma", "openai_compatible", name="gemma-4-E4B")

    monkeypatch.setattr(offline_gate, "find_local_language_model", _fake_find)

    out: dict = {}
    got = _run(offline_gate.gate_language_model_id("model:gpt", fallback_out=out))
    assert got == "model:gemma"
    assert out == {
        "offline_fallback": True,
        "from_model_id": "model:gpt",
        "to_model_id": "model:gemma",
        "to_model_name": "gemma-4-E4B",
        "reason": "offline",
    }


def test_cloud_offline_no_local_raises_fast(monkeypatch):
    _patch_state(monkeypatch, "offline")
    _patch_model_get(monkeypatch, {"model:gpt": _model("model:gpt", "openai")})

    async def _fake_find():
        return None

    monkeypatch.setattr(offline_gate, "find_local_language_model", _fake_find)

    with pytest.raises(ConfigurationError):
        _run(offline_gate.gate_language_model_id("model:gpt"))


def test_record_load_failure_passes_through(monkeypatch):
    _patch_state(monkeypatch, "offline")

    async def _boom(model_id):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(offline_gate, "_get_model_record", _boom)
    # Gate must never turn a DB hiccup into a blocked turn.
    assert _run(offline_gate.gate_language_model_id("model:gpt")) == "model:gpt"


def test_non_language_candidate_never_gated(monkeypatch):
    _patch_state(monkeypatch, "offline")
    _patch_model_get(
        monkeypatch, {"model:emb": _model("model:emb", "openai", type="embedding")}
    )
    assert _run(offline_gate.gate_language_model_id("model:emb")) == "model:emb"


def test_find_local_prefers_default_chat(monkeypatch):
    async def _fake_defaults():
        return SimpleNamespace(default_chat_model="model:gemma")

    monkeypatch.setattr(offline_gate, "_get_defaults", _fake_defaults)
    _patch_model_get(
        monkeypatch, {"model:gemma": _model("model:gemma", "openai_compatible")}
    )
    got = _run(offline_gate.find_local_language_model())
    assert got.id == "model:gemma"


def test_find_local_falls_back_to_query(monkeypatch):
    async def _fake_defaults():
        return SimpleNamespace(default_chat_model="model:gpt")

    monkeypatch.setattr(offline_gate, "_get_defaults", _fake_defaults)
    _patch_model_get(monkeypatch, {"model:gpt": _model("model:gpt", "openai")})

    async def _fake_by_type(t):
        return [
            _model("model:zeta", "ollama", name="zeta"),
            _model("model:alpha", "openai_compatible", name="alpha"),
            _model("model:cloudy", "anthropic", name="cloudy"),
        ]

    monkeypatch.setattr(offline_gate, "_get_language_models", _fake_by_type)
    got = _run(offline_gate.find_local_language_model())
    assert got.id == "model:alpha"  # local providers only, name-sorted


def test_forced_offline_reason_label(monkeypatch):
    async def _fake():
        return NetworkState(
            status="offline", forced_offline=True, checked_at=0.0, source="override"
        )

    monkeypatch.setattr(offline_gate, "get_network_state_with_settings", _fake)
    _patch_model_get(monkeypatch, {"model:gpt": _model("model:gpt", "openai")})

    async def _fake_find():
        return _model("model:gemma", "openai_compatible", name="gemma-4-E4B")

    monkeypatch.setattr(offline_gate, "find_local_language_model", _fake_find)

    out: dict = {}
    _run(offline_gate.gate_language_model_id("model:gpt", fallback_out=out))
    assert out["reason"] == "forced-offline"
