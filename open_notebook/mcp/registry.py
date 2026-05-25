"""Phase 2 — MCP server registry, DB-backed.

Reads from the `mcp_server` SurrealDB table (migration 17). The
chat graph calls `list_enabled_servers()` once per turn to
discover which MCP endpoints to expose as tools.
"""
from __future__ import annotations


async def list_enabled_servers() -> list[dict]:
    from open_notebook.database.repository import repo_query
    rows = await repo_query(
        "SELECT id, name, url, enabled FROM mcp_server "
        "WHERE enabled = true",
    )
    # Filter to enabled servers only (defense-in-depth: also filter in Python
    # in case repo_query returns unexpected data)
    return [r for r in (rows or []) if r.get("enabled", False)]
