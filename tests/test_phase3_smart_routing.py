"""Phase 3 Task 11+12 — pick_provider() and provision_langchain_chat_model() tests.

Task 11 tests are pure function tests for local-vs-cloud routing logic.
Task 12 tests verify that provision_langchain_chat_model() correctly gates
smart routing behind OPEN_NOTEBOOK_AUTO_ROUTE_CHAT and forwards the router's
choice to provision_langchain_model.

All tests are deterministic, require no I/O, and exercise every branch.
"""
import pytest
from open_notebook.ai.router import pick_provider, ModelChoice


class TestPickProviderAutoMode:
    """Spec: auto mode prefers local when healthy AND fits."""

    def test_router_prefers_local_when_healthy_and_fits(self):
        """Baseline happy path: healthy local, content fits in n_ctx with headroom."""
        choice = pick_provider(
            content_tokens=2000,
            local_chat_healthy=True,
            local_chat_n_ctx=32768,
            cloud_model_id="model:gpt-4o",
            local_model_id="model:hermes-3",
            default_provider="auto",
        )
        assert choice == ModelChoice(
            model_id="model:hermes-3",
            reason="local: healthy + fits in n_ctx",
        )

    def test_router_falls_back_to_cloud_when_too_big_for_local(self):
        """Content exceeds n_ctx - 1k headroom; fall back to cloud."""
        choice = pick_provider(
            content_tokens=50_000,
            local_chat_healthy=True,
            local_chat_n_ctx=32768,
            cloud_model_id="model:gpt-4o",
            local_model_id="model:hermes-3",
            default_provider="auto",
        )
        assert choice.model_id == "model:gpt-4o"
        assert "exceeds n_ctx" in choice.reason

    def test_router_local_unhealthy_falls_back_to_cloud(self):
        """Local sidecar unhealthy; fall back to cloud even if content fits."""
        choice = pick_provider(
            content_tokens=2000,
            local_chat_healthy=False,
            local_chat_n_ctx=32768,
            cloud_model_id="model:gpt-4o",
            local_model_id="model:hermes-3",
            default_provider="auto",
        )
        assert choice.model_id == "model:gpt-4o"
        assert "local unavailable" in choice.reason

    def test_router_respects_1k_headroom_threshold(self):
        """Content at exactly n_ctx - 1000 should use local; beyond that, cloud."""
        # Exactly 1000 headroom left: should use local
        choice = pick_provider(
            content_tokens=31768,  # 32768 - 1000
            local_chat_healthy=True,
            local_chat_n_ctx=32768,
            cloud_model_id="model:gpt-4o",
            local_model_id="model:hermes-3",
            default_provider="auto",
        )
        assert choice.model_id == "model:hermes-3"

        # 999 headroom left: should fall back to cloud
        choice = pick_provider(
            content_tokens=31769,  # 32768 - 999
            local_chat_healthy=True,
            local_chat_n_ctx=32768,
            cloud_model_id="model:gpt-4o",
            local_model_id="model:hermes-3",
            default_provider="auto",
        )
        assert choice.model_id == "model:gpt-4o"


class TestPickProviderOverrides:
    """Spec: user-forced overrides win over auto logic."""

    def test_router_user_forced_cloud_wins_over_auto(self):
        """User explicitly picks cloud; ignore local health/fit."""
        choice = pick_provider(
            content_tokens=2000,
            local_chat_healthy=True,
            local_chat_n_ctx=32768,
            cloud_model_id="model:gpt-4o",
            local_model_id="model:hermes-3",
            default_provider="cloud",
        )
        assert choice.model_id == "model:gpt-4o"
        assert choice.reason == "user-forced cloud"

    def test_router_user_forced_local_wins_over_auto(self):
        """User explicitly picks local; ignore content size."""
        choice = pick_provider(
            content_tokens=50_000,  # Way over n_ctx
            local_chat_healthy=True,
            local_chat_n_ctx=32768,
            cloud_model_id="model:gpt-4o",
            local_model_id="model:hermes-3",
            default_provider="local",
        )
        assert choice.model_id == "model:hermes-3"
        assert choice.reason == "user-forced local"

    def test_router_forced_cloud_without_cloud_model_falls_through(self):
        """User forces cloud but no cloud model configured; gracefully fall back to auto."""
        choice = pick_provider(
            content_tokens=2000,
            local_chat_healthy=True,
            local_chat_n_ctx=32768,
            cloud_model_id=None,
            local_model_id="model:hermes-3",
            default_provider="cloud",
        )
        # Falls through to auto-mode since cloud is not available
        assert choice.model_id == "model:hermes-3"
        assert "healthy" in choice.reason

    def test_router_forced_local_without_local_model_raises(self):
        """User forces local but no local model configured; error."""
        with pytest.raises(ValueError, match="No model available"):
            pick_provider(
                content_tokens=2000,
                local_chat_healthy=True,
                local_chat_n_ctx=32768,
                cloud_model_id="model:gpt-4o",
                local_model_id=None,
                default_provider="local",
            )


class TestPickProviderErrorCases:
    """Spec: error on genuinely impossible states."""

    def test_router_raises_when_no_model_available(self):
        """Both cloud and local are None; impossible state."""
        with pytest.raises(ValueError, match="No model available"):
            pick_provider(
                content_tokens=2000,
                local_chat_healthy=True,
                local_chat_n_ctx=32768,
                cloud_model_id=None,
                local_model_id=None,
                default_provider="auto",
            )


class TestPickProviderFallbacks:
    """Edge cases and fallback paths."""

    def test_router_local_fallback_when_oversized_and_no_cloud(self):
        """Content oversized, local unhealthy, but only local available."""
        choice = pick_provider(
            content_tokens=50_000,
            local_chat_healthy=False,
            local_chat_n_ctx=32768,
            cloud_model_id=None,
            local_model_id="model:hermes-3",
            default_provider="auto",
        )
        assert choice.model_id == "model:hermes-3"
        assert "fallback" in choice.reason

    def test_router_cloud_preferred_over_unhealthy_local(self):
        """Local unhealthy, cloud available; use cloud."""
        choice = pick_provider(
            content_tokens=10_000,
            local_chat_healthy=False,
            local_chat_n_ctx=32768,
            cloud_model_id="model:gpt-4o",
            local_model_id="model:hermes-3",
            default_provider="auto",
        )
        assert choice.model_id == "model:gpt-4o"
        assert "local unavailable" in choice.reason


# ---------------------------------------------------------------------------
# Phase 3 Task 12 — provision_langchain_chat_model() wiring tests
# ---------------------------------------------------------------------------


class TestProvisionLangchainChatModelDisabled:
    """OPEN_NOTEBOOK_AUTO_ROUTE_CHAT unset — wrapper must be a transparent
    pass-through to provision_langchain_model(model_id=None, default_type='chat')."""

    def test_provision_skips_router_when_disabled(self, monkeypatch):
        """When auto-routing env var is unset the wrapper delegates directly
        to provision_langchain_model with model_id=None and default_type='chat'.
        pick_provider() must never be called."""
        import asyncio
        import open_notebook.ai.provision as provision_mod

        # Ensure env var is absent
        monkeypatch.delenv("OPEN_NOTEBOOK_AUTO_ROUTE_CHAT", raising=False)

        captured: list[dict] = []

        async def _fake_provision(content, model_id, default_type, **kwargs):
            captured.append(
                {"content": content, "model_id": model_id, "default_type": default_type}
            )
            return object()  # sentinel — caller doesn't dereference the model

        monkeypatch.setattr(provision_mod, "provision_langchain_model", _fake_provision)

        # Also assert pick_provider is never reached by patching it to explode
        import open_notebook.ai.router as router_mod

        def _exploding_pick_provider(**kwargs):
            raise AssertionError("pick_provider() must not be called when routing is off")

        monkeypatch.setattr(router_mod, "pick_provider", _exploding_pick_provider)

        asyncio.get_event_loop().run_until_complete(
            provision_mod.provision_langchain_chat_model("hello world")
        )

        assert len(captured) == 1
        assert captured[0]["model_id"] is None
        assert captured[0]["default_type"] == "chat"


class TestProvisionLangchainChatModelEnabled:
    """OPEN_NOTEBOOK_AUTO_ROUTE_CHAT=1 — wrapper must call pick_provider and
    forward its model_id choice to provision_langchain_model."""

    def _run(self, coro):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_provision_calls_router_when_enabled_picks_local(self, monkeypatch):
        """Small content + healthy local → router picks local model."""
        import open_notebook.ai.provision as provision_mod

        monkeypatch.setenv("OPEN_NOTEBOOK_AUTO_ROUTE_CHAT", "1")
        monkeypatch.setenv("OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID", "model:hermes")
        monkeypatch.setenv("OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID", "model:gpt4")
        monkeypatch.delenv("OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL", raising=False)

        # Patch health cache to return healthy
        monkeypatch.setattr(provision_mod, "_local_chat_healthy_cached", lambda: True)

        captured: list[dict] = []

        async def _fake_provision(content, model_id, default_type, **kwargs):
            captured.append({"model_id": model_id, "default_type": default_type})
            return object()

        monkeypatch.setattr(provision_mod, "provision_langchain_model", _fake_provision)

        # Small content — should fit in default n_ctx (32768) with headroom
        self._run(provision_mod.provision_langchain_chat_model("short prompt"))

        assert len(captured) == 1, "provision_langchain_model should be called exactly once"
        assert captured[0]["model_id"] == "model:hermes", (
            f"Expected local model_id 'model:hermes', got {captured[0]['model_id']!r}"
        )
        assert captured[0]["default_type"] == "chat"

    def test_provision_calls_router_when_enabled_picks_cloud(self, monkeypatch):
        """Huge content overflows local n_ctx → router picks cloud model."""
        import open_notebook.ai.provision as provision_mod

        monkeypatch.setenv("OPEN_NOTEBOOK_AUTO_ROUTE_CHAT", "1")
        monkeypatch.setenv("OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID", "model:hermes")
        monkeypatch.setenv("OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID", "model:gpt4")
        monkeypatch.setenv("OPEN_NOTEBOOK_LOCAL_N_CTX", "32768")
        monkeypatch.delenv("OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL", raising=False)

        monkeypatch.setattr(provision_mod, "_local_chat_healthy_cached", lambda: True)

        captured: list[dict] = []

        async def _fake_provision(content, model_id, default_type, **kwargs):
            captured.append({"model_id": model_id, "default_type": default_type})
            return object()

        monkeypatch.setattr(provision_mod, "provision_langchain_model", _fake_provision)

        # ~500k characters → vastly exceeds any local n_ctx → must pick cloud
        huge_content = "x" * 500_000
        self._run(provision_mod.provision_langchain_chat_model(huge_content))

        assert len(captured) == 1
        assert captured[0]["model_id"] == "model:gpt4", (
            f"Expected cloud model_id 'model:gpt4', got {captured[0]['model_id']!r}"
        )
        assert captured[0]["default_type"] == "chat"


# ---------------------------------------------------------------------------
# v0.8.1 Item 2 — cloud_model_id resolution via auto_route_cloud field
# ---------------------------------------------------------------------------


class TestCloudModelIdResolution:
    """Verify that provision_langchain_chat_model resolves cloud_model_id from
    DefaultModels.auto_route_cloud (not default_chat_model) when the env var
    is unset — the fix for the v0.8.0 silent-local-masquerade bug."""

    def _run(self, coro):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_cloud_id_resolves_from_auto_route_cloud_field(self, monkeypatch):
        """Env var unset: cloud_model_id must come from auto_route_cloud, NOT
        default_chat_model.  The v0.8.0 bug would have used default_chat_model
        which might be a local model."""
        import open_notebook.ai.provision as provision_mod

        monkeypatch.setenv("OPEN_NOTEBOOK_AUTO_ROUTE_CHAT", "1")
        monkeypatch.setenv("OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID", "model:local_y")
        # Env var intentionally absent — must resolve via field.
        monkeypatch.delenv("OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID", raising=False)
        monkeypatch.setenv("OPEN_NOTEBOOK_LOCAL_N_CTX", "32768")

        # Local is unhealthy so the router will try to use the cloud model.
        monkeypatch.setattr(provision_mod, "_local_chat_healthy_cached", lambda: False)

        # Stub get_defaults: auto_route_cloud points at cloud; default_chat_model at local.
        from open_notebook.ai.models import DefaultModels

        fake_defaults = DefaultModels.__new__(DefaultModels)
        object.__setattr__(fake_defaults, "auto_route_cloud", "model:cloud_x")
        object.__setattr__(fake_defaults, "default_chat_model", "model:local_y")

        monkeypatch.setattr(
            provision_mod.model_manager,
            "get_defaults",
            lambda: _async_return(fake_defaults),
        )

        captured: list[dict] = []

        async def _fake_provision(content, model_id, default_type, **kwargs):
            captured.append({"model_id": model_id})
            return object()

        monkeypatch.setattr(provision_mod, "provision_langchain_model", _fake_provision)

        # Oversized content to force cloud branch.
        self._run(provision_mod.provision_langchain_chat_model("x" * 500_000))

        assert len(captured) == 1
        assert captured[0]["model_id"] == "model:cloud_x", (
            f"Expected auto_route_cloud 'model:cloud_x', got {captured[0]['model_id']!r} — "
            "the v0.8.0 fallback to default_chat_model may still be in place"
        )

    def test_cloud_id_env_var_overrides_auto_route_cloud_field(self, monkeypatch):
        """OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID set: env var must win over the
        auto_route_cloud field value."""
        import open_notebook.ai.provision as provision_mod

        monkeypatch.setenv("OPEN_NOTEBOOK_AUTO_ROUTE_CHAT", "1")
        monkeypatch.setenv("OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID", "model:local_y")
        monkeypatch.setenv("OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID", "model:env_z")
        monkeypatch.setenv("OPEN_NOTEBOOK_LOCAL_N_CTX", "32768")

        monkeypatch.setattr(provision_mod, "_local_chat_healthy_cached", lambda: False)

        # Stub defaults with a different field value — env must take priority.
        from open_notebook.ai.models import DefaultModels

        fake_defaults = DefaultModels.__new__(DefaultModels)
        object.__setattr__(fake_defaults, "auto_route_cloud", "model:field_w")
        object.__setattr__(fake_defaults, "default_chat_model", "model:local_y")

        monkeypatch.setattr(
            provision_mod.model_manager,
            "get_defaults",
            lambda: _async_return(fake_defaults),
        )

        captured: list[dict] = []

        async def _fake_provision(content, model_id, default_type, **kwargs):
            captured.append({"model_id": model_id})
            return object()

        monkeypatch.setattr(provision_mod, "provision_langchain_model", _fake_provision)

        self._run(provision_mod.provision_langchain_chat_model("x" * 500_000))

        assert len(captured) == 1
        assert captured[0]["model_id"] == "model:env_z", (
            f"Expected env override 'model:env_z', got {captured[0]['model_id']!r}"
        )

    def test_cloud_id_is_none_when_neither_env_nor_field_set(self, monkeypatch):
        """Neither env var nor auto_route_cloud set: cloud_model_id must be None
        so pick_provider falls through to its 'no cloud configured' branch
        (uses local fallback) rather than masquerading a local model as cloud."""
        import open_notebook.ai.provision as provision_mod

        monkeypatch.setenv("OPEN_NOTEBOOK_AUTO_ROUTE_CHAT", "1")
        monkeypatch.setenv("OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID", "model:local_y")
        monkeypatch.delenv("OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID", raising=False)
        monkeypatch.setenv("OPEN_NOTEBOOK_LOCAL_N_CTX", "32768")

        # Local is healthy; content fits — pick_provider should return local.
        monkeypatch.setattr(provision_mod, "_local_chat_healthy_cached", lambda: True)

        # Stub defaults: auto_route_cloud is None (not configured).
        from open_notebook.ai.models import DefaultModels

        fake_defaults = DefaultModels.__new__(DefaultModels)
        object.__setattr__(fake_defaults, "auto_route_cloud", None)
        object.__setattr__(fake_defaults, "default_chat_model", "model:local_y")

        monkeypatch.setattr(
            provision_mod.model_manager,
            "get_defaults",
            lambda: _async_return(fake_defaults),
        )

        captured: list[dict] = []

        async def _fake_provision(content, model_id, default_type, **kwargs):
            captured.append({"model_id": model_id})
            return object()

        monkeypatch.setattr(provision_mod, "provision_langchain_model", _fake_provision)

        # Small content — fits local; with no cloud available it stays local.
        self._run(provision_mod.provision_langchain_chat_model("short prompt"))

        assert len(captured) == 1
        # The router must pick local (no cloud configured) rather than
        # fabricating a cloud route via default_chat_model.
        assert captured[0]["model_id"] == "model:local_y", (
            f"Expected local fallback 'model:local_y', got {captured[0]['model_id']!r} — "
            "router may be masquerading a local model as cloud"
        )


# ---------------------------------------------------------------------------
# Shared helper for async stubs
# ---------------------------------------------------------------------------


async def _async_return(value):
    """Helper: wrap a plain value in a coroutine so monkeypatch.setattr can
    replace async methods with a lambda that returns this coroutine."""
    return value


class TestHealthCacheTTL:
    """_local_chat_healthy_cached() must call the probe at most once within TTL."""

    def test_health_cache_respects_ttl(self, monkeypatch):
        """Two back-to-back calls within the TTL window must hit the probe
        exactly once (the second call returns the cached result)."""
        import open_notebook.ai.provision as provision_mod

        # Reset the module-level cache so the test starts clean
        monkeypatch.setattr(provision_mod, "_health_cache", None)

        probe_call_count = [0]

        def _fake_probe(creds):
            probe_call_count[0] += 1
            # Return a single healthy result so _health_cache is populated
            return [{"name": "Local GGUF (llama.cpp)", "status": "healthy"}]

        # Patch probe_all_local_models inside the health module so the import
        # inside _local_chat_healthy_cached resolves to our fake.
        import open_notebook.health.local_models as health_mod
        monkeypatch.setattr(health_mod, "probe_all_local_models", _fake_probe)

        # Provide a base URL so the cache path actually builds creds
        monkeypatch.setenv("OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL", "http://localhost:8080")

        # First call — cache miss, probe runs
        result1 = provision_mod._local_chat_healthy_cached()
        # Second call — cache hit within TTL, probe should NOT run again
        result2 = provision_mod._local_chat_healthy_cached()

        assert probe_call_count[0] == 1, (
            f"Expected probe to be called exactly once, got {probe_call_count[0]}"
        )
        assert result1 is True
        assert result2 is True
