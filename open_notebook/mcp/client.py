"""Phase 2 — Generic MCP client wrapper.

Wraps `mcp.client.streamable_http.streamablehttp_client` so the
chat graph can call `await client.list_tool_names()` and
`await client.call_tool(name, args)` without dealing with the
session lifecycle directly.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass


@asynccontextmanager
async def _open_session(url: str):
    """Open an MCP ClientSession over streamable HTTP. Each call
    is a fresh session — MCP's streamable-http transport doesn't
    keep sessions across requests (per the openchronicle shim's
    inline comment in v0.4)."""
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@dataclass
class MCPClient:
    url: str

    async def list_tool_names(self) -> list[str]:
        async with _open_session(self.url) as s:
            result = await s.list_tools()
            return [t.name for t in result.tools]

    async def call_tool(self, name: str, arguments: dict) -> dict:
        async with _open_session(self.url) as s:
            result = await s.call_tool(name, arguments=arguments)
            if result.content:
                first = result.content[0]
                if hasattr(first, "text"):
                    return {"ok": True, "text": first.text}
                return {"ok": True, "data": getattr(first, "data", None)}
            return {"ok": True, "text": ""}
