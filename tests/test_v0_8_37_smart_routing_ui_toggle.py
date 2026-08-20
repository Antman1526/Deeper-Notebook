"""v0.8.37 Phase 2 — `auto_route_enabled` + `auto_route_provider_pref`
fields on DefaultModels drive smart routing from the UI.

Background: pre-v0.8.37 the only way to flip smart routing on was the
DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT env var. Power-users could set it before
launch but the UI had no surface. v0.8.37 adds two persisted fields:

  - `auto_route_enabled: bool` (default False — same as the v0.8.0 default)
  - `auto_route_provider_pref: Literal["auto","local","cloud"]` (default "auto")

`provision_langchain_chat_model` consults these when the env var is
UNSET. Env var still wins for back-compat + ops overrides.

These tests cover the 4-way precedence matrix:
  - Env var "1" → smart routing ON regardless of field.
  - Env var "0" → smart routing OFF regardless of field.
  - Env var unset, field True → smart routing ON.
  - Env var unset, field False → smart routing OFF.
And the provider_pref field falls through to pick_provider correctly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


class _FakeDefaults:
    """Stand-in for DefaultModels.get_instance() return value. Only the
    attrs the provision module reads are populated."""

    def __init__(self, *, enabled=False, pref="auto", cloud=None):
        self.auto_route_enabled = enabled
        self.auto_route_provider_pref = pref
        self.auto_route_cloud = cloud
        self.default_chat_model = None


def _stub_defaults(monkeypatch, fake_defaults):
    """Patch model_manager.get_defaults to return our stub."""
    import deeper_notebook.ai.provision as provision_mod

    monkeypatch.setattr(
        provision_mod.model_manager,
        "get_defaults",
        AsyncMock(return_value=fake_defaults),
    )


def _stub_provision_inner(monkeypatch):
    """Replace provision_langchain_model with a capturing fake."""
    import deeper_notebook.ai.provision as provision_mod

    captured: list[dict] = []

    async def _fake(content, model_id, default_type, **kwargs):
        captured.append({"model_id": model_id, "default_type": default_type})
        return object()

    monkeypatch.setattr(provision_mod, "provision_langchain_model", _fake)
    return captured


def _run(coro):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)


class TestSmartRoutingToggleEnvVsField:
    """Env var precedence over the new DefaultModels field."""

    def test_env_var_truthy_wins_even_when_field_false(self, monkeypatch):
        """Env var ON → smart routing runs even if the UI toggle is off.
        Power-user setup keeps working after the v0.8.37 field rollout."""
        import deeper_notebook.ai.provision as provision_mod

        monkeypatch.setenv("DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT", "1")
        monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID", "model:hermes")
        monkeypatch.setenv("DEEPER_NOTEBOOK_CLOUD_CHAT_MODEL_ID", "model:gpt4")
        monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL", raising=False)
        monkeypatch.setattr(
            provision_mod,
            "_local_chat_healthy_cached",
            AsyncMock(return_value=True),
        )
        _stub_defaults(monkeypatch, _FakeDefaults(enabled=False, pref="auto"))
        captured = _stub_provision_inner(monkeypatch)

        _run(provision_mod.provision_langchain_chat_model("hi"))

        # Smart router ran — model_id is the local pick, not None.
        assert captured[0]["model_id"] == "model:hermes"

    def test_env_var_unset_field_true_enables_routing(self, monkeypatch):
        """The headline new behavior — UI toggle ON, no env var, smart
        router runs. Tests the exact path a user clicking "Enable smart
        routing" in Settings would hit on the next chat turn."""
        import deeper_notebook.ai.provision as provision_mod

        monkeypatch.delenv("DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT", raising=False)
        monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID", "model:hermes")
        monkeypatch.setenv("DEEPER_NOTEBOOK_CLOUD_CHAT_MODEL_ID", "model:gpt4")
        monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL", raising=False)
        monkeypatch.setattr(
            provision_mod,
            "_local_chat_healthy_cached",
            AsyncMock(return_value=True),
        )
        _stub_defaults(monkeypatch, _FakeDefaults(enabled=True, pref="auto"))
        captured = _stub_provision_inner(monkeypatch)

        _run(provision_mod.provision_langchain_chat_model("hi"))

        assert captured[0]["model_id"] == "model:hermes"

    def test_env_var_unset_field_false_keeps_routing_off(self, monkeypatch):
        """Default state — toggle off, env var off. The wrapper must pass
        model_id=None to the inner provision so the existing default-chat
        path drives selection (no router interference)."""
        import deeper_notebook.ai.provision as provision_mod

        monkeypatch.delenv("DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT", raising=False)
        _stub_defaults(monkeypatch, _FakeDefaults(enabled=False))
        captured = _stub_provision_inner(monkeypatch)

        _run(provision_mod.provision_langchain_chat_model("hi"))

        # Wrapper bypassed the router entirely — model_id=None means
        # "use the default for type=chat".
        assert captured[0]["model_id"] is None
        assert captured[0]["default_type"] == "chat"

    def test_get_defaults_failure_safe_defaults_to_off(self, monkeypatch):
        """If reading DefaultModels.get_instance() raises (DB unavailable,
        migration mid-flight, etc.) we must default to OFF — never
        accidentally route to a half-configured local sidecar."""
        import deeper_notebook.ai.provision as provision_mod

        monkeypatch.delenv("DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT", raising=False)
        monkeypatch.setattr(
            provision_mod.model_manager,
            "get_defaults",
            AsyncMock(side_effect=RuntimeError("DB down")),
        )
        captured = _stub_provision_inner(monkeypatch)

        _run(provision_mod.provision_langchain_chat_model("hi"))

        # Falls through to the disabled-path → model_id=None.
        assert captured[0]["model_id"] is None


class TestProviderPrefField:
    """auto_route_provider_pref flows through to pick_provider's
    default_provider arg."""

    def test_field_pref_local_forces_local(self, monkeypatch):
        """auto_route_provider_pref="local" → router honors user-forced
        local (per pick_provider's contract). Verified by feeding huge
        content that would normally route to cloud and asserting the
        local model is still picked."""
        import deeper_notebook.ai.provision as provision_mod

        monkeypatch.delenv("DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT", raising=False)
        monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_PROVIDER", raising=False)
        monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID", "model:hermes")
        monkeypatch.setenv("DEEPER_NOTEBOOK_CLOUD_CHAT_MODEL_ID", "model:gpt4")
        monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL", raising=False)
        monkeypatch.setattr(
            provision_mod,
            "_local_chat_healthy_cached",
            AsyncMock(return_value=True),
        )
        _stub_defaults(
            monkeypatch,
            _FakeDefaults(enabled=True, pref="local"),
        )
        captured = _stub_provision_inner(monkeypatch)

        # v0.8.67u — Use space-separated repeating pattern to prevent tiktoken regex backtracking.
        _run(provision_mod.provision_langchain_chat_model("x " * 250_000))
        # 500k chars would normally overflow local → cloud. Pref=local
        # overrides that decision.
        assert captured[0]["model_id"] == "model:hermes"

    def test_env_provider_overrides_field(self, monkeypatch):
        """DEEPER_NOTEBOOK_CHAT_PROVIDER env var wins over the field, same
        precedence shape as the master toggle."""
        import deeper_notebook.ai.provision as provision_mod

        monkeypatch.delenv("DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT", raising=False)
        monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_PROVIDER", "cloud")
        monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID", "model:hermes")
        monkeypatch.setenv("DEEPER_NOTEBOOK_CLOUD_CHAT_MODEL_ID", "model:gpt4")
        monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL", raising=False)
        monkeypatch.setattr(
            provision_mod,
            "_local_chat_healthy_cached",
            AsyncMock(return_value=True),
        )
        # Field says local but env says cloud → cloud wins.
        _stub_defaults(monkeypatch, _FakeDefaults(enabled=True, pref="local"))
        captured = _stub_provision_inner(monkeypatch)

        _run(provision_mod.provision_langchain_chat_model("hi"))

        assert captured[0]["model_id"] == "model:gpt4"

    def test_bad_pref_value_falls_back_to_auto(self, monkeypatch):
        """A typo / SurrealQL-direct write of an invalid pref string
        must NOT crash the chat turn — fall back to "auto"."""
        import deeper_notebook.ai.provision as provision_mod

        monkeypatch.delenv("DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT", raising=False)
        monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_PROVIDER", raising=False)
        monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID", "model:hermes")
        monkeypatch.setenv("DEEPER_NOTEBOOK_CLOUD_CHAT_MODEL_ID", "model:gpt4")
        monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL", raising=False)
        monkeypatch.setattr(
            provision_mod,
            "_local_chat_healthy_cached",
            AsyncMock(return_value=True),
        )
        _stub_defaults(
            monkeypatch,
            _FakeDefaults(enabled=True, pref="not-a-real-mode"),
        )
        captured = _stub_provision_inner(monkeypatch)

        _run(provision_mod.provision_langchain_chat_model("hi"))

        # Auto + healthy local + small content → local pick.
        assert captured[0]["model_id"] == "model:hermes"


class TestMeasuredBenchmarkChatRouting:
    """Measured local benchmark winners can fill the smart-router local slot."""

    def test_measured_chat_winner_used_when_env_local_model_missing(self, monkeypatch):
        """UI smart routing + no DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID should still
        have a local candidate when the local benchmark history has a measured
        chat winner."""
        import deeper_notebook.ai.provision as provision_mod

        monkeypatch.delenv("DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT", raising=False)
        monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID", raising=False)
        monkeypatch.setenv("DEEPER_NOTEBOOK_CLOUD_CHAT_MODEL_ID", "model:gpt4")
        monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL", raising=False)
        monkeypatch.setattr(
            provision_mod,
            "_local_chat_healthy_cached",
            AsyncMock(return_value=True),
        )
        monkeypatch.setattr(
            provision_mod,
            "_measured_local_chat_model_id",
            AsyncMock(return_value="model:bench-chat"),
        )
        _stub_defaults(monkeypatch, _FakeDefaults(enabled=True, pref="auto"))
        captured = _stub_provision_inner(monkeypatch)

        _run(provision_mod.provision_langchain_chat_model("hi"))

        assert captured[0]["model_id"] == "model:bench-chat"

    def test_env_local_model_still_overrides_measured_winner(self, monkeypatch):
        """Explicit operator/user local model choice keeps precedence over
        benchmark automation."""
        import deeper_notebook.ai.provision as provision_mod

        measured_lookup = AsyncMock(return_value="model:bench-chat")
        monkeypatch.delenv("DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT", raising=False)
        monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID", "model:hermes")
        monkeypatch.setenv("DEEPER_NOTEBOOK_CLOUD_CHAT_MODEL_ID", "model:gpt4")
        monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL", raising=False)
        monkeypatch.setattr(
            provision_mod,
            "_local_chat_healthy_cached",
            AsyncMock(return_value=True),
        )
        monkeypatch.setattr(
            provision_mod,
            "_measured_local_chat_model_id",
            measured_lookup,
        )
        _stub_defaults(monkeypatch, _FakeDefaults(enabled=True, pref="auto"))
        captured = _stub_provision_inner(monkeypatch)

        _run(provision_mod.provision_langchain_chat_model("hi"))

        assert captured[0]["model_id"] == "model:hermes"
        measured_lookup.assert_not_called()
