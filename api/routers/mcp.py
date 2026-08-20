"""Phase 2 Task 9 — /api/mcp CRUD router.

Admin-only endpoints (auth-protected by PasswordAuthMiddleware)
for managing MCP server registry rows. Read by the Settings UI
in Task 10 and by the chat-graph node in Task 8.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# v0.8.68 — surrealdb 2.0 raises its own SurrealError subclass
# (InvalidRecordIdError) from RecordID.parse instead of ValueError, so the
# v0.8.66 H2/H3 `except (ValueError, TypeError)` guards stopped catching a
# malformed id — the client got an opaque 500 instead of the intended clean
# 400. Catch the library's error class alongside the stdlib ones; the
# fallback keeps imports working if a future client drops the module path.
try:
    from surrealdb.errors import SurrealError as _SurrealIdError
except ImportError:  # pragma: no cover — older surrealdb clients

    class _SurrealIdError(Exception):
        pass


_BAD_RECORD_ID_ERRORS = (ValueError, TypeError, _SurrealIdError)

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
    from deeper_notebook.database.repository import repo_query

    rows = await repo_query("SELECT id, name, url, enabled FROM mcp_server")
    return rows or []


@router.get("/api/mcp/recommendations")
async def list_mcp_recommendations():
    """v0.8.41 — Curated MCP server recommendations.

    Static list maintained in
    `deeper_notebook/mcp/recommendations.py:RECOMMENDATIONS`. Mirrors the
    shape of the v0.8.39b GGUF recommendations endpoint — frontend
    renders each as a one-click "Connect" card on the MCP settings
    page. The user has to install the server externally (Docker, npm,
    Python — link is in `install_url`); Connect just pre-fills the
    new-server form with `(label, default_url)` and POSTs to the
    existing `POST /api/mcp` create endpoint.

    Selection inspired by the XDA Developers article on local-LLM
    stacks; we skipped picks we already cover server-side (Mem0,
    Qdrant, sentence-transformers) or that don't fit our research-
    assistant use case (Context7 — code-doc lookup).
    """
    from deeper_notebook.mcp.recommendations import RECOMMENDATIONS

    return {"recommendations": RECOMMENDATIONS}


@router.get("/api/mcp/web-search")
async def web_search_status():
    """v0.8.65 — availability of the built-in `web_search` chat tool.

    The tool is bound into the chat tool loop (independently of any MCP server)
    whenever a provider is configured via env — SERPER_API_KEY / TAVILY_API_KEY
    / SEARXNG_BASE_URL. It isn't a registry row, so the chat MCP picker can't
    discover it from `GET /api/mcp`. This endpoint lets the picker render a
    synthetic `web_search` toggle (and name the active provider) so the user
    can SEE it's on and disable it per-turn via `disabled_mcp_servers`.

    Returns ``{enabled, provider, tool_name}``. No secrets — provider is a
    label (serper/tavily/searxng/wikipedia), never the key.

    v0.8.82 — also reports the keyless ``scholarly_search`` tool
    (``scholarly_enabled`` / ``scholarly_tool_name``) so the picker can offer
    a per-turn off-switch for it too; an always-on network tool must not be
    the one tool the picker can't untick.
    """
    from deeper_notebook.tools.scholarly_search import (
        SCHOLARLY_SEARCH_TOOL_NAME,
        scholarly_search_enabled,
    )
    from deeper_notebook.tools.web_search import (
        WEB_SEARCH_TOOL_NAME,
        active_provider,
        web_search_enabled,
    )

    return {
        "enabled": web_search_enabled(),
        "provider": active_provider(),
        "tool_name": WEB_SEARCH_TOOL_NAME,
        "scholarly_enabled": scholarly_search_enabled(),
        "scholarly_tool_name": SCHOLARLY_SEARCH_TOOL_NAME,
    }


@router.post("/api/mcp", status_code=201)
async def create_mcp_server(body: MCPServerCreate):
    """Register a new MCP server.

    v0.8.0 Task 9 — uses repo_create (not repo_upsert); the correct
    create-new-record primitive. Auto-adds timestamps, returns the
    new record with its generated id.

    Raises 409 if the mcp_server_name_unique index fires (Migration 17).
    """
    from deeper_notebook.database.repository import repo_create
    from deeper_notebook.security.mcp_transport import validate_mcp_url

    # v0.8.66 (audit H4) — validate and resolve before persisting. The stored
    # URL is later fetched outbound by /test and the chat tool loop; the same
    # lower-layer policy is also re-run at that transport boundary.
    try:
        await validate_mcp_url(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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
        if (
            "unique" in exc_str
            or "duplicate" in exc_str
            or "already contains" in exc_str
        ):
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
    from deeper_notebook.database.repository import ensure_record_id, repo_update

    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(400, "No fields to update")
    # v0.8.66 (audit H2) — coerce the client-supplied path param to a real
    # RecordID BEFORE it reaches repo_update. Previously the raw string was
    # interpolated into `UPDATE {record_id} MERGE $data`, so
    # `server_id="mcp_server:x; DELETE notebook; --"` composed a second
    # statement that SurrealDB's multi-statement query() executed. ensure_
    # record_id parses+escapes the record portion; repo_update now also binds
    # it as $rid (defense in depth). A malformed id yields a clean 400.
    try:
        rid = ensure_record_id(server_id)
    except _BAD_RECORD_ID_ERRORS:
        raise HTTPException(400, "Invalid server_id")
    # v0.8.1 — repo_update(table, id, data) auto-bumps `updated`; we only
    # set the fields the caller actually sent so enabled and priority can
    # each be changed independently without clobbering the other.
    result = await repo_update("mcp_server", rid, fields)
    # repo_update returns a list from repo_query; normalise to dict.
    if isinstance(result, list):
        return result[0] if result else {}
    return result


@router.delete("/api/mcp/{server_id}")
async def delete_mcp_server(server_id: str):
    """Remove an MCP server row by id."""
    from deeper_notebook.database.repository import ensure_record_id, repo_query

    # v0.8.66 (audit H3) — a SurrealDB record `id` column is a RecordID; the
    # comparison `id = $id` is FALSE when `$id` is bound as a plain string, so
    # the previous `{"id": server_id}` DELETE matched 0 rows and silently
    # returned ok:true while the row survived (the UI showed a false success
    # toast and the server reappeared on refetch). Bind a real RecordID to fix.
    try:
        rid = ensure_record_id(server_id)
    except _BAD_RECORD_ID_ERRORS:
        raise HTTPException(400, "Invalid server_id")
    await repo_query("DELETE mcp_server WHERE id = $id", {"id": rid})
    return {"ok": True}


@router.post("/api/mcp/{server_id}/test")
async def test_mcp_server(server_id: str):
    """Probe the MCP server and return its list_tools result.

    Returns ``{"ok": True, "tools": [...]}`` on success or
    ``{"ok": False, "error": "..."}`` on failure so the Settings UI
    can render a connectivity badge without catching exceptions on the
    client side.
    """
    from deeper_notebook.database.repository import ensure_record_id, repo_query
    from deeper_notebook.mcp.client import MCPClient
    from deeper_notebook.security.mcp_transport import validate_mcp_url

    # v0.8.66 (audit H3) — bind a RecordID, not a string, or the SELECT matches
    # 0 rows and Test 404s on a server that genuinely exists.
    try:
        rid = ensure_record_id(server_id)
    except _BAD_RECORD_ID_ERRORS:
        raise HTTPException(400, "Invalid server_id")
    rows = await repo_query(
        "SELECT url FROM mcp_server WHERE id = $id LIMIT 1",
        {"id": rid},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="MCP server not found")

    # v0.8.66 (audit H4) — re-validate the stored URL before the outbound fetch
    # so a row that predates create-time validation (or was written by a direct
    # DB edit) can't be abused for SSRF via the Test button.
    try:
        await validate_mcp_url(rows[0]["url"])
    except ValueError as exc:
        return {"ok": False, "error": str(exc)[:200]}

    client = MCPClient(url=rows[0]["url"])
    try:
        names = await client.list_tool_names()
        return {"ok": True, "tools": names}
    except Exception as exc:
        # v0.8.0 — return shape-stable response so the UI can show a
        # "test failed" badge without parsing exceptions on the client.
        return {"ok": False, "error": str(exc)[:200]}
