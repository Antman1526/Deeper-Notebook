"""Phase 2 — Generic MCP client wrapper.

Wraps `mcp.client.streamable_http.streamablehttp_client` so the
chat graph can call `await client.list_tool_names()` and
`await client.call_tool(name, args)` without dealing with the
session lifecycle directly.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any


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

    async def list_tools_full(self) -> list[dict[str, Any]]:
        """v0.8.11 — Return the full tool surface: name, description,
        and inputSchema (JSON Schema dict) per tool. This lets the
        chat graph build LangChain `StructuredTool`s with proper
        `args_schema` Pydantic models so `bind_tools` sends rich
        function-call schemas to the LLM (real arg names + types)
        instead of the no-schema fallback (single `input: str`).

        Pre-v0.8.11 the graph's `_resolve_chat_tools` only knew
        tool names — the LLM had to guess what args to pass, which
        worked when the server happened to use common arg names
        like `query`/`url` but failed silently otherwise.

        Returns one dict per tool with keys: name, description,
        input_schema. Missing/empty inputSchema falls back to a
        permissive empty object schema (LangChain treats as "no
        args"), so a tool with no args still binds cleanly.
        """
        async with _open_session(self.url) as s:
            result = await s.list_tools()
            tools_out: list[dict[str, Any]] = []
            for t in result.tools:
                schema = getattr(t, "inputSchema", None) or {
                    "type": "object", "properties": {}
                }
                tools_out.append({
                    "name": t.name,
                    "description": getattr(t, "description", "") or "",
                    "input_schema": schema,
                })
            return tools_out

    async def call_tool(self, name: str, arguments: dict) -> dict:
        async with _open_session(self.url) as s:
            result = await s.call_tool(name, arguments=arguments)
            if result.content:
                first = result.content[0]
                if hasattr(first, "text"):
                    return {"ok": True, "text": first.text}
                return {"ok": True, "data": getattr(first, "data", None)}
            return {"ok": True, "text": ""}
