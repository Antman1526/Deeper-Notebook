"""Minimal loopback-only MCP plugin for Deeper Notebook development.

Run with ``uv run python examples/mcp_local_streamable_http.py`` and register
``http://127.0.0.1:8765/mcp`` in Settings -> MCP Servers.  This process is
intentionally external to Deeper Notebook so registration and failure
isolation can be exercised without an in-process code loader.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

_DEFAULT_PORT = 8765


def _port() -> int:
    raw = os.environ.get("DEEPER_NOTEBOOK_MCP_EXAMPLE_PORT", "")
    try:
        port = int(raw)
    except ValueError:
        return _DEFAULT_PORT
    return port if 1024 <= port <= 65535 else _DEFAULT_PORT


mcp = FastMCP(
    "deeper-notebook-local-example",
    instructions="Small local plugin used to verify MCP registration.",
    host="127.0.0.1",
    port=_port(),
    streamable_http_path="/mcp",
    stateless_http=True,
)


@mcp.tool()
def local_echo(text: str) -> str:
    """Return a bounded echo for connectivity and tool-call checks."""
    return text[:2048]


@mcp.tool()
def local_status() -> dict[str, bool | str]:
    """Return a small, deterministic plugin status record."""
    return {"ok": True, "plugin": "deeper-notebook-local-example"}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
