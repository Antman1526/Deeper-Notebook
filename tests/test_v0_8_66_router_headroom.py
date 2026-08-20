"""v0.8.66 (audit A-6/A-7) — pick_provider reserves the real reply + schema
headroom, not a flat 1000, so a near-full prompt routes to cloud instead of
overflowing the local sidecar (llama.cpp 400 context_length_exceeded).
"""

from __future__ import annotations

from deeper_notebook.ai.router import pick_provider


def test_near_full_prompt_routes_cloud_with_real_headroom():
    # 16k local ctx; prompt of 9000 content tokens. Fits under the OLD flat-1000
    # headroom (9000 <= 15000) → would have routed LOCAL then overflowed once an
    # 8192-token reply was reserved. With a realistic 9216 headroom it routes
    # cloud (9000 > 16384-9216=7168).
    choice = pick_provider(
        content_tokens=9000,
        local_chat_healthy=True,
        local_chat_n_ctx=16384,
        cloud_model_id="model:gpt-4o",
        local_model_id="model:hermes",
        default_provider="auto",
        reply_headroom_tokens=9216,
    )
    assert choice.model_id == "model:gpt-4o"
    assert "exceeds n_ctx" in choice.reason


def test_small_prompt_still_local_with_real_headroom():
    choice = pick_provider(
        content_tokens=1500,
        local_chat_healthy=True,
        local_chat_n_ctx=16384,
        cloud_model_id="model:gpt-4o",
        local_model_id="model:hermes",
        default_provider="auto",
        reply_headroom_tokens=9216,
    )
    assert choice.model_id == "model:hermes"


def test_default_headroom_is_back_compat():
    """Direct/legacy callers (no reply_headroom_tokens) keep ~1k behavior."""
    choice = pick_provider(
        content_tokens=2000,
        local_chat_healthy=True,
        local_chat_n_ctx=32768,
        cloud_model_id="model:gpt-4o",
        local_model_id="model:hermes",
        default_provider="auto",
    )
    assert choice.model_id == "model:hermes"
