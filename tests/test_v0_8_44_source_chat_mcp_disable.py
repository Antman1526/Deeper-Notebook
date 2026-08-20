"""v0.8.44 — Source-chat MCP picker parity tests.

The v0.8.42 + v0.8.43 work shipped MCP server disable picks for notebook
chat. v0.8.44 brings the same affordance to source-chat:

  - `SourceChatState` carries `disabled_mcp_servers: Optional[list[str]]`.
  - `SendMessageRequest` (source-chat router) accepts `disabled_mcp_servers`
    with the same shape as `ExecuteChatRequest`.
  - The source-chat graph node forwards the state field into
    `bind_mcp_and_run_tool_loop(exclude_server_names=...)` — identical to
    the v0.8.42 chat graph wiring.

Tests:
  - Schema accepts the new field (absent / null / empty / list).
  - The source-chat router signature exists and propagates the field
    through to `stream_source_chat_response`.
  - `SourceChatState` TypedDict has the field declared (regression
    guard against an accidental schema rollback).
"""

from __future__ import annotations

import typing

import pytest


def test_send_message_request_accepts_disabled_mcp_servers():
    """Schema must validate the new optional list field (absent / null
    / empty / non-empty) with the v0.8.42 chat-router shape."""
    from api.routers.source_chat import SendMessageRequest

    # Absent → null default
    r = SendMessageRequest(message="hi")
    assert r.disabled_mcp_servers is None

    # Explicit null
    r = SendMessageRequest(message="hi", disabled_mcp_servers=None)
    assert r.disabled_mcp_servers is None

    # Empty list — treated as "no disables" downstream
    r = SendMessageRequest(message="hi", disabled_mcp_servers=[])
    assert r.disabled_mcp_servers == []

    # Non-empty
    r = SendMessageRequest(
        message="hi",
        disabled_mcp_servers=["SearXNG", "Crawl4AI"],
    )
    assert r.disabled_mcp_servers == ["SearXNG", "Crawl4AI"]


def test_source_chat_state_has_disabled_mcp_servers_field():
    """SourceChatState TypedDict must declare the field. A future
    accidental rollback that drops it would silently break the picker
    on source chat — guard with a type-level assertion."""
    from deeper_notebook.graphs.source_chat import SourceChatState

    hints = typing.get_type_hints(SourceChatState)
    assert "disabled_mcp_servers" in hints, (
        "v0.8.44: SourceChatState lost the disabled_mcp_servers field"
    )


def test_stream_source_chat_response_accepts_disabled_mcp_servers_kwarg():
    """Generator signature must accept the kwarg — otherwise the
    handler can't forward `request.disabled_mcp_servers` into it."""
    import inspect

    from api.routers.source_chat import stream_source_chat_response

    sig = inspect.signature(stream_source_chat_response)
    assert "disabled_mcp_servers" in sig.parameters, (
        "v0.8.44: stream_source_chat_response missing disabled_mcp_servers "
        "kwarg — handler can't propagate the per-request picks"
    )
    # And the default should be None (back-compat — pre-v0.8.44 callers
    # didn't pass it).
    assert sig.parameters["disabled_mcp_servers"].default is None
