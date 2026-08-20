"""v0.8.68 — provision_langchain_model consults the offline gate."""

from __future__ import annotations

import asyncio

import pytest

from deeper_notebook.ai import provision
from deeper_notebook.exceptions import ConfigurationError


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeLangchain:
    pass


class _FakeEsperantoModel:
    def to_langchain(self):
        return _FakeLangchain()


def _patch_manager(monkeypatch, *, default_id="model:gpt"):
    """Patch model_manager: id resolution + instantiation recording."""
    got: dict = {}

    async def _fake_default_id(model_type):
        return default_id

    async def _fake_get_model(model_id, **kwargs):
        got["model_id"] = model_id
        return _FakeEsperantoModel()

    monkeypatch.setattr(
        provision.model_manager, "get_default_model_id", _fake_default_id
    )
    monkeypatch.setattr(provision.model_manager, "get_model", _fake_get_model)
    # isinstance(model, LanguageModel) check: make the fake pass.
    monkeypatch.setattr(provision, "LanguageModel", object)
    return got


def test_gate_substitution_flows_through(monkeypatch):
    got = _patch_manager(monkeypatch)

    async def _fake_gate(candidate_id, *, fallback_out=None):
        if fallback_out is not None:
            fallback_out["offline_fallback"] = True
            fallback_out["to_model_id"] = "model:gemma"
        return "model:gemma"

    monkeypatch.setattr(provision, "gate_language_model_id", _fake_gate)

    out: dict = {}
    model = _run(
        provision.provision_langchain_model(
            "hello",
            None,
            "chat",
            fallback_out=out,
        )
    )
    assert isinstance(model, _FakeLangchain)
    assert got["model_id"] == "model:gemma"
    assert out.get("offline_fallback") is True


def test_gate_passthrough_keeps_explicit_candidate(monkeypatch):
    got = _patch_manager(monkeypatch)

    async def _fake_gate(candidate_id, *, fallback_out=None):
        return candidate_id

    monkeypatch.setattr(provision, "gate_language_model_id", _fake_gate)

    _run(provision.provision_langchain_model("hello", "model:explicit", "chat"))
    assert got["model_id"] == "model:explicit"


def test_gate_configuration_error_propagates(monkeypatch):
    _patch_manager(monkeypatch)

    async def _fake_gate(candidate_id, *, fallback_out=None):
        raise ConfigurationError("offline, no local model")

    monkeypatch.setattr(provision, "gate_language_model_id", _fake_gate)

    with pytest.raises(ConfigurationError):
        _run(provision.provision_langchain_model("hello", None, "chat"))


def test_no_candidate_still_raises_configuration_error(monkeypatch):
    _patch_manager(monkeypatch, default_id=None)

    async def _fake_gate(candidate_id, *, fallback_out=None):
        return candidate_id

    monkeypatch.setattr(provision, "gate_language_model_id", _fake_gate)

    with pytest.raises(ConfigurationError):
        _run(provision.provision_langchain_model("hello", None, "chat"))


def test_default_path_load_failure_becomes_no_model_configured(monkeypatch):
    """Pre-v0.8.68 behavior preserved: a default-resolved id that fails to
    load logs and falls through to the 'No model configured' error."""
    got = _patch_manager(monkeypatch)

    async def _fake_get_model(model_id, **kwargs):
        raise ConfigurationError("model record vanished")

    monkeypatch.setattr(provision.model_manager, "get_model", _fake_get_model)

    async def _fake_gate(candidate_id, *, fallback_out=None):
        return candidate_id

    monkeypatch.setattr(provision, "gate_language_model_id", _fake_gate)

    with pytest.raises(ConfigurationError) as exc_info:
        _run(provision.provision_langchain_model("hello", None, "chat"))
    assert "No model configured" in str(exc_info.value)


def test_explicit_path_load_failure_propagates_verbatim(monkeypatch):
    """Explicit model_id keeps get_model's typed error (pre-v0.8.68)."""
    _patch_manager(monkeypatch)

    async def _fake_get_model(model_id, **kwargs):
        raise ConfigurationError("Model with ID model:explicit not found.")

    monkeypatch.setattr(provision.model_manager, "get_model", _fake_get_model)

    async def _fake_gate(candidate_id, *, fallback_out=None):
        return candidate_id

    monkeypatch.setattr(provision, "gate_language_model_id", _fake_gate)

    with pytest.raises(ConfigurationError) as exc_info:
        _run(provision.provision_langchain_model("hello", "model:explicit", "chat"))
    assert "not found" in str(exc_info.value)
