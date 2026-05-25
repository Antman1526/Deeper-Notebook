"""Phase 2 — MCP server registry, DB-backed.

Reads from the `mcp_server` SurrealDB table (migration 17). The
chat graph calls `list_enabled_servers()` once per turn to
discover which MCP endpoints to expose as tools.
"""
from __future__ import annotations


async def list_enabled_servers() -> list[dict]:
    from open_notebook.database.repository import repo_query
    # v0.8.1 — sort by priority ASC then created ASC so the chat graph's
    # servers[0] pick is deterministic: the operator's explicitly preferred
    # server wins over insertion-order. Tied priorities fall back to created
    # timestamp (stable across page loads). New rows default to priority=100
    # (migration 19); existing rows kept at 100 by the DEFAULT clause so no
    # data changes — the effective order is unchanged unless the operator
    # explicitly reorders via PATCH /api/mcp/{id}.
    rows = await repo_query(
        "SELECT id, name, url, enabled, priority, created FROM mcp_server "
        "WHERE enabled = true "
        "ORDER BY priority ASC, created ASC",
    )
    # Filter to enabled servers only (defense-in-depth: also filter in Python
    # in case repo_query returns unexpected data)
    return [r for r in (rows or []) if r.get("enabled", False)]
