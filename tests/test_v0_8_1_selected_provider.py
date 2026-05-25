"""v0.8.1 — ExecuteChatResponse.selected_provider shape + plumbing tests.

Background: the v0.8.0 chat smart-router (pick_provider in
open_notebook/ai/router.py) routes a chat turn to "local" or "cloud" and
provision_langchain_chat_model wraps it. Prior to v0.8.1 the routing
decision was log-only — nothing in the HTTP response told the client
which side won. scripts/verify-chat-platform.sh Steps 4 and 5 therefore
had to print "manual eyeball check" warnings.

v0.8.1 adds `selected_provider: Optional[str]` to ExecuteChatResponse.
The chat LangGraph node captures pick_provider's choice into state, and
the /chat/execute router reads it back into the response.

These tests verify the Pydantic shape AND that the plumbing from the
provision layer through the graph state actually surfaces the value
(mocked end-to-end — no live SurrealDB/LLM required).
"""
from __future__ import annotations

import pytest


class TestExecuteChatResponseShape:
    """The Pydantic model must declare `selected_provider`, default None."""

    def test_selected_provider_field_present_default_none(self):
        from api.routers.chat import ChatMessage, ExecuteChatResponse

        resp = ExecuteChatResponse(session_id="chat_session:abc", messages=[])
        # Default — the field exists and is None when unset.
        assert resp.selected_provider is None

    def test_selected_provider_accepts_local(self):
        from api.routers.chat import ExecuteChatResponse

        resp = ExecuteChatResponse(
            session_id="chat_session:abc",
            messages=[],
            selected_provider="local",
        )
        assert resp.selected_provider == "local"

    def test_selected_provider_accepts_cloud(self):
        from api.routers.chat import ExecuteChatResponse

        resp = ExecuteChatResponse(
            session_id="chat_session:abc",
            messages=[],
            selected_provider="cloud",
        )
        assert resp.selected_provider == "cloud"

    def test_selected_provider_in_serialized_output(self):
        """Pydantic model_dump() must include the key so FastAPI emits it."""
        from api.routers.chat import ExecuteChatResponse

        resp = ExecuteChatResponse(
            session_id="chat_session:abc",
            messages=[],
            selected_provider="local",
        )
        dumped = resp.model_dump()
        assert "selected_provider" in dumped
        assert dumped["selected_provider"] == "local"


class TestProvisionChatModelExposesSelection:
    """provision_langchain_chat_model must surface its routing choice when
    the caller asks for it. The chat-graph node uses this hook to write
    `selected_provider` into the LangGraph state so the /chat/execute
    router can include it in the response."""

    def _run(self, coro):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_selection_out_populated_when_routing_picks_local(self, monkeypatch):
        """Smart router on, healthy local, small content → selection_out
        carries provider='local'."""
        import open_notebook.ai.provision as provision_mod

        monkeypatch.setenv("OPEN_NOTEBOOK_AUTO_ROUTE_CHAT", "1")
        monkeypatch.setenv("OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID", "model:hermes")
        monkeypatch.setenv("OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID", "model:gpt4")
        monkeypatch.delenv("OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL", raising=False)
        monkeypatch.setattr(
            provision_mod, "_local_chat_healthy_cached", lambda: True
        )

        async def _fake_provision(content, model_id, default_type, **kwargs):
            return object()

        monkeypatch.setattr(
            provision_mod, "provision_langchain_model", _fake_provision
        )

        selection_out: dict = {}
        self._run(
            provision_mod.provision_langchain_chat_model(
                "short prompt", selection_out=selection_out
            )
        )

        assert selection_out.get("selected_provider") == "local"
        assert selection_out.get("selected_model_id") == "model:hermes"

    def test_selection_out_populated_when_routing_picks_cloud(self, monkeypatch):
        """Overflow content → router picks cloud → selection_out reflects it."""
        import open_notebook.ai.provision as provision_mod

        monkeypatch.setenv("OPEN_NOTEBOOK_AUTO_ROUTE_CHAT", "1")
        monkeypatch.setenv("OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID", "model:hermes")
        monkeypatch.setenv("OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID", "model:gpt4")
        monkeypatch.setenv("OPEN_NOTEBOOK_LOCAL_N_CTX", "32768")
        monkeypatch.delenv("OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL", raising=False)
        monkeypatch.setattr(
            provision_mod, "_local_chat_healthy_cached", lambda: True
        )

        async def _fake_provision(content, model_id, default_type, **kwargs):
            return object()

        monkeypatch.setattr(
            provision_mod, "provision_langchain_model", _fake_provision
        )

        selection_out: dict = {}
        self._run(
            provision_mod.provision_langchain_chat_model(
                "x" * 500_000, selection_out=selection_out
            )
        )

        assert selection_out.get("selected_provider") == "cloud"
        assert selection_out.get("selected_model_id") == "model:gpt4"

    def test_selection_out_none_when_smart_routing_disabled(self, monkeypatch):
        """Smart-routing env var unset → selection_out stays empty (no
        local/cloud distinction exists in the default-path)."""
        import open_notebook.ai.provision as provision_mod

        monkeypatch.delenv("OPEN_NOTEBOOK_AUTO_ROUTE_CHAT", raising=False)

        async def _fake_provision(content, model_id, default_type, **kwargs):
            return object()

        monkeypatch.setattr(
            provision_mod, "provision_langchain_model", _fake_provision
        )

        selection_out: dict = {}
        self._run(
            provision_mod.provision_langchain_chat_model(
                "short prompt", selection_out=selection_out
            )
        )

        # No selected_provider key set — caller treats absence as None.
        assert selection_out.get("selected_provider") is None
