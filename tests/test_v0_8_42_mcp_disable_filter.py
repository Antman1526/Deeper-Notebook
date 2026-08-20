"""v0.8.42 — Per-request MCP server disable list tests.

The frontend sends `disabled_mcp_servers: [<names>]` in the chat body
so the user can untick specific MCP servers' tools for the current
chat turn without disabling them at the registry level. The chat
graph filters in `_resolve_chat_tools` BEFORE network discovery so
the filtered-out case never even probes the server.

Covers:
  - `_resolve_chat_tools(exclude_server_names=...)` filters the input.
  - Case-insensitive + whitespace-trim matching (UI typos / quoting).
  - `bind_mcp_and_run_tool_loop(exclude_server_names=...)` threads
    the kwarg through to the resolver.
  - `ExecuteChatRequest` schema accepts the new field (default null).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# _resolve_chat_tools filtering
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_resolve_chat_tools_filters_out_excluded_servers(monkeypatch):
    """An excluded server name → not in the resolved tool list. With
    only one server in the list AND that server excluded, the result
    is an empty list (and no network discovery happens — verified by
    the patched `list_tool_names` never being called)."""
    import deeper_notebook.graphs.chat as chat_mod

    # Use force_servers so we don't have to mock list_enabled_servers.
    # Two servers; exclude one; verify the other survives.
    fake_servers = [
        {"id": "1", "name": "SearXNG", "url": "http://127.0.0.1:8080"},
        {"id": "2", "name": "Crawl4AI", "url": "http://127.0.0.1:11235"},
    ]

    # Patch MCPClient so the test doesn't actually hit any URL — we
    # only care about which server NAME got through the filter into
    # `servers[0]`. The resolver only uses servers[0] today, so the
    # filter result is observable as "which server is the resolver
    # building its client around."
    captured_url: list[str] = []

    class _FakeClient:
        def __init__(self, *, url: str):
            captured_url.append(url)

        async def list_tool_names(self):
            return []

        async def list_tools(self):
            return []

        async def call_tool(self, *_a, **_k):
            return {}

    monkeypatch.setattr(chat_mod, "MCPClient", _FakeClient, raising=False)
    # Also patch the import inside _resolve_chat_tools — the function
    # does `from deeper_notebook.mcp.client import MCPClient` lazily.
    import deeper_notebook.mcp.client as mcp_client_mod

    monkeypatch.setattr(mcp_client_mod, "MCPClient", _FakeClient)

    # SearXNG excluded → Crawl4AI's URL should be captured.
    _run(
        chat_mod._resolve_chat_tools(
            force_servers=fake_servers,
            exclude_server_names=["SearXNG"],
        )
    )
    assert captured_url == ["http://127.0.0.1:11235"]


def test_resolve_chat_tools_excludes_case_insensitively(monkeypatch):
    """`searxng` and `SearXNG` and `  searxng  ` all match the same
    underlying server name. UI typos / quirky casing shouldn't
    silently bypass the user's intent."""
    import deeper_notebook.graphs.chat as chat_mod
    import deeper_notebook.mcp.client as mcp_client_mod

    fake_servers = [{"id": "1", "name": "SearXNG", "url": "http://x"}]

    class _FakeClient:
        def __init__(self, *, url):
            raise AssertionError(
                "MCPClient should NOT be constructed — server excluded",
            )

    monkeypatch.setattr(mcp_client_mod, "MCPClient", _FakeClient)

    # All three case variants → empty tools, no client constructed.
    for variant in ("searxng", "SEARXNG", "  SearXNG  "):
        tools = _run(
            chat_mod._resolve_chat_tools(
                force_servers=fake_servers,
                exclude_server_names=[variant],
            )
        )
        assert tools == [], f"variant {variant!r} did not filter out"


def test_resolve_chat_tools_empty_exclude_list_is_noop(monkeypatch):
    """An empty exclude list MUST NOT accidentally filter everything
    out. None and [] are both the "all-included" sentinel."""
    import deeper_notebook.graphs.chat as chat_mod
    import deeper_notebook.mcp.client as mcp_client_mod

    fake_servers = [{"id": "1", "name": "SearXNG", "url": "http://x"}]

    captured: list[str] = []

    class _FakeClient:
        def __init__(self, *, url):
            captured.append(url)

        async def list_tool_names(self):
            return []

        async def list_tools(self):
            return []

        async def call_tool(self, *_a, **_k):
            return {}

    monkeypatch.setattr(mcp_client_mod, "MCPClient", _FakeClient)

    for empty in (None, []):
        captured.clear()
        _run(
            chat_mod._resolve_chat_tools(
                force_servers=fake_servers,
                exclude_server_names=empty,
            )
        )
        assert captured == ["http://x"], (
            f"exclude={empty!r} unexpectedly filtered out the server"
        )


def test_resolve_chat_tools_ignores_blank_strings_in_exclude_list(monkeypatch):
    """A frontend that sends `disabled_mcp_servers: ["", "SearXNG", ""]`
    should still exclude SearXNG; empty entries are noise (not "exclude
    a server named empty string")."""
    import deeper_notebook.graphs.chat as chat_mod
    import deeper_notebook.mcp.client as mcp_client_mod

    fake_servers = [
        {"id": "1", "name": "SearXNG", "url": "http://a"},
        {"id": "2", "name": "Crawl4AI", "url": "http://b"},
    ]

    captured: list[str] = []

    class _FakeClient:
        def __init__(self, *, url):
            captured.append(url)

        async def list_tool_names(self):
            return []

        async def list_tools(self):
            return []

        async def call_tool(self, *_a, **_k):
            return {}

    monkeypatch.setattr(mcp_client_mod, "MCPClient", _FakeClient)

    _run(
        chat_mod._resolve_chat_tools(
            force_servers=fake_servers,
            exclude_server_names=["", "SearXNG", "   "],
        )
    )
    # Crawl4AI survived.
    assert captured == ["http://b"]


# ---------------------------------------------------------------------------
# bind_mcp_and_run_tool_loop threads exclude_server_names through
# ---------------------------------------------------------------------------


def test_bind_loop_forwards_exclude_to_resolver(monkeypatch):
    """bind_mcp_and_run_tool_loop is the seam the chat node calls.
    Verify the exclude list reaches `_resolve_chat_tools`."""
    import deeper_notebook.graphs.chat as chat_mod

    received: list[dict] = []

    async def _fake_resolve(
        *,
        force_servers=None,
        captures=None,
        force_tool_names=None,
        force_tools_full=None,
        exclude_server_names=None,
    ):
        received.append(
            {
                "exclude_server_names": exclude_server_names,
            }
        )
        return []

    monkeypatch.setattr(chat_mod, "_resolve_chat_tools", _fake_resolve)

    # We don't care about the model output here — just that the
    # resolver was called with the right exclude list. Provide a
    # minimal model whose .ainvoke returns a no-tool-calls message.
    class _FakeAI:
        tool_calls = []
        content = ""

        def model_copy(self, update):
            return self

    class _Model:
        async def ainvoke(self, _payload):
            return _FakeAI()

        def bind_tools(self, _tools):
            return self

    _run(
        chat_mod.bind_mcp_and_run_tool_loop(
            _Model(),
            payload=[],
            exclude_server_names=["SearXNG", "Crawl4AI"],
        )
    )

    assert len(received) == 1
    assert received[0]["exclude_server_names"] == ["SearXNG", "Crawl4AI"]


# ---------------------------------------------------------------------------
# ExecuteChatRequest schema accepts the field
# ---------------------------------------------------------------------------


def test_execute_chat_request_accepts_disabled_mcp_servers_field():
    """Schema must validate with disabled_mcp_servers absent (back-
    compat), present-and-null, present-and-empty, and present-with-
    list."""
    from api.routers.chat import ExecuteChatRequest

    # Absent — default null
    r = ExecuteChatRequest(
        session_id="chat_session:1",
        message="hi",
        context={},
    )
    assert r.disabled_mcp_servers is None

    # Explicit null
    r = ExecuteChatRequest(
        session_id="chat_session:1",
        message="hi",
        context={},
        disabled_mcp_servers=None,
    )
    assert r.disabled_mcp_servers is None

    # Empty list — treated as "no disables" by the resolver
    r = ExecuteChatRequest(
        session_id="chat_session:1",
        message="hi",
        context={},
        disabled_mcp_servers=[],
    )
    assert r.disabled_mcp_servers == []

    # Non-empty
    r = ExecuteChatRequest(
        session_id="chat_session:1",
        message="hi",
        context={},
        disabled_mcp_servers=["SearXNG"],
    )
    assert r.disabled_mcp_servers == ["SearXNG"]
