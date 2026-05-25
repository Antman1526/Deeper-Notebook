"""Phase 2 Task 9 — /api/mcp CRUD router.

Admin-only endpoints (auth-protected by PasswordAuthMiddleware)
for managing MCP server registry rows. Read by the Settings UI
in Task 10 and by the chat-graph node in Task 8.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class MCPServerCreate(BaseModel):
    name: str
    url: str  # NB: keep as str, not HttpUrl, so localhost/loopback work
    enabled: bool = True


@router.get("/api/mcp")
async def list_mcp_servers():
    """Return all registered MCP servers with id, name, url, enabled."""
    from open_notebook.database.repository import repo_query

    rows = await repo_query("SELECT id, name, url, enabled FROM mcp_server")
    return rows or []


@router.post("/api/mcp", status_code=201)
async def create_mcp_server(body: MCPServerCreate):
    """Register a new MCP server.

    v0.8.0 Task 9 — uses repo_create (not repo_upsert); the correct
    create-new-record primitive. Auto-adds timestamps, returns the
    new record with its generated id.

    Raises 409 if the mcp_server_name_unique index fires (Migration 17).
    """
    from open_notebook.database.repository import repo_create

    try:
        result = await repo_create("mcp_server", body.model_dump())
        # repo_create may return a dict or a list[dict]; normalise to dict.
        if isinstance(result, list):
            return result[0]
        return result
    except Exception as exc:
        # v0.8.0 — mcp_server_name_unique index raises on duplicate names.
        exc_str = str(exc).lower()
        if "unique" in exc_str or "duplicate" in exc_str or "already contains" in exc_str:
            raise HTTPException(
                status_code=409,
                detail="An MCP server with that name already exists",
            )
        raise


@router.delete("/api/mcp/{server_id}")
async def delete_mcp_server(server_id: str):
    """Remove an MCP server row by id."""
    from open_notebook.database.repository import repo_query

    await repo_query("DELETE mcp_server WHERE id = $id", {"id": server_id})
    return {"ok": True}


@router.post("/api/mcp/{server_id}/test")
async def test_mcp_server(server_id: str):
    """Probe the MCP server and return its list_tools result.

    Returns ``{"ok": True, "tools": [...]}`` on success or
    ``{"ok": False, "error": "..."}`` on failure so the Settings UI
    can render a connectivity badge without catching exceptions on the
    client side.
    """
    from open_notebook.database.repository import repo_query
    from open_notebook.mcp.client import MCPClient

    rows = await repo_query(
        "SELECT url FROM mcp_server WHERE id = $id LIMIT 1",
        {"id": server_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="MCP server not found")

    client = MCPClient(url=rows[0]["url"])
    try:
        names = await client.list_tool_names()
        return {"ok": True, "tools": names}
    except Exception as exc:
        # v0.8.0 — return shape-stable response so the UI can show a
        # "test failed" badge without parsing exceptions on the client.
        return {"ok": False, "error": str(exc)[:200]}
