"""ONP v0.6.17 — Tests for start_aiohttp_server_thread.

The previous implementation silently swallowed every server-startup
exception, leaving the caller with site_port=0 and no clue what went
wrong. These tests confirm:
  - happy path: real aiohttp server binds + returns a working port
  - factory raises → caller gets a clear RuntimeError (not blank window)
  - timeout path → caller gets TimeoutError
"""

from __future__ import annotations

import socket
import time

import pytest
from aiohttp import web

from desktop.aiohttp_window import start_aiohttp_server_thread


def _make_simple_app() -> web.Application:
    app = web.Application()

    async def hello(_request):
        return web.json_response({"ok": True})

    app.router.add_get("/", hello)
    return app


def test_starts_real_server_and_returns_bound_port():
    port, thread, loop, runner = start_aiohttp_server_thread(_make_simple_app)
    try:
        assert port > 0
        assert thread.is_alive()
        # Sanity: socket actually open
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(("127.0.0.1", port))
        s.close()
    finally:
        # Best-effort shutdown
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)


def test_factory_exception_surfaces_as_runtime_error():
    """The bug we just fixed: a factory that raises used to leave the caller
    with port=0 after 5s. Now it raises a clear RuntimeError quickly."""

    def _bad_factory():
        raise RuntimeError("simulated factory boom")

    with pytest.raises(RuntimeError, match=r"factory boom"):
        start_aiohttp_server_thread(_bad_factory, startup_timeout_s=2.0)


def test_setup_exception_during_runner_setup_propagates():
    """A factory that returns an app that fails at runner.setup() time —
    e.g. an on_startup handler raises. Must surface as RuntimeError."""

    def _on_startup_raises(_app):
        raise ValueError("startup signal raised")

    def _factory():
        app = web.Application()
        app.on_startup.append(_on_startup_raises)
        return app

    with pytest.raises(RuntimeError) as exc:
        start_aiohttp_server_thread(_factory, startup_timeout_s=2.0)
    # Inner cause exposed in message
    assert "startup signal raised" in str(exc.value)


def test_timeout_raises_clear_error_when_server_hangs():
    """If app_factory hangs indefinitely we eventually give up with a
    timeout. Picking a short timeout keeps the test fast."""

    def _slow_factory():
        time.sleep(2.0)  # exceeds the 0.3s timeout below
        return _make_simple_app()

    with pytest.raises((TimeoutError, RuntimeError)):
        start_aiohttp_server_thread(_slow_factory, startup_timeout_s=0.3)
