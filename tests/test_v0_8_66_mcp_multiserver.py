"""v0.8.66 (audit MCP-2) — _resolve_chat_tools must bind tools from ALL enabled
MCP servers, not just servers[0]. Pre-fix, every server after the first was
silently ignored, so the multi-server Settings UI was a single-server selector.
"""

from __future__ import annotations

import asyncio

import pytest


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _patch_per_url_client(monkeypatch, tools_by_url):
    """Patch MCPClient so list_tools_full() returns a different tool set per
    server url."""
    import deeper_notebook.graphs.chat as chat_mod
    import deeper_notebook.mcp.client as mcp_client_mod

    class _FakeClient:
        def __init__(self, *, url):
            self.url = url

        async def list_tools_full(self):
            return tools_by_url.get(self.url, [])

        async def call_tool(self, *_a, **_k):
            return {"text": "ok"}

    monkeypatch.setattr(mcp_client_mod, "MCPClient", _FakeClient)
    # Discovery is TTL-cached by url — clear so the fakes are actually called.
    chat_mod._tool_discovery_cache.clear()
    return chat_mod


def _schema():
    return {"type": "object", "properties": {}}


def test_binds_tools_from_all_servers(monkeypatch):
    tools_by_url = {
        "http://a": [{"name": "alpha", "description": "", "input_schema": _schema()}],
        "http://b": [{"name": "beta", "description": "", "input_schema": _schema()}],
    }
    chat_mod = _patch_per_url_client(monkeypatch, tools_by_url)

    servers = [
        {"id": "1", "name": "A", "url": "http://a"},
        {"id": "2", "name": "B", "url": "http://b"},
    ]
    tools = _run(chat_mod._resolve_chat_tools(force_servers=servers))
    names = {t.name for t in tools}
    assert names == {"mcp_alpha", "mcp_beta"}, (
        f"expected tools from BOTH servers, got {names}"
    )


def test_tool_name_collision_first_server_wins(monkeypatch):
    """If two servers expose the same tool name, the first (higher-priority)
    server's tool is kept and the dup is dropped (logged)."""
    tools_by_url = {
        "http://a": [
            {"name": "search", "description": "from A", "input_schema": _schema()}
        ],
        "http://b": [
            {"name": "search", "description": "from B", "input_schema": _schema()}
        ],
    }
    chat_mod = _patch_per_url_client(monkeypatch, tools_by_url)

    servers = [
        {"id": "1", "name": "A", "url": "http://a"},
        {"id": "2", "name": "B", "url": "http://b"},
    ]
    tools = _run(chat_mod._resolve_chat_tools(force_servers=servers))
    assert [t.name for t in tools] == ["mcp_search"], "collision not deduped"
    assert "from A" in tools[0].description, "first server's tool should win"
