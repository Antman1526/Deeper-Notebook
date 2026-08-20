"""v0.8.68 — offline_fallback flows node-result → ExecuteChatResponse."""

from __future__ import annotations

from api.routers.chat import ExecuteChatResponse


def test_execute_chat_response_carries_offline_fallback():
    resp = ExecuteChatResponse(
        session_id="s1",
        messages=[],
        offline_fallback={
            "offline_fallback": True,
            "from_model_id": "model:gpt",
            "to_model_id": "model:gemma",
            "to_model_name": "gemma-4-E4B",
            "reason": "offline",
        },
    )
    assert resp.offline_fallback["to_model_name"] == "gemma-4-E4B"


def test_execute_chat_response_defaults_none():
    resp = ExecuteChatResponse(session_id="s1", messages=[])
    assert resp.offline_fallback is None
