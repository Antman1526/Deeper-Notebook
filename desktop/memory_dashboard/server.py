"""Aiohttp server backing the Memory Dashboard PyWebView window.

Most data requests proxy through to the memory retriever shim (which has the
mem0 client). This server itself is thin — just serves the static UI and
provides a /api/theme endpoint so the dashboard adopts the user's wizard theme.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from aiohttp import web

STATIC_DIR = Path(__file__).parent / "static"


# P1-HIGH-05 audit fix: persist a single timestamp marking the last "Recent
# capture" event the user acknowledged (approve/dismiss/mark-seen). On reload
# the inbox only shows events after this timestamp, so it doesn't become a
# wall of already-triaged items. Survives app restart; user-deletable.
def _capture_state_path() -> Path:
    base = Path(os.environ.get("HOME", os.environ.get("USERPROFILE", ".")))
    return base / ".open-notebook-plus" / "capture_state.json"


def _load_last_seen() -> str:
    p = _capture_state_path()
    if not p.exists():
        return ""
    try:
        return json.loads(p.read_text()).get("last_seen", "")
    except Exception:
        return ""


def _save_last_seen(ts: str) -> None:
    p = _capture_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(json.dumps({"last_seen": ts}))
    except Exception:
        pass  # best-effort; missing-state means inbox just shows more


def build_app(
    memory_retriever_url: str,
    *,
    openchronicle_bridge_url: str = "",
    upstream_api_url: str = "",
) -> web.Application:
    """Build the dashboard aiohttp app.

    memory_retriever_url      — http://127.0.0.1:<memory_port>/  (mem0 + writer)
    openchronicle_bridge_url  — http://127.0.0.1:<openchronicle_port>/ if the
                                bridge spawned, else "" (Capture Inbox shows
                                an empty/unavailable state).
    upstream_api_url          — http://127.0.0.1:<api_port>      (FastAPI;
                                feeds the 'Active models' panel which shows
                                which model fills each role slot).
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
                events = list(events or [])
                # P1-HIGH-05: filter out events already acknowledged in past
                # sessions. Events with no `ts` always pass (we can't compare).
                last_seen = _load_last_seen()
                if last_seen:
                    events = [e for e in events
                              if not e.get("ts") or e["ts"] > last_seen]
                return web.json_response({"available": True, "events": events,
                                          "last_seen": last_seen})
            except Exception as exc:
                return web.json_response(
                    {"available": True, "events": [], "error": str(exc)},
                    status=502,
                )

    async def capture_mark_seen(req: web.Request) -> web.Response:
        """Update the last-seen watermark. Posted by dashboard.js when the user
        clicks 'Mark all as seen' OR after a successful approve/dismiss.
        """
        try:
            body = await req.json()
        except Exception:
            body = {}
        ts = (body.get("ts") or "").strip()
        if not ts:
            return web.json_response({"error": "ts required"}, status=400)
        _save_last_seen(ts)
        return web.json_response({"ok": True, "last_seen": ts})

    async def active_models(_: web.Request) -> web.Response:
        """Resolve each DefaultModels slot → human-readable model name.

        The dashboard surfaces this at the top so users see which model is
        currently doing what (chat / tools / reasoning / etc.) without
        having to context-switch to the Settings → Models page.
        """
        if not upstream_api_url:
            return web.json_response({"available": False, "slots": {}})
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                defaults_resp, models_resp = await client.get(
                    f"{upstream_api_url}/api/models/defaults"
                ), await client.get(f"{upstream_api_url}/api/models")
                defaults_resp.raise_for_status()
                models_resp.raise_for_status()
                defaults = defaults_resp.json() or {}
                models = models_resp.json() or []
        except Exception as exc:
            return web.json_response(
                {"available": False, "slots": {}, "error": str(exc)},
                status=502,
            )
        # id → name lookup for human-readable display
        id_to_name = {m.get("id", ""): m.get("name", "") for m in models}
        # Order matches the Settings panel for consistency.
        slot_to_field = [
            ("Chat",            "default_chat_model"),
            ("Tools",           "default_tools_model"),
            ("Reasoning",       "default_reasoning_model"),
            ("Transformation",  "default_transformation_model"),
            ("Large Context",   "large_context_model"),
            ("Embedding",       "default_embedding_model"),
            ("Text-to-Speech",  "default_text_to_speech_model"),
            ("Speech-to-Text",  "default_speech_to_text_model"),
        ]
        slots = {}
        for label, field in slot_to_field:
            v = defaults.get(field)
            slots[label] = id_to_name.get(v, v) if v else None
        return web.json_response({"available": True, "slots": slots})

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
    app.router.add_post("/api/capture/mark_seen", capture_mark_seen)
    app.router.add_get("/api/dashboard/active-models", active_models)
    app.router.add_get("/api/theme", theme)
    if STATIC_DIR.exists():
        app.router.add_static("/static", STATIC_DIR)
    return app
