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

from desktop.data_root import active_data_root

STATIC_DIR = Path(__file__).parent / "static"


# P1-HIGH-05 audit fix: persist a single timestamp marking the last "Recent
# capture" event the user acknowledged (approve/dismiss/mark-seen). On reload
# the inbox only shows events after this timestamp, so it doesn't become a
# wall of already-triaged items. Survives app restart; user-deletable.
def _capture_state_path() -> Path:
    return active_data_root() / "capture_state.json"


def _load_capture_state() -> dict:
    """Returns full capture state dict: {last_seen, muted_apps}."""
    p = _capture_state_path()
    if not p.exists():
        return {"last_seen": "", "muted_apps": []}
    try:
        data = json.loads(p.read_text())
        return {
            "last_seen": data.get("last_seen", ""),
            "muted_apps": list(data.get("muted_apps", [])),
        }
    except Exception:
        return {"last_seen": "", "muted_apps": []}


def _save_capture_state(state: dict) -> None:
    """Writes the full state dict back. Best-effort — missing state just
    means the inbox shows more events.

    v0.6.27 — atomic write. The previous `p.write_text(...)` was a single
    open-truncate-write-close sequence; if the launcher crashed mid-write
    (sigkill, OOM, host shutdown), the file was left half-written.
    `_load_capture_state` then caught the JSON decode error and silently
    returned the default empty state — losing the user's muted_apps list.
    Now we write to a sibling .tmp file and os.replace into place; the
    visible file is always either the old complete content or the new
    complete content, never partial.
    """
    p = _capture_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "last_seen": state.get("last_seen", ""),
            "muted_apps": sorted(set(state.get("muted_apps", []))),
        }
    )
    tmp = p.with_suffix(p.suffix + ".tmp")
    try:
        tmp.write_text(payload)
        os.replace(tmp, p)
    except Exception:
        # Clean up any leftover .tmp so the next save isn't blocked by
        # a stale temp file (rare but possible if write succeeded and
        # replace failed).
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


# Legacy helpers — preserved for tests that previously called them directly.
def _load_last_seen() -> str:
    return _load_capture_state().get("last_seen", "")


def _save_last_seen(ts: str) -> None:
    state = _load_capture_state()
    state["last_seen"] = ts
    _save_capture_state(state)


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

    # ONP v0.5.5 perf — reuse a single httpx client for the lifetime of the
    # dashboard server. Previously every proxy/inbox/active-models call did
    # `async with httpx.AsyncClient(...)` which incurs TCP + TLS handshake
    # overhead per request (~30-50 ms locally). One pool, one connection.
    shared_client = httpx.AsyncClient(timeout=10)

    async def _cleanup(_: web.Application) -> None:
        await shared_client.aclose()

    app.on_cleanup.append(_cleanup)

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
        try:
            if req.method == "GET":
                r = await shared_client.get(url, params=dict(req.query))
            elif req.method == "DELETE":
                r = await shared_client.delete(url)
            elif req.method == "POST":
                body = await req.json() if req.body_exists else None
                r = await shared_client.post(url, json=body)
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
                {
                    "available": False,
                    "events": [],
                    "reason": "openchronicle not detected",
                }
            )
        minutes = int(req.query.get("minutes", "30"))
        url = f"{openchronicle_bridge_url}/context/recent"
        try:
            r = await shared_client.get(url, params={"minutes": minutes}, timeout=5)
            r.raise_for_status()
            payload = r.json()
            events = payload.get("events") if isinstance(payload, dict) else payload
            events = list(events or [])
            state = _load_capture_state()
            # P1-HIGH-05: filter out events already acknowledged in past
            # sessions. Events with no `ts` always pass (we can't compare).
            last_seen = state.get("last_seen", "")
            if last_seen:
                events = [e for e in events if not e.get("ts") or e["ts"] > last_seen]
            # v0.5.8 — per-app mute. Drop events whose `app` field matches
            # any muted app (case-insensitive substring match).
            muted_apps = [a.lower() for a in state.get("muted_apps", [])]
            if muted_apps:
                events = [
                    e
                    for e in events
                    if not any(m in (e.get("app") or "").lower() for m in muted_apps)
                ]
            return web.json_response(
                {
                    "available": True,
                    "events": events,
                    "last_seen": last_seen,
                    "muted_apps": state.get("muted_apps", []),
                }
            )
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

    async def capture_mute(req: web.Request) -> web.Response:
        """v0.5.8 — toggle an app's mute state. Body: {app: "VSCode",
        action: "mute" | "unmute"}. Persists to capture_state.json so the
        rule survives restarts."""
        try:
            body = await req.json()
        except Exception:
            body = {}
        app_name = (body.get("app") or "").strip()
        action = body.get("action", "mute")
        if not app_name:
            return web.json_response({"error": "app required"}, status=400)
        state = _load_capture_state()
        muted = set(state.get("muted_apps", []))
        if action == "mute":
            muted.add(app_name)
        elif action == "unmute":
            muted.discard(app_name)
        else:
            return web.json_response(
                {"error": "action must be mute|unmute"}, status=400
            )
        state["muted_apps"] = sorted(muted)
        _save_capture_state(state)
        return web.json_response({"ok": True, "muted_apps": state["muted_apps"]})

    async def active_models(_: web.Request) -> web.Response:
        """Resolve each DefaultModels slot → human-readable model name.

        The dashboard surfaces this at the top so users see which model is
        currently doing what (chat / tools / reasoning / etc.) without
        having to context-switch to the Settings → Models page.
        """
        if not upstream_api_url:
            return web.json_response({"available": False, "slots": {}})
        try:
            defaults_resp = await shared_client.get(
                f"{upstream_api_url}/api/models/defaults", timeout=5
            )
            models_resp = await shared_client.get(
                f"{upstream_api_url}/api/models", timeout=5
            )
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
            ("Chat", "default_chat_model"),
            ("Tools", "default_tools_model"),
            ("Reasoning", "default_reasoning_model"),
            ("Transformation", "default_transformation_model"),
            ("Large Context", "large_context_model"),
            ("Embedding", "default_embedding_model"),
            ("Text-to-Speech", "default_text_to_speech_model"),
            ("Speech-to-Text", "default_speech_to_text_model"),
        ]
        slots = {}
        for label, field in slot_to_field:
            v = defaults.get(field)
            slots[label] = id_to_name.get(v, v) if v else None
        return web.json_response({"available": True, "slots": slots})

    async def health(_: web.Request) -> web.Response:
        """ONP v0.5.6 — live status of the subsystems the dashboard depends on.

        Hits each subsystem's /health (or equivalent) endpoint with a short
        timeout and reports up/down per service. Surfaced in the dashboard
        footer so users see at a glance if anything's broken without having
        to tail launcher.log.
        """

        async def _probe(
            name: str, url: str, ok_status: int = 200
        ) -> tuple[str, bool, str | None]:
            if not url:
                return (name, False, "not wired")
            try:
                r = await shared_client.get(url, timeout=2)
                return (
                    name,
                    r.status_code == ok_status,
                    None if r.status_code == ok_status else f"HTTP {r.status_code}",
                )
            except Exception as exc:
                return (name, False, type(exc).__name__)

        import asyncio

        results = await asyncio.gather(
            _probe(
                "memory_retriever",
                f"{memory_retriever_url}/health" if memory_retriever_url else "",
            ),
            _probe(
                "upstream_api", f"{upstream_api_url}/health" if upstream_api_url else ""
            ),
            _probe(
                "openchronicle_bridge",
                f"{openchronicle_bridge_url}/health"
                if openchronicle_bridge_url
                else "",
            ),
        )
        services = {name: {"ok": ok, "detail": detail} for name, ok, detail in results}
        all_ok = all(v["ok"] for v in services.values() if v["detail"] != "not wired")
        return web.json_response({"all_ok": all_ok, "services": services})

    async def theme(_: web.Request) -> web.Response:
        try:
            from desktop.config import default_config_path, load_or_create

            cfg = load_or_create(default_config_path())
            return web.json_response({"theme": cfg.theme})
        except Exception:
            return web.json_response({"theme": "research-core-dark"})

    app.router.add_get("/", index)
    app.router.add_get("/api/memory/{path:.+}", proxy)
    app.router.add_delete("/api/memory/{path:.+}", proxy)
    app.router.add_post("/api/memory/{path:.+}", proxy)
    app.router.add_get("/api/capture/inbox", capture_inbox)
    app.router.add_post("/api/capture/mark_seen", capture_mark_seen)
    app.router.add_post("/api/capture/mute", capture_mute)
    app.router.add_get("/api/dashboard/active-models", active_models)
    app.router.add_get("/api/dashboard/health", health)
    app.router.add_get("/api/theme", theme)
    if STATIC_DIR.exists():
        app.router.add_static("/static", STATIC_DIR)
    return app
