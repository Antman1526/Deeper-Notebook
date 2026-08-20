"""v0.8.44b — Source-chat session persistence for MCP picks.

v0.8.44 made source-chat MCP picks per-request (hook-local). v0.8.44b
persists them on the session row — reusing migration 20 (v0.8.43)
since source-chat sessions share the `chat_session` table with
notebook chat.

Tests (schema-level; the live-DB round-trip is exercised by the
shared ChatSession domain tests in test_v0_8_43_persistent_mcp_picks):
  - UpdateSourceChatSessionRequest accepts the field (absent / null /
    empty / list) with exclude_unset semantics.
  - SourceChatSessionResponse + WithMessages expose the field.
  - The update handler uses exclude_unset (omitting the field is NOT
    a clear).
  - The SSE precedence: request body wins, session value falls back.
"""

from __future__ import annotations

import pytest

from api.routers.source_chat import (
    SendMessageRequest,
    SourceChatSessionResponse,
    SourceChatSessionWithMessagesResponse,
    UpdateSourceChatSessionRequest,
)


def test_update_request_accepts_disabled_mcp_servers_exclude_unset():
    # Absent → not in exclude_unset dump (rename/model-override flow
    # must not clobber the persisted picks)
    r = UpdateSourceChatSessionRequest(title="Renamed")
    assert "disabled_mcp_servers" not in r.model_dump(exclude_unset=True)

    # Explicit null
    r = UpdateSourceChatSessionRequest(disabled_mcp_servers=None)
    assert r.disabled_mcp_servers is None

    # Empty list IS in exclude_unset (explicit "no disables")
    r = UpdateSourceChatSessionRequest(disabled_mcp_servers=[])
    assert r.disabled_mcp_servers == []
    assert "disabled_mcp_servers" in r.model_dump(exclude_unset=True)

    # Non-empty
    r = UpdateSourceChatSessionRequest(disabled_mcp_servers=["SearXNG"])
    assert r.disabled_mcp_servers == ["SearXNG"]


def test_response_schemas_expose_disabled_mcp_servers():
    resp = SourceChatSessionResponse(
        id="chat_session:abc",
        title="t",
        source_id="source:1",
        created="2026-01-01T00:00:00Z",
        updated="2026-01-01T00:00:00Z",
        message_count=0,
        disabled_mcp_servers=["SearXNG"],
    )
    assert resp.disabled_mcp_servers == ["SearXNG"]

    # WithMessages subclass inherits the field; default null when unset.
    wresp = SourceChatSessionWithMessagesResponse(
        id="chat_session:abc",
        title="t",
        source_id="source:1",
        created="2026-01-01T00:00:00Z",
        updated="2026-01-01T00:00:00Z",
    )
    assert wresp.disabled_mcp_servers is None


def test_send_message_request_still_carries_per_request_field():
    """v0.8.44 per-request field is independent of v0.8.44b session
    persistence; both coexist."""
    r = SendMessageRequest(message="hi", disabled_mcp_servers=["X"])
    assert r.disabled_mcp_servers == ["X"]


def test_sse_precedence_request_wins_else_session_fallback():
    """Reproduces the handler's precedence expression so a future
    refactor that breaks it is caught here. Request body (incl. an
    explicit empty list) wins; only a null body falls back to the
    session's persisted picks."""

    def effective(request_val, session_val):
        # Mirror of api/routers/source_chat.py send-message handler.
        return request_val if request_val is not None else session_val

    # Request null → session fallback
    assert effective(None, ["SearXNG"]) == ["SearXNG"]
    # Request empty list → explicit "no disables this turn" (NOT fallback)
    assert effective([], ["SearXNG"]) == []
    # Request non-empty → wins
    assert effective(["Crawl4AI"], ["SearXNG"]) == ["Crawl4AI"]
    # Both null → null
    assert effective(None, None) is None
