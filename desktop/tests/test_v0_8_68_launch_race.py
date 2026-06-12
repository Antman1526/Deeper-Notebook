"""v0.8.68 — launch-race fixes for "This page couldn't load" at startup.

Two halves, both observed live: pywebview navigates exactly once, so if
that single request races the Next.js server the user gets a static error
page with no recovery; and the launcher's frontend gate returned on one
lucky probe of the bare "/" (a 307), not the page the webview actually
loads.
"""
from __future__ import annotations

import threading
import time

import pytest


# ---------------------------------------------------------- load watchdog

class _FakeWindow:
    def __init__(self, fail_first_n: int = 0):
        self.load_calls = 0
        self._fail_first_n = fail_first_n

    def load_url(self, url: str) -> None:
        self.load_calls += 1
        if self.load_calls <= self._fail_first_n:
            raise RuntimeError("window not ready")


def test_watchdog_noop_when_page_loads_within_grace():
    from desktop.window import _start_load_retry_watchdog

    loaded = threading.Event()
    loaded.set()  # page loaded immediately
    win = _FakeWindow()
    t = _start_load_retry_watchdog(
        win, "http://x/", loaded, grace_sec=0.05, retry_interval_sec=0.05
    )
    t.join(timeout=2)
    assert not t.is_alive()
    assert win.load_calls == 0


def test_watchdog_retries_until_loaded():
    from desktop.window import _start_load_retry_watchdog

    loaded = threading.Event()
    win = _FakeWindow()
    orig = win.load_url

    def _load(url):
        orig(url)
        if win.load_calls >= 2:  # second retry "succeeds"
            loaded.set()

    win.load_url = _load
    t = _start_load_retry_watchdog(
        win, "http://x/", loaded,
        grace_sec=0.05, retry_interval_sec=0.05, max_retries=5,
    )
    t.join(timeout=5)
    assert not t.is_alive()
    assert win.load_calls == 2


def test_watchdog_gives_up_after_max_retries():
    from desktop.window import _start_load_retry_watchdog

    loaded = threading.Event()  # never set
    win = _FakeWindow()
    t = _start_load_retry_watchdog(
        win, "http://x/", loaded,
        grace_sec=0.02, retry_interval_sec=0.02, max_retries=3,
    )
    t.join(timeout=5)
    assert not t.is_alive()
    assert win.load_calls == 3


def test_watchdog_survives_load_url_errors():
    """load_url before webview.start() can raise — must keep retrying."""
    from desktop.window import _start_load_retry_watchdog

    loaded = threading.Event()
    win = _FakeWindow(fail_first_n=99)
    t = _start_load_retry_watchdog(
        win, "http://x/", loaded,
        grace_sec=0.02, retry_interval_sec=0.02, max_retries=2,
    )
    t.join(timeout=5)
    assert not t.is_alive()
    assert win.load_calls == 2  # errors swallowed, attempts continued


# ---------------------------------------------------------- hardened gate

class _Resp:
    def __init__(self, status_code: int):
        self.status_code = status_code


def test_wait_http_consecutive_resets_streak(monkeypatch):
    """ok, error, ok, ok, ok — with consecutive=3 the gate must not pass
    until the THREE uninterrupted successes at the end."""
    from desktop import launcher

    seq = [_Resp(200), ConnectionError("blip"), _Resp(200), _Resp(200), _Resp(200)]
    calls = {"n": 0}

    def _fake_get(url, timeout=None, follow_redirects=False):
        i = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        item = seq[i]
        if isinstance(item, Exception):
            raise launcher.httpx.RequestError("blip")
        return item

    monkeypatch.setattr(launcher.httpx, "get", _fake_get)
    monkeypatch.setattr(launcher.time, "sleep", lambda s: None)
    launcher._wait_http("http://x/", timeout=5.0, consecutive=3)
    assert calls["n"] == 5  # streak reset by the failure, rebuilt after


def test_wait_http_passes_follow_redirects(monkeypatch):
    from desktop import launcher

    seen = {}

    def _fake_get(url, timeout=None, follow_redirects=False):
        seen["follow"] = follow_redirects
        return _Resp(200)

    monkeypatch.setattr(launcher.httpx, "get", _fake_get)
    launcher._wait_http("http://x/", timeout=2.0, follow_redirects=True)
    assert seen["follow"] is True


def test_wait_http_default_single_probe_unchanged(monkeypatch):
    """/readyz callers keep the original one-success semantics."""
    from desktop import launcher

    calls = {"n": 0}

    def _fake_get(url, timeout=None, follow_redirects=False):
        calls["n"] += 1
        return _Resp(200)

    monkeypatch.setattr(launcher.httpx, "get", _fake_get)
    launcher._wait_http("http://x/", timeout=2.0)
    assert calls["n"] == 1
