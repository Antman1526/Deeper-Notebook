"""Shared scaffolding for PyWebView windows backed by a local aiohttp server.

Used by:
  - desktop/first_run/server.py        (the first-launch wizard)
  - desktop/model_manager/server.py    (the model-manager window)
  - desktop/__main__.py                (inline model-manager startup)

Each consumer provides:
  - a build_app(...) function returning an aiohttp.web.Application
  - a static_dir Path (auto-mounted at /static)
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Callable

from aiohttp import web


def start_aiohttp_server_thread(
    app_factory: Callable[[], web.Application],
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[int, threading.Thread, asyncio.AbstractEventLoop | None, web.AppRunner | None]:
    """Start an aiohttp server in a daemon thread.

    Returns (bound_port, thread, loop, runner).

    Use the loop + runner to schedule shutdown:
        loop.call_soon_threadsafe(loop.stop)
    The runner can then be cleaned up with:
        loop.run_until_complete(runner.cleanup())
    """
    site_port: list[int] = [0]
    state: dict = {}

    def _serve() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = app_factory()
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, host, port)
        loop.run_until_complete(site.start())
        site_port[0] = site._server.sockets[0].getsockname()[1]
        state["loop"] = loop
        state["runner"] = runner
        loop.run_forever()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    # Wait for the server to bind its port (up to 5 s).
    waited = 0.0
    while site_port[0] == 0 and waited < 5.0:
        time.sleep(0.02)
        waited += 0.02

    return site_port[0], t, state.get("loop"), state.get("runner")
