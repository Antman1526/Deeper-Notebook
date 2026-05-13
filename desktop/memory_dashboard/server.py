"""Aiohttp server backing the Memory Dashboard PyWebView window.

Most data requests proxy through to the memory retriever shim (which has the
mem0 client). This server itself is thin — just serves the static UI and
provides a /api/theme endpoint so the dashboard adopts the user's wizard theme.
"""
from __future__ import annotations

from pathlib import Path

import httpx
from aiohttp import web

STATIC_DIR = Path(__file__).parent / "static"


def build_app(
    memory_retriever_url: str,
    *,
    openchronicle_bridge_url: str = "",
) -> web.Application:
    """Build the dashboard aiohttp app.

    memory_retriever_url      — http://127.0.0.1:<memory_port>/  (mem0 + writer)
    openchronicle_bridge_url  — http://127.0.0.1:<openchronicle_port>/ if the
                                bridge spawned, else "" (Capture Inbox shows
                                an empty/unavailable state).
    """
    app = web.Application()

    async def index(_: web.Request) -> web.Response:
        idx = STATIC_DIR / "index.html"
        if idx.exists():
            return web.FileResponse(idx)
        return web.Response(
            text="<html><body>Memory dashboard (static UI not built yet)</body></html>",
            content_type="text/html",
        )

    async def proxy(req: web.Request) -> web.Response:
        """Proxy /api/memory/* to the retriever shim."""
        path = req.match_info["path"]
        url = f"{memory_retriever_url}/api/memory/{path}"
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                if req.method == "GET":
                    r = await client.get(url, params=dict(req.query))
                elif req.method == "DELETE":
                    r = await client.delete(url)
                elif req.method == "POST":
                    body = await req.json() if req.body_exists else None
                    r = await client.post(url, json=body)
                else:
                    return web.Response(status=405, text="method not allowed")
                return web.Response(
                    status=r.status_code,
                    body=r.content,
                    content_type=r.headers.get("content-type", "application/json"),
                )
            except Exception as exc:
                return web.json_response({"error": str(exc)}, status=502)

    # --- ONP v0.5 — Capture Inbox -----------------------------------------
    # The inbox shows recent OpenChronicle screen events so the user can curate
    # them BEFORE they commit to memory. If the bridge isn't running (user
    # chose "skip" in the wizard or hasn't installed OC), this returns an
    # empty list — the dashboard then renders an "OpenChronicle not available"
    # state instead of an error.

    async def capture_inbox(req: web.Request) -> web.Response:
        if not openchronicle_bridge_url:
            return web.json_response(
                {"available": False, "events": [], "reason": "openchronicle not detected"}
            )
        minutes = int(req.query.get("minutes", "30"))
        url = f"{openchronicle_bridge_url}/context/recent"
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                r = await client.get(url, params={"minutes": minutes})
                r.raise_for_status()
                payload = r.json()
                events = payload.get("events") if isinstance(payload, dict) else payload
                return web.json_response({"available": True, "events": list(events or [])})
            except Exception as exc:
                return web.json_response(
                    {"available": True, "events": [], "error": str(exc)},
                    status=502,
                )

    async def theme(_: web.Request) -> web.Response:
        try:
            from desktop.config import default_config_path, load_or_create
            cfg = load_or_create(default_config_path())
            return web.json_response({"theme": cfg.theme})
        except Exception:
            return web.json_response({"theme": "light-blue"})

    app.router.add_get("/", index)
    app.router.add_get("/api/memory/{path:.+}", proxy)
    app.router.add_delete("/api/memory/{path:.+}", proxy)
    app.router.add_post("/api/memory/{path:.+}", proxy)
    app.router.add_get("/api/capture/inbox", capture_inbox)
    app.router.add_get("/api/theme", theme)
    if STATIC_DIR.exists():
        app.router.add_static("/static", STATIC_DIR)
    return app
