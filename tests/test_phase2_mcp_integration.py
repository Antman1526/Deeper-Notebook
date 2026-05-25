"""Phase 2 — MCP server client + chat-graph integration."""
from __future__ import annotations


def test_mcp_client_lists_tools_via_streamable_http(monkeypatch):
    """Given a working streamable-http MCP server URL, the client
    must `list_tools()` and return the discovered tool names."""
    from open_notebook.mcp.client import MCPClient

    fake_tools = [
        {"name": "web_search", "description": "Search the web"},
        {"name": "fetch_url", "description": "Fetch a URL"},
    ]

    class FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def list_tools(self):
            return type("X", (), {"tools": [
                type("T", (), {"name": t["name"], "description": t["description"]})()
                for t in fake_tools
            ]})()

    monkeypatch.setattr(
        "open_notebook.mcp.client._open_session",
        lambda url: FakeSession(),
    )
    client = MCPClient(url="http://127.0.0.1:8742/mcp")
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        names = loop.run_until_complete(client.list_tool_names())
    finally:
        loop.close()
    assert names == ["web_search", "fetch_url"]


def test_chat_graph_exposes_mcp_tools_when_enabled(monkeypatch):
    """When at least one MCP server is enabled, the chat graph's
    tool registry must include `mcp_search` and `mcp_fetch`."""
    monkeypatch.setattr(
        "open_notebook.mcp.registry.list_enabled_servers",
        lambda: __import__("asyncio").Future(),
    )
    from open_notebook.graphs.chat import _resolve_chat_tools
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        tools = loop.run_until_complete(
            _resolve_chat_tools(force_servers=[
                {"id": "mcp_server:1", "name": "test",
                 "url": "http://x", "enabled": True}
            ])
        )
    finally:
        loop.close()
    tool_names = [t.name for t in tools]
    assert "mcp_search" in tool_names
    assert "mcp_fetch" in tool_names


def test_mcp_registry_lists_enabled_servers(monkeypatch):
    """`list_enabled_servers()` returns only servers with
    `enabled=True`. Disabled servers are not used by the chat
    graph even if they're in the DB."""
    from open_notebook.mcp.registry import list_enabled_servers

    async def _fake_repo_query(q, params=None):
        return [
            {"id": "mcp_server:1", "name": "OpenChronicle",
             "url": "http://127.0.0.1:8742/mcp", "enabled": True},
            {"id": "mcp_server:2", "name": "DuckDuckGo",
             "url": "http://127.0.0.1:8743/mcp", "enabled": False},
        ]
    monkeypatch.setattr(
        "open_notebook.database.repository.repo_query",
        _fake_repo_query,
    )
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        servers = loop.run_until_complete(list_enabled_servers())
    finally:
        loop.close()
    assert len(servers) == 1
    assert servers[0]["name"] == "OpenChronicle"
