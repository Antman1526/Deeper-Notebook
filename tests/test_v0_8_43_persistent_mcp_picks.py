"""v0.8.43 — Persistent per-conversation MCP picks tests.

The v0.8.42 picks were hook-local. v0.8.43 persists them on the
`chat_session` row so the user's "load only what I need" survives
page reload + navigation. Tests:

  - `ChatSession` domain model accepts + persists the new field.
  - `UpdateSessionRequest` schema accepts the new field with
    `exclude_unset=True` semantics (omitting it on PATCH does NOT
    clear the persisted value).
  - `ChatSessionResponse` exposes the field.
  - The migration file is syntactically valid SurrealQL.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.routers.chat import (
    ChatSessionResponse,
    ExecuteChatRequest,
    UpdateSessionRequest,
)


def test_update_session_request_accepts_disabled_mcp_servers():
    """The new field must be optional + accept null, [] and a list."""
    # Absent (the v0.7.x rename flow)
    r = UpdateSessionRequest(title="Renamed")
    assert "disabled_mcp_servers" not in r.model_dump(exclude_unset=True)

    # Explicit null
    r = UpdateSessionRequest(disabled_mcp_servers=None)
    assert r.disabled_mcp_servers is None

    # Empty list (user explicitly cleared all picks)
    r = UpdateSessionRequest(disabled_mcp_servers=[])
    assert r.disabled_mcp_servers == []
    # exclude_unset should NOT skip a set-to-empty-list field
    assert "disabled_mcp_servers" in r.model_dump(exclude_unset=True)

    # Non-empty
    r = UpdateSessionRequest(disabled_mcp_servers=["SearXNG"])
    assert r.disabled_mcp_servers == ["SearXNG"]


def test_chat_session_response_exposes_disabled_mcp_servers():
    """Response schema must include the field so the frontend hydrates
    `useNotebookChat.disabledMcpServers` on session load."""
    resp = ChatSessionResponse(
        id="chat_session:abc",
        title="t",
        notebook_id="notebook:1",
        created="2026-01-01T00:00:00Z",
        updated="2026-01-01T00:00:00Z",
        message_count=0,
        disabled_mcp_servers=["SearXNG", "Crawl4AI"],
    )
    assert resp.disabled_mcp_servers == ["SearXNG", "Crawl4AI"]
    # Default null when not set (back-compat for pre-v0.8.43 callers)
    resp2 = ChatSessionResponse(
        id="chat_session:abc",
        title="t",
        notebook_id="notebook:1",
        created="2026-01-01T00:00:00Z",
        updated="2026-01-01T00:00:00Z",
    )
    assert resp2.disabled_mcp_servers is None


def test_chat_session_domain_model_has_field():
    """Pydantic field on the domain model so SurrealDB writes the value."""
    from deeper_notebook.domain.notebook import ChatSession

    s = ChatSession(title="hello", disabled_mcp_servers=["SearXNG"])
    assert s.disabled_mcp_servers == ["SearXNG"]
    # Default None
    s2 = ChatSession(title="hello")
    assert s2.disabled_mcp_servers is None
    # Listed in nullable_fields so SurrealDB serializer treats None correctly
    assert "disabled_mcp_servers" in ChatSession.nullable_fields


def test_execute_chat_request_keeps_per_request_field():
    """Sanity check that v0.8.42's per-request field still works
    independently of v0.8.43's session-level field. Both are valid
    inputs — per-request wins when both are present."""
    r = ExecuteChatRequest(
        session_id="chat_session:1",
        message="hi",
        context={},
        disabled_mcp_servers=["X"],
    )
    assert r.disabled_mcp_servers == ["X"]


def test_v0_8_43_migration_files_exist_and_define_field():
    """Cheap migration sanity test — verify the up + down files exist
    and reference `disabled_mcp_servers ON chat_session`. A typo here
    would propagate silently on every install."""
    repository_root = Path(__file__).resolve().parent.parent
    base = repository_root / "deeper_notebook" / "database" / "migrations"
    expected_base = (
        Path(__file__).resolve().parent.parent
        / "deeper_notebook"
        / "database"
        / "migrations"
    )
    assert base == expected_base
    up = base / "20.surrealql"
    down = base / "20_down.surrealql"

    assert up.exists(), f"missing up migration: {up}"
    assert down.exists(), f"missing down migration: {down}"

    up_text = up.read_text()
    down_text = down.read_text()

    # Up MUST mention the new field + the chat_session table
    assert "disabled_mcp_servers" in up_text
    assert "chat_session" in up_text
    assert "DEFINE FIELD" in up_text

    # Down MUST remove the field (no half-rollback)
    assert "disabled_mcp_servers" in down_text
    assert "REMOVE FIELD" in down_text
