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


class MCPServerUpdate(BaseModel):
    """v0.8.1 Item 5 — partial-update body for PATCH /api/mcp/{server_id}.

    Both fields are optional; at least one must be present (the router
    rejects an empty body with 400). Using None as sentinel rather than
    model_fields_set so callers can always send a plain JSON object.
    """
    priority: int | None = None
    enabled: bool | None = None


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
    except HTTPException:
        # v0.8.31 — Honor the v0.7.135 meta-test convention: any time
        # an `except Exception → HTTPException(500)` pattern exists, an
        # `except HTTPException: raise` clause must come first to keep
        # typed 4xx/5xx exceptions from being clobbered. Today
        # `repo_create` doesn't raise HTTPException, so the bare `raise`
        # in the generic branch below would still propagate it — but a
        # future refactor of the repo layer that adds typed HTTP errors
        # could regress. Defensive convention. Caught by the v0.7.135
        # AST meta-test in `tests/test_v0_7_135_meta.py`.
        raise
    except Exception as exc:
        # v0.8.0 — mcp_server_name_unique index raises on duplicate names.
        exc_str = str(exc).lower()
        if "unique" in exc_str or "duplicate" in exc_str or "already contains" in exc_str:
            raise HTTPException(
                status_code=409,
                detail="An MCP server with that name already exists",
            )
        raise


@router.patch("/api/mcp/{server_id}")
async def update_mcp_server(server_id: str, body: MCPServerUpdate):
    """Partial update for an MCP server row.

    v0.8.1 Item 5 — accepts ``{priority?: int, enabled?: bool}``.
    Only the fields actually present in the payload are written;
    ``repo_update`` auto-bumps the ``updated`` timestamp.
    Returns 400 when the caller sends an empty body (nothing to write).
    """
    from open_notebook.database.repository import repo_update

    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(400, "No fields to update")
    # v0.8.1 — repo_update(table, id, data) auto-bumps `updated`; we only
    # set the fields the caller actually sent so enabled and priority can
    # each be changed independently without clobbering the other.
    result = await repo_update("mcp_server", server_id, fields)
    # repo_update returns a list from repo_query; normalise to dict.
    if isinstance(result, list):
        return result[0] if result else {}
    return result


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
