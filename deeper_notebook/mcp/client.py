"""Phase 2 — Generic MCP client wrapper.

Wraps `mcp.client.streamable_http.streamablehttp_client` so the
chat graph can call `await client.list_tool_names()` and
`await client.call_tool(name, args)` without dealing with the
session lifecycle directly.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

from deeper_notebook.environment import resolve_env


def _rpc_timeout(default: float = 30.0) -> float:
    """v0.8.66 (audit MCP-1) — bound EVERY MCP RPC. Without this, an
    unresponsive server pins the caller (discovery in `_resolve_chat_tools`,
    the `/api/mcp/{id}/test` endpoint) up to the transport's ~300s SSE read
    timeout. Guarded+clamped like the other env knobs: blank/garbage/≤0 →
    default 30s."""
    raw = (resolve_env("DEEPER_NOTEBOOK_MCP_RPC_TIMEOUT_SEC") or "").strip()
    if not raw:
        return default
    try:
        val = float(raw)
    except ValueError:
        return default
    return val if val > 0 else default


def _env_headers() -> Optional[dict[str, str]]:
    """v0.8.66 (audit MCP-4) — optional auth header for protected MCP servers.
    `ONP_MCP_AUTH_HEADER="Authorization: Bearer <token>"` (a single
    `Name: value` pair) makes auth'd streamable-http servers usable without a
    registry-schema change. Returns None when unset."""
    raw = (resolve_env("DEEPER_NOTEBOOK_MCP_AUTH_HEADER") or "").strip()
    if not raw or ":" not in raw:
        return None
    name, _, value = raw.partition(":")
    name, value = name.strip(), value.strip()
    return {name: value} if name and value else None


@asynccontextmanager
async def _open_session(url: str, headers: Optional[dict[str, str]] = None):
    """Open an MCP ClientSession over streamable HTTP. Each call
    is a fresh session — MCP's streamable-http transport doesn't
    keep sessions across requests (per the openchronicle shim's
    inline comment in v0.4)."""
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    # v0.8.66 (audit MCP-4) — pass auth headers when provided (some MCP
    # transports reject an explicit `headers=None`, so only forward when set).
    kwargs = {"headers": headers} if headers else {}
    async with streamablehttp_client(url, **kwargs) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@dataclass
class MCPClient:
    url: str
    headers: Optional[dict[str, str]] = field(default=None)

    def _headers(self) -> Optional[dict[str, str]]:
        return self.headers or _env_headers()

    async def list_tool_names(self) -> list[str]:
        async def _do() -> list[str]:
            async with _open_session(self.url, self._headers()) as s:
                result = await s.list_tools()
                return [t.name for t in result.tools]
        return await asyncio.wait_for(_do(), timeout=_rpc_timeout())

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
        async def _do() -> list[dict[str, Any]]:
            async with _open_session(self.url, self._headers()) as s:
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
        # v0.8.66 (audit MCP-1) — bound discovery; a hung server otherwise
        # stalls every chat turn that resolves tools.
        return await asyncio.wait_for(_do(), timeout=_rpc_timeout())

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """v0.8.13 — return ALL content blocks, not just the first,
        and preserve the block type so non-text content (images,
        embedded resources, PDFs) isn't silently dropped.

        Output shape::

            {
                "ok": True,
                "text": "concatenated text from all TextContent blocks",
                "blocks": [
                    {"type": "text", "text": "..."},
                    {"type": "image", "mime_type": "image/png",
                     "data": "<base64...>", "bytes": 12345},
                    {"type": "resource", "uri": "...", "mime_type": "...",
                     "text": "..."},
                    {"type": "unknown", "repr": "<...>"},
                ],
            }

        ``text`` is kept at the top level for back-compat with the
        v0.8.11 closure that just wanted a string for the LLM. Empty
        result → ``text=""``, ``blocks=[]``.

        Pre-v0.8.13 only the FIRST content block was returned and
        non-text content was either missing its mime type
        (ImageContent) or silently lost (EmbeddedResource).
        """
        # v0.8.66 (audit MCP-1) — wrap the whole RPC in a timeout. The chat
        # tool loop already wraps THIS call (v0.8.35e), but the `/test` endpoint
        # and any direct caller did not; this makes the client safe by default.
        return await asyncio.wait_for(
            self._call_tool_inner(name, arguments), timeout=_rpc_timeout()
        )

    async def _call_tool_inner(self, name: str, arguments: dict) -> dict:
        async with _open_session(self.url, self._headers()) as s:
            result = await s.call_tool(name, arguments=arguments)
            content = list(result.content or [])

            blocks: list[dict] = []
            text_chunks: list[str] = []

            for block in content:
                # TextContent — `.text` is a plain string.
                if hasattr(block, "text") and not hasattr(block, "resource"):
                    txt = getattr(block, "text", "") or ""
                    blocks.append({"type": "text", "text": txt})
                    text_chunks.append(txt)
                    continue

                # ImageContent — `.data` is base64, `.mimeType` is e.g.
                # "image/png". `bytes` is an approximate decoded size
                # so the popover can show "image, 12 KB" without
                # decoding the actual base64.
                if hasattr(block, "data") and not hasattr(block, "resource"):
                    data = getattr(block, "data", "") or ""
                    mime = getattr(block, "mimeType", None) or "application/octet-stream"
                    # base64 -> bytes approx: len * 3 / 4 minus padding
                    approx = max(0, len(data) * 3 // 4)
                    blocks.append({
                        "type": "image",
                        "mime_type": mime,
                        "data": data,
                        "bytes": approx,
                    })
                    # Add a placeholder line to text_chunks so the LLM
                    # at least knows something arrived.
                    text_chunks.append(f"[image: {mime}, ~{approx} bytes]")
                    continue

                # EmbeddedResource — `.resource` has `.uri`, `.mimeType`,
                # and either `.text` or `.blob`.
                if hasattr(block, "resource"):
                    res = block.resource
                    uri = getattr(res, "uri", "") or ""
                    mime = getattr(res, "mimeType", None) or ""
                    res_text = getattr(res, "text", None)
                    res_blob = getattr(res, "blob", None)
                    entry: dict = {
                        "type": "resource",
                        "uri": str(uri),
                        "mime_type": mime,
                    }
                    if res_text is not None:
                        entry["text"] = res_text
                        text_chunks.append(res_text)
                    elif res_blob is not None:
                        # blob is base64 — same approximation as image
                        entry["data"] = res_blob
                        entry["bytes"] = max(0, len(res_blob) * 3 // 4)
                        text_chunks.append(
                            f"[resource: {uri or 'untitled'} ({mime}), "
                            f"~{entry['bytes']} bytes]"
                        )
                    else:
                        text_chunks.append(f"[resource: {uri or 'untitled'}]")
                    blocks.append(entry)
                    continue

                # Future-proof fallback for content types we don't
                # know about. Don't drop them silently — surface a
                # repr so the LLM and the operator can see something
                # arrived (so we know to add a handler).
                blocks.append({"type": "unknown", "repr": repr(block)})

            return {
                "ok": True,
                "text": "\n".join(c for c in text_chunks if c),
                "blocks": blocks,
            }
