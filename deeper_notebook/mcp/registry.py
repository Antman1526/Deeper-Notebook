"""Phase 2 — MCP server registry, DB-backed.

Reads from the `mcp_server` SurrealDB table (migration 17). The
chat graph calls `list_enabled_servers()` once per turn to
discover which MCP endpoints to expose as tools.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit

_MAX_MCP_SERVERS = 32
_MAX_SERVER_NAME_CHARS = 128
_MAX_SERVER_URL_CHARS = 2048
_SERVER_FIELDS = ("id", "name", "url", "enabled", "priority", "created")


def _project_server(row: object) -> dict | None:
    if not isinstance(row, Mapping) or row.get("enabled") is not True:
        return None
    name = row.get("name")
    url = row.get("url")
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(url, str) or len(url.strip()) > _MAX_SERVER_URL_CHARS:
        return None
    name = name.strip()
    url = url.strip()
    if len(name) > _MAX_SERVER_NAME_CHARS:
        return None
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
    except ValueError:
        return None
    # Do not call ``dict(row)`` here.  A database adapter normally returns a
    # plain dict, but this boundary is still third-party input and a custom
    # Mapping can materialise an unbounded iterator (or raise while iterating).
    # Project only the fields selected by the query, with a fixed number of
    # guarded lookups, so the bound happens before any copy/materialisation.
    projected: dict[str, object] = {}
    for key in _SERVER_FIELDS:
        try:
            if key in row:
                projected[key] = row.get(key)
        except Exception:
            continue
    projected["name"] = name
    projected["url"] = url
    return projected


async def list_enabled_servers() -> list[dict]:
    from deeper_notebook.database.repository import repo_query

    # v0.8.1 — sort by priority ASC then created ASC so the chat graph's
    # servers[0] pick is deterministic: the operator's explicitly preferred
    # server wins over insertion-order. Tied priorities fall back to created
    # timestamp (stable across page loads). New rows default to priority=100
    # (migration 19); existing rows kept at 100 by the DEFAULT clause so no
    # data changes — the effective order is unchanged unless the operator
    # explicitly reorders via PATCH /api/mcp/{id}.
    try:
        rows = await repo_query(
            "SELECT id, name, url, enabled, priority, created FROM mcp_server "
            "WHERE enabled = true "
            "ORDER BY priority ASC, created ASC",
        )
    except Exception:
        # MCP is an optional extension surface; a registry/DB hiccup must not
        # make the chat turn fail when native tools remain available.
        return []
    if not isinstance(rows, (list, tuple)):
        return []
    servers: list[dict] = []
    for row in rows:
        projected = _project_server(row)
        if projected is None:
            continue
        servers.append(projected)
        if len(servers) >= _MAX_MCP_SERVERS:
            break
    return servers
