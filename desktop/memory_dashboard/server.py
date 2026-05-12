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


def build_app(memory_retriever_url: str) -> web.Application:
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
    app.router.add_get("/api/theme", theme)
    if STATIC_DIR.exists():
        app.router.add_static("/static", STATIC_DIR)
    return app
