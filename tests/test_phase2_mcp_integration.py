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
