# desktop/first_run/server.py
"""First-run wizard: tiny aiohttp app serving 4 static screens.

Only used the very first time the app boots (no config.toml exists). Once the
user clicks Done, the wizard writes the config and signals completion.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from aiohttp import web

from desktop.config import Config

if TYPE_CHECKING:
    from desktop.progress import ProgressBus

_VALID_PROVIDERS = {"ollama", "llamacpp", "none"}
STATIC_DIR = Path(__file__).parent / "static"


def build_app(config_path: Path, on_done: Callable[[], None],
              progress_bus: "ProgressBus | None" = None) -> web.Application:
    app = web.Application()

    async def index(_: web.Request) -> web.Response:
        return web.FileResponse(STATIC_DIR / "index.html")

    async def save(req: web.Request) -> web.Response:
        body = await req.json()
        provider = body.get("provider", "none")
        if provider not in _VALID_PROVIDERS:
            return web.json_response({"error": "invalid provider"}, status=400)
        # Server-side expansion of ~ and %USERPROFILE% — the browser can't see
        # the user's home dir so JS can't expand them reliably.
        raw_dir = body["model_dir"]
        if raw_dir.startswith("%USERPROFILE%"):
            import os
            raw_dir = os.environ.get("USERPROFILE", str(Path.home())) + raw_dir[len("%USERPROFILE%"):]
        model_dir = Path(raw_dir).expanduser()
        cfg = Config(
            model_dir=model_dir,
            provider=provider,
            default_model=body.get("default_model", ""),
            surreal_user="root",
            surreal_password=secrets.token_urlsafe(24),
            theme=body.get("theme", "light-blue"),
            encryption_key=secrets.token_urlsafe(32),
        )
        cfg.save(config_path)
        on_done()
        return web.json_response({"ok": True})

    async def progress_stream(req: web.Request) -> web.StreamResponse:
        if progress_bus is None:
            return web.json_response({"error": "no progress bus"}, status=503)
        resp = web.StreamResponse(status=200, headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        })
        await resp.prepare(req)
        loop = asyncio.get_event_loop()
        q: asyncio.Queue = asyncio.Queue()

        def reader():
            for evt in progress_bus.subscribe(timeout=120.0, replay=True):
                loop.call_soon_threadsafe(q.put_nowait, evt)
            loop.call_soon_threadsafe(q.put_nowait, None)

        threading.Thread(target=reader, daemon=True).start()

        while True:
            evt = await q.get()
            if evt is None:
                break
            await resp.write(f"data: {json.dumps(evt)}\n\n".encode())
            if evt["step"] == "ready" and evt["status"] == "done":
                break
        await resp.write_eof()
        return resp

    app.router.add_get("/", index)
    app.router.add_get("/api/progress", progress_stream)
    app.router.add_post("/api/save", save)
    app.router.add_static("/static", STATIC_DIR)
    return app


def run_wizard_blocking(config_path: Path,
                        progress_bus: "ProgressBus | None" = None) -> None:
    """Open the wizard in PyWebView; return once the user clicks Done."""
    import asyncio
    import threading

    import webview

    done = threading.Event()
    runner_loop: asyncio.AbstractEventLoop | None = None
    runner: web.AppRunner | None = None
    site_port = 0

    def serve():
        nonlocal runner_loop, runner, site_port
        runner_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(runner_loop)
        app = build_app(config_path, on_done=done.set, progress_bus=progress_bus)
        runner = web.AppRunner(app)
        runner_loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, "127.0.0.1", 0)
        runner_loop.run_until_complete(site.start())
        site_port = site._server.sockets[0].getsockname()[1]
        runner_loop.run_forever()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    while site_port == 0:
        import time as _t
        _t.sleep(0.05)

    window = webview.create_window("Open Notebook Plus — Setup",
                                   f"http://127.0.0.1:{site_port}/",
                                   width=720, height=540)
    def _watch_done():
        import time as _t
        while not done.is_set():
            _t.sleep(0.2)
        window.destroy()
    threading.Thread(target=_watch_done, daemon=True).start()
    webview.start()

    if runner_loop is not None and runner is not None:
        runner_loop.call_soon_threadsafe(runner_loop.stop)
