"""v0.8.68 — launch-race fixes for "This page couldn't load" at startup.

Final architecture (two earlier cuts failed live): the window opens on an
inline splash, and a PYTHON handoff controller decides when to navigate —
it can see real HTTP status/bodies (an in-page no-cors probe cannot, so
Next's warm-up 404, served with status 200, read as "ready"), and a failed
handoff puts the splash back and retries, so the error page is never the
resting state. The loaded handler confirms a genuine app page via an
in-page sentinel because get_current_url() is None for html= pages and
reports the target URL even for failed loads.
"""

from __future__ import annotations

import threading

import pytest


class _FakeWindow:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.fail_load_url_times = 0

    def load_url(self, url: str) -> None:
        if self.fail_load_url_times > 0:
            self.fail_load_url_times -= 1
            self.calls.append(("load_url_raised", url))
            raise RuntimeError("window not ready")
        self.calls.append(("load_url", url))

    def load_html(self, html: str) -> None:
        self.calls.append(("load_html", html[:20]))


def _run_controller(win, loaded, **kw):
    from desktop.window import _start_handoff_controller

    defaults = dict(
        min_splash_sec=0.0,
        poll_sec=0.0,
        attempt_timeout_sec=0.2,
        max_attempts=3,
        sleep=lambda s: None,
    )
    defaults.update(kw)
    t = _start_handoff_controller(win, "http://x/", loaded, "<SPLASH/>", **defaults)
    t.join(timeout=10)
    assert not t.is_alive()
    return win.calls


# ------------------------------------------------------- handoff controller


def test_happy_path_waits_for_consecutive_ready_then_navigates():
    seq = iter([False, True, True])
    loaded = threading.Event()
    win = _FakeWindow()
    orig = win.load_url

    def _load(url):
        orig(url)
        loaded.set()  # navigation succeeds

    win.load_url = _load
    calls = _run_controller(win, loaded, server_ready=lambda: next(seq, True))
    assert calls == [("load_url", "http://x/")]


def test_failed_handoff_restores_splash_and_retries():
    loaded = threading.Event()
    win = _FakeWindow()
    attempts = {"n": 0}
    orig = win.load_url

    def _load(url):
        orig(url)
        attempts["n"] += 1
        if attempts["n"] >= 2:  # second navigation succeeds
            loaded.set()

    win.load_url = _load
    calls = _run_controller(win, loaded, server_ready=lambda: True)
    # nav fail → splash back → nav success
    assert calls == [
        ("load_url", "http://x/"),
        ("load_html", "<SPLASH/>"),
        ("load_url", "http://x/"),
    ]


def test_min_splash_time_is_respected():
    """The user asked to actually SEE the welcome screen — the controller
    sleeps out the remainder of min_splash_sec before the first handoff."""
    slept: list[float] = []
    clock = {"t": 0.0}

    def _sleep(s):
        slept.append(s)
        clock["t"] += s

    loaded = threading.Event()
    win = _FakeWindow()
    orig = win.load_url

    def _load(url):
        orig(url)
        loaded.set()

    win.load_url = _load
    _run_controller(
        win,
        loaded,
        server_ready=lambda: True,
        min_splash_sec=3.0,
        sleep=_sleep,
        clock=lambda: clock["t"],
    )
    assert sum(slept) >= 3.0


def test_gives_up_to_frontend_url_after_max_attempts():
    """Exhausted retries leave the frontend URL up (manual Reload works)."""
    loaded = threading.Event()  # never set
    win = _FakeWindow()
    calls = _run_controller(win, loaded, server_ready=lambda: True, max_attempts=2)
    assert calls == [
        ("load_url", "http://x/"),
        ("load_html", "<SPLASH/>"),
        ("load_url", "http://x/"),
        ("load_html", "<SPLASH/>"),
        ("load_url", "http://x/"),  # final resting navigation
    ]


def test_recovers_after_many_failed_navigations_before_giving_up():
    """v0.8.72 regression — the live bug: on a slow ad-hoc cold boot WKWebView
    refuses to load for minutes (probe + manual Reload both succeed, but the
    controller's load_url keeps failing), so the OLD 10-attempt budget gave up
    and rested on the error page. The widened budget must keep retrying past 10
    and succeed once the navigation finally takes — without ever resting on the
    error page. Here the 15th navigation is the first to 'load'."""
    loaded = threading.Event()
    win = _FakeWindow()
    attempts = {"n": 0}
    orig = win.load_url

    def _load(url):
        orig(url)
        attempts["n"] += 1
        if attempts["n"] >= 15:  # WKWebView finally willing on the 15th try
            loaded.set()

    win.load_url = _load
    # Production default is 40; 15 > the old give-up bound of 10.
    calls = _run_controller(win, loaded, server_ready=lambda: True, max_attempts=40)
    # It navigated successfully and STOPPED (didn't burn all 40 or rest on error).
    assert loaded.is_set()
    assert attempts["n"] == 15
    assert calls[-1] == ("load_url", "http://x/")  # ended on a successful nav
    assert calls.count(("load_url", "http://x/")) == 15


def test_production_retry_budget_outlasts_a_slow_cold_boot():
    """Lock in the widened defaults so a future tweak can't silently shrink the
    budget back below a realistic slow-boot window (~minutes)."""
    import inspect

    from desktop.window import _start_handoff_controller

    sig = inspect.signature(_start_handoff_controller)
    max_attempts = sig.parameters["max_attempts"].default
    attempt_timeout = sig.parameters["attempt_timeout_sec"].default
    # ≥ ~3 min of total retry headroom before giving up to the manual-Reload page.
    assert max_attempts * attempt_timeout >= 180


def test_load_url_exception_is_retried():
    loaded = threading.Event()
    win = _FakeWindow()
    win.fail_load_url_times = 1
    orig = win.load_url

    def _load(url):
        orig(url)
        loaded.set()

    # patch AFTER fail counter so first call raises through orig
    inner = win.load_url

    calls = _run_controller(win, loaded, server_ready=lambda: True)
    assert ("load_url_raised", "http://x/") in calls
    assert calls[-1] == ("load_url", "http://x/")


# ------------------------------------------------------- server readiness


class _Resp:
    def __init__(self, status_code: int, content: bytes = b"<html>ok</html>"):
        self.status_code = status_code
        self.content = content


def test_server_ready_rejects_next_warmup_404(monkeypatch):
    """Next 16 standalone briefly serves its not-found page (HTTP 200!) for
    valid routes while route manifests lazy-load — seen live. Status alone
    cannot catch it; the <title> ("404: …") must. The real warm-up page DOES
    carry the Next runtime (__next_f) — the title is the discriminator."""
    import desktop.window as w

    class _Httpx:
        @staticmethod
        def get(url, timeout=None, follow_redirects=False):
            return _Resp(
                200,
                b"<html><head><title>404: This page could not be found.</title>"
                b"</head><body><script>self.__next_f=[]</script>"
                b'<h1 class="next-error-h1">404</h1></body></html>',
            )

    monkeypatch.setitem(__import__("sys").modules, "httpx", _Httpx)
    assert w._frontend_server_ready("http://x/") is False


def test_server_ready_accepts_real_page(monkeypatch):
    import desktop.window as w

    class _Httpx:
        @staticmethod
        def get(url, timeout=None, follow_redirects=False):
            assert follow_redirects is True  # must probe the FINAL page
            return _Resp(
                200,
                b"<html><head><title>Open notebook+</title></head>"
                b"<body><script>self.__next_f=[]</script>app</body></html>",
            )

    monkeypatch.setitem(__import__("sys").modules, "httpx", _Httpx)
    assert w._frontend_server_ready("http://x/") is True


def test_server_ready_accepts_page_with_embedded_next_error_styles(monkeypatch):
    """v0.8.70 regression — Next 16 streams the global notFound boundary
    (including its `.next-error-h1` style block) into EVERY page's RSC payload.
    The old `b"next-error-h1" not in content` check therefore returned False
    for real pages too, so `_frontend_server_ready` never passed and the
    splash→app handoff hung forever. A real app page (title != 404, Next
    runtime present) must read READY even though it contains `next-error-h1`."""
    import desktop.window as w

    class _Httpx:
        @staticmethod
        def get(url, timeout=None, follow_redirects=False):
            return _Resp(
                200,
                b"<html><head><title>Open notebook+</title></head><body>"
                b"<style>.next-error-h1{border-right:1px solid}</style>"
                b"<script>self.__next_f=[]</script></body></html>",
            )

    monkeypatch.setitem(__import__("sys").modules, "httpx", _Httpx)
    assert w._frontend_server_ready("http://x/") is True


def test_server_ready_rejects_connection_error(monkeypatch):
    import desktop.window as w

    class _Httpx:
        @staticmethod
        def get(url, timeout=None, follow_redirects=False):
            raise ConnectionError("refused")

    monkeypatch.setitem(__import__("sys").modules, "httpx", _Httpx)
    assert w._frontend_server_ready("http://x/") is False


# ------------------------------------------------------- loaded sentinel


def test_frontend_sentinel_js_shape():
    """The sentinel must check the Next runtime AND exclude Next's 404
    title — URL-based checks were proven unable to distinguish the error
    page (reports target URL) and the splash (reports None)."""
    from desktop.window import _FRONTEND_SENTINEL_JS

    assert "__next_f" in _FRONTEND_SENTINEL_JS
    assert "404" in _FRONTEND_SENTINEL_JS
