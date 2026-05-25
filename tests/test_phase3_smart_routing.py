"""Phase 3 Task 11 — pick_provider() unit tests.

Pure function tests for local-vs-cloud routing logic.
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
