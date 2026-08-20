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
    startup_timeout_s: float = 5.0,
) -> tuple[
    int, threading.Thread, asyncio.AbstractEventLoop | None, web.AppRunner | None
]:
    """Start an aiohttp server in a daemon thread.

    Returns (bound_port, thread, loop, runner).

    Use the loop + runner to schedule shutdown:
        loop.call_soon_threadsafe(loop.stop)
    The runner can then be cleaned up with:
        loop.run_until_complete(runner.cleanup())

    v0.6.17 — previously this swallowed ALL server-startup exceptions
    silently (the daemon thread just died, leaving site_port[0] = 0).
    Callers (first-run wizard, model manager) then opened a PyWebView
    window at http://127.0.0.1:0/ which loads as a blank failed-to-
    connect page with no error trail. Now:
      - any exception in _serve is captured into state["error"]
      - if startup_timeout_s elapses without binding, we re-raise the
        captured error (or a TimeoutError) so the caller can show a
        real failure message instead of opening a broken window.
    """
    site_port: list[int] = [0]
    state: dict = {}

    def _serve() -> None:
        try:
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
        except BaseException as exc:  # capture EVERYTHING including SystemExit
            state["error"] = exc

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    # Wait for the server to bind its port. Bail early if the thread
    # already failed (no point waiting the full timeout in that case).
    waited = 0.0
    while site_port[0] == 0 and "error" not in state and waited < startup_timeout_s:
        time.sleep(0.02)
        waited += 0.02

    if site_port[0] == 0:
        # Either we timed out OR the server thread threw. Surface the
        # actual exception if we have one, else raise a generic timeout.
        err = state.get("error")
        if err is not None:
            raise RuntimeError(
                f"aiohttp server failed to start: {type(err).__name__}: {err}"
            ) from err
        raise TimeoutError(
            f"aiohttp server did not bind a port within {startup_timeout_s}s"
        )

    return site_port[0], t, state.get("loop"), state.get("runner")
