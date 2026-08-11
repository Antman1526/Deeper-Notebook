"""Phase 2 — Generic MCP client wrapper.

Wraps `mcp.client.streamable_http.streamablehttp_client` so the
chat graph can call `await client.list_tool_names()` and
`await client.call_tool(name, args)` without dealing with the
session lifecycle directly.
"""
from __future__ import annotations

import asyncio
import math
import os
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

from deeper_notebook.environment import resolve_env

# MCP responses are third-party input.  Keep every projection finite before it
# reaches the chat graph, while leaving ordinary valid responses unchanged.
_MAX_MCP_TOOLS = 64
_MAX_TOOL_NAME_CHARS = 128
_MAX_DESCRIPTION_CHARS = 2048
_MAX_SCHEMA_DEPTH = 6
_MAX_SCHEMA_ITEMS = 64
_MAX_SCHEMA_STRING_CHARS = 1024
_MAX_CONTENT_BLOCKS = 32
_MAX_TEXT_CHARS = 8192
_MAX_BINARY_CHARS = 1024 * 1024
# Per-block limits above keep an individual payload finite.  These result-wide
# budgets prevent a server from multiplying those limits across every allowed
# content block in one response.
_MAX_RESULT_TEXT_CHARS = 64 * 1024
_MAX_RESULT_BINARY_CHARS = 4 * 1024 * 1024
_MAX_URI_CHARS = 2048
_MAX_MIME_CHARS = 128
_MAX_REPR_CHARS = 1024
_MAX_RPC_TIMEOUT_SEC = 300.0

_EMPTY_SCHEMA = {"type": "object", "properties": {}}


def _bounded_iterable(value: Any, limit: int) -> list[Any]:
    """Read at most ``limit`` values without materialising an attacker iterable."""
    try:
        iterator = iter(value)
    except Exception:
        return []
    values: list[Any] = []
    for _ in range(limit):
        try:
            values.append(next(iterator))
        except StopIteration:
            break
        except Exception:
            break
    return values


def _normalise_tool_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or len(name) > _MAX_TOOL_NAME_CHARS:
        return None
    if any(ord(char) < 32 for char in name):
        return None
    return name


def _bounded_schema_value(value: Any, depth: int = 0) -> Any:
    """Copy JSON-like schema data with finite depth, keys, and strings."""
    if depth > _MAX_SCHEMA_DEPTH:
        return None
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value[:_MAX_SCHEMA_STRING_CHARS]
    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        try:
            items = iter(value.items())
        except Exception:
            return copied
        for _ in range(_MAX_SCHEMA_ITEMS):
            try:
                key, item = next(items)
            except StopIteration:
                break
            except Exception:
                break
            if not isinstance(key, str) or not key or len(key) > _MAX_SCHEMA_STRING_CHARS:
                continue
            bounded = _bounded_schema_value(item, depth + 1)
            if bounded is not None:
                copied[key] = bounded
        return copied
    if isinstance(value, (list, tuple)):
        return [
            bounded
            for item in _bounded_iterable(value, _MAX_SCHEMA_ITEMS)
            if (bounded := _bounded_schema_value(item, depth + 1)) is not None
        ]
    return None


def _bounded_input_schema(value: Any) -> dict[str, Any]:
    """Return a safe JSON-schema projection for a discovered MCP tool."""
    if not isinstance(value, Mapping):
        return dict(_EMPTY_SCHEMA)
    bounded = _bounded_schema_value(value)
    if not isinstance(bounded, dict):
        return dict(_EMPTY_SCHEMA)
    properties = bounded.get("properties")
    if not isinstance(properties, Mapping):
        properties = {}
    safe_properties: dict[str, dict[str, Any]] = {}
    try:
        property_items = iter(properties.items())
    except Exception:
        property_items = iter(())
    for _ in range(_MAX_SCHEMA_ITEMS):
        try:
            key, spec = next(property_items)
        except StopIteration:
            break
        except Exception:
            break
        if not isinstance(key, str) or not key or len(key) > _MAX_SCHEMA_STRING_CHARS:
            continue
        bounded_spec = _bounded_schema_value(spec)
        if isinstance(bounded_spec, dict):
            safe_properties[key] = bounded_spec
    bounded["type"] = "object"
    bounded["properties"] = safe_properties
    required = bounded.get("required")
    if isinstance(required, list):
        bounded["required"] = [
            name
            for name in required[:_MAX_SCHEMA_ITEMS]
            if isinstance(name, str) and name in safe_properties
        ]
    else:
        bounded.pop("required", None)
    return bounded


def _tool_value(tool: Any, key: str, default: Any = None) -> Any:
    if isinstance(tool, Mapping):
        return tool.get(key, default)
    return getattr(tool, key, default)


def _bounded_tool_spec(tool: Any) -> dict[str, Any] | None:
    try:
        name = _normalise_tool_name(_tool_value(tool, "name"))
    except Exception:
        return None
    if name is None:
        return None
    try:
        description = _tool_value(tool, "description", "")
    except Exception:
        description = ""
    if not isinstance(description, str):
        description = ""
    try:
        schema = _tool_value(tool, "input_schema", _tool_value(tool, "inputSchema"))
    except Exception:
        schema = None
    return {
        "name": name,
        "description": description[:_MAX_DESCRIPTION_CHARS],
        "input_schema": _bounded_input_schema(schema),
    }


def _bounded_tool_specs(raw_tools: Any) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for raw_tool in _bounded_iterable(raw_tools, _MAX_MCP_TOOLS):
        spec = _bounded_tool_spec(raw_tool)
        if spec is None:
            continue
        projected.append(spec)
    return projected


def _safe_repr(value: Any) -> str:
    try:
        return repr(value)[:_MAX_REPR_CHARS]
    except Exception:
        return "<unrepresentable MCP content>"


def _rpc_timeout(default: float = 30.0) -> float:
    """v0.8.66 (audit MCP-1) — bound EVERY MCP RPC. Without this, an
    unresponsive server pins the caller (discovery in `_resolve_chat_tools`,
    the `/api/mcp/{id}/test` endpoint) up to the transport's ~300s SSE read
    timeout. Guarded+clamped like the other env knobs: blank/garbage/≤0 →
    default 30s."""
    safe_default = (
        min(default, _MAX_RPC_TIMEOUT_SEC)
        if math.isfinite(default) and default > 0
        else 30.0
    )
    raw = (resolve_env("DEEPER_NOTEBOOK_MCP_RPC_TIMEOUT_SEC") or "").strip()
    if not raw:
        return safe_default
    try:
        val = float(raw)
    except ValueError:
        return safe_default
    if not math.isfinite(val) or val <= 0:
        return safe_default
    return min(val, _MAX_RPC_TIMEOUT_SEC)


def _env_headers() -> Optional[dict[str, str]]:
    """v0.8.66 (audit MCP-4) — optional auth header for protected MCP servers.
    `DEEPER_NOTEBOOK_MCP_AUTH_HEADER="Authorization: Bearer <token>"` (a single
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

    from api.credentials_service import validate_url

    # v0.8.?? — final outbound SSRF boundary. Registry rows can predate URL
    # validation or be edited directly, so create/test validation is not
    # sufficient. Reuse the credential URL policy immediately before opening
    # the transport; this preserves explicitly allowed loopback/private local
    # plugins while blocking link-local and unsupported schemes on every path.
    await asyncio.to_thread(validate_url, url, "mcp")

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
                return [tool["name"] for tool in _bounded_tool_specs(getattr(result, "tools", []))]
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
                return _bounded_tool_specs(getattr(result, "tools", []))
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
            raw_content = getattr(result, "content", [])
            content = _bounded_iterable(raw_content, _MAX_CONTENT_BLOCKS)

            blocks: list[dict] = []
            text_chunks: list[str] = []
            remaining_text = _MAX_RESULT_TEXT_CHARS
            remaining_binary = _MAX_RESULT_BINARY_CHARS

            for block in content:
                try:
                    # TextContent — `.text` is a plain string.
                    if hasattr(block, "text") and not hasattr(block, "resource"):
                        txt = getattr(block, "text", "")
                        if isinstance(txt, str):
                            allowed = min(_MAX_TEXT_CHARS, remaining_text)
                            txt = txt[:allowed]
                            remaining_text -= len(txt)
                            blocks.append({"type": "text", "text": txt})
                            text_chunks.append(txt)
                        continue

                    # ImageContent — `.data` is base64, `.mimeType` is e.g.
                    # "image/png". `bytes` is an approximate decoded size.
                    if hasattr(block, "data") and not hasattr(block, "resource"):
                        data = getattr(block, "data", "")
                        if not isinstance(data, str):
                            continue
                        allowed = min(_MAX_BINARY_CHARS, remaining_binary)
                        data = data[:allowed]
                        remaining_binary -= len(data)
                        mime = getattr(block, "mimeType", None)
                        mime = (
                            mime[:_MAX_MIME_CHARS]
                            if isinstance(mime, str) and mime
                            else "application/octet-stream"
                        )
                        approx = max(0, len(data) * 3 // 4)
                        blocks.append({
                            "type": "image",
                            "mime_type": mime,
                            "data": data,
                            "bytes": approx,
                        })
                        text_chunks.append(f"[image: {mime}, ~{approx} bytes]")
                        continue

                    # EmbeddedResource — `.resource` has `.uri`, `.mimeType`,
                    # and either `.text` or `.blob`.
                    if hasattr(block, "resource"):
                        res = block.resource
                        uri = getattr(res, "uri", "")
                        uri = str(uri)[:_MAX_URI_CHARS] if uri else ""
                        mime = getattr(res, "mimeType", None)
                        mime = mime[:_MAX_MIME_CHARS] if isinstance(mime, str) else ""
                        res_text = getattr(res, "text", None)
                        res_blob = getattr(res, "blob", None)
                        entry: dict = {
                            "type": "resource",
                            "uri": uri,
                            "mime_type": mime,
                        }
                        if isinstance(res_text, str):
                            allowed = min(_MAX_TEXT_CHARS, remaining_text)
                            entry["text"] = res_text[:allowed]
                            remaining_text -= len(entry["text"])
                            text_chunks.append(entry["text"])
                        elif isinstance(res_blob, str):
                            allowed = min(_MAX_BINARY_CHARS, remaining_binary)
                            res_blob = res_blob[:allowed]
                            remaining_binary -= len(res_blob)
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

                    blocks.append({"type": "unknown", "repr": _safe_repr(block)})
                except Exception:
                    # One malformed block must not discard valid siblings or
                    # abort the chat turn.
                    blocks.append({"type": "unknown", "repr": _safe_repr(block)})

            return {
                "ok": True,
                "text": "\n".join(c for c in text_chunks if c)[:_MAX_TEXT_CHARS],
                "blocks": blocks,
            }
