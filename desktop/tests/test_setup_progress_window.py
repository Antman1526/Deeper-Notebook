"""v0.8.130 — first-launch setup shows its progress.

The wizard window closed the instant settings were saved, and the launcher's
startup phases only ran afterwards, so the wizard's "Setting up" screen was never
seen and the user had no window for the minutes first-launch setup takes (seen in
a packaged run on 2026-10-05). The launcher now keeps the wizard's server running
and opens the setting-up screen in a small helper process until the main window
is ready. Startup itself stays on the launcher's main thread, where its signal
handlers and native dialogs must run.
"""

import json
import os
import subprocess
import sys
import threading
import time
import types
import urllib.request
from pathlib import Path

import pytest

from desktop import setup_progress_window as helper
from desktop.progress import ProgressBus

STATIC = Path(__file__).resolve().parents[1] / "first_run" / "static"


# ---- the helper process -----------------------------------------------------


def test_packaged_app_relaunches_its_own_binary(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Apps/Deeper Notebook")
    assert helper.command_for(port=4321, parent_pid=77) == [
        "/Apps/Deeper Notebook", helper.FLAG, "4321", "77",
    ]


def test_source_checkout_runs_the_module(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    command = helper.command_for(port=4321, parent_pid=77)
    assert command[:3] == [sys.executable, "-m", "desktop"]
    assert command[3:] == [helper.FLAG, "4321", "77"]


def test_a_helper_that_cannot_start_never_stops_the_launch(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise OSError("no such file")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    assert helper.spawn(port=4321) is None


def test_close_stops_the_helper_and_is_safe_to_repeat():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    helper.close(process)
    assert process.poll() is not None
    helper.close(process)
    helper.close(None)


def test_the_helper_knows_when_its_launcher_is_gone():
    assert helper.parent_alive(os.getpid()) is True
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    assert helper.parent_alive(finished.pid) is False


def test_arguments_are_parsed_and_anything_else_is_not_ours():
    assert helper.parse_args([helper.FLAG, "4321", "77"]) == (4321, 77, None)
    assert helper.parse_args([helper.FLAG, "4321", "77", "tokyo-night"]) == (4321, 77, "tokyo-night")
    # A theme id is letters, digits and hyphens; anything else is dropped, not passed into a URL.
    assert helper.parse_args([helper.FLAG, "4321", "77", "x&screen=welcome"]) == (4321, 77, None)
    assert helper.parse_args([]) is None
    assert helper.parse_args(["-psn_0_12345"]) is None
    assert helper.parse_args([helper.FLAG, "not-a-port", "77"]) is None


def test_the_helper_window_shows_the_setting_up_screen(monkeypatch):
    opened = {}
    fake = types.SimpleNamespace(
        create_window=lambda title, url, **kw: opened.update(title=title, url=url, **kw) or object(),
        start=lambda *a, **k: opened.update(started=True),
    )
    monkeypatch.setitem(sys.modules, "webview", fake)
    assert helper.main([helper.FLAG, "4321", str(os.getpid())]) == 0
    assert opened["url"] == "http://127.0.0.1:4321/?screen=setting-up"
    assert opened["started"] is True


def test_the_helper_window_wears_the_theme_just_chosen(monkeypatch):
    opened = {}
    fake = types.SimpleNamespace(
        create_window=lambda title, url, **kw: opened.update(url=url) or object(),
        start=lambda *a, **k: None,
    )
    monkeypatch.setitem(sys.modules, "webview", fake)
    helper.main([helper.FLAG, "4321", str(os.getpid()), "tokyo-night"])
    assert opened["url"] == "http://127.0.0.1:4321/?screen=setting-up&theme=tokyo-night"
    assert helper.command_for(port=1, parent_pid=2, theme="nord")[-1] == "nord"
    wizard = (STATIC / "wizard.js").read_text(encoding="utf-8")
    assert "get('theme')" in wizard


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


def _titled_window(page_title):
    window = types.SimpleNamespace(
        events=types.SimpleNamespace(loaded=_Event()),
        evaluate_js=lambda script: page_title if script == "document.title" else None,
        titles=[],
        destroy=lambda: None,
    )
    window.set_title = window.titles.append
    return window


def test_window_titles_follow_the_translated_page_title():
    window = _titled_window("Deeper Notebook — Einrichtung")
    helper.follow_page_title(window)
    for handler in window.events.loaded.handlers:
        handler()
    assert window.titles == ["Deeper Notebook — Einrichtung"]

    # A page that gives no title, or a web view that cannot say, changes nothing.
    silent = _titled_window("")
    helper.follow_page_title(silent)
    for handler in silent.events.loaded.handlers:
        handler()
    assert silent.titles == []
    helper.follow_page_title(object())  # no events at all: must not raise


def test_the_progress_window_adds_no_second_dock_icon(monkeypatch):
    """The app already has a Dock icon; the helper is a window of it, not a second app."""
    policies, scheduled = [], []
    application = types.SimpleNamespace(
        setActivationPolicy_=policies.append,
        activateIgnoringOtherApps_=lambda flag: policies.append(("front", flag)),
    )
    appkit = types.SimpleNamespace(
        NSApplication=types.SimpleNamespace(sharedApplication=lambda: application),
        NSApplicationActivationPolicyAccessory=1,
    )
    tools = types.SimpleNamespace(AppHelper=types.SimpleNamespace(callAfter=scheduled.append))
    monkeypatch.setitem(sys.modules, "AppKit", appkit)
    monkeypatch.setitem(sys.modules, "PyObjCTools", tools)
    monkeypatch.setattr(helper.sys, "platform", "darwin")

    window = types.SimpleNamespace(events=types.SimpleNamespace(shown=_Event()))
    helper.stay_out_of_the_dock(window)
    for handler in window.events.shown.handlers:
        handler()
    assert policies == [], "AppKit is only touched on the main thread"
    for job in scheduled:
        job()
    assert policies == [1, ("front", True)]

    # Elsewhere, or with no window events, it does nothing and does not raise.
    monkeypatch.setattr(helper.sys, "platform", "linux")
    other = types.SimpleNamespace(events=types.SimpleNamespace(shown=_Event()))
    helper.stay_out_of_the_dock(other)
    assert other.events.shown.handlers == []
    helper.stay_out_of_the_dock(object())


def test_the_wizard_window_title_is_translated_too():
    source = (Path(helper.__file__).parent / "first_run" / "server.py").read_text(encoding="utf-8")
    assert "follow_page_title(window)" in source


def test_the_entry_point_hands_over_before_the_launcher_starts():
    source = (Path(helper.__file__).parent / "__main__.py").read_text(encoding="utf-8")
    dispatch = source.index("setup_progress_window")
    launcher = source.index("from desktop.app import run")
    assert dispatch < launcher, "the helper must not start a second launcher"


# ---- the wizard's server outlives the wizard window ---------------------------


@pytest.fixture
def fake_webview(monkeypatch):
    window = types.SimpleNamespace(destroy=lambda: None)
    fake = types.SimpleNamespace(
        create_window=lambda *a, **k: window,
        start=lambda *a, **k: None,  # the user closes the wizard at once
    )
    monkeypatch.setitem(sys.modules, "webview", fake)
    return fake


def test_progress_is_still_served_after_the_wizard_window_closes(tmp_path, fake_webview):
    from desktop.first_run.server import run_wizard_blocking

    bus = ProgressBus(log_path=tmp_path / "progress.jsonl")
    bus.publish("startup", "running", "Launcher starting…")
    server = run_wizard_blocking(tmp_path / "config.toml", progress_bus=bus)
    try:
        assert server is not None and server.port > 0

        def finish():
            time.sleep(0.3)
            bus.publish("supervisor.surreal", "running")
            bus.publish("ready", "done", "Main window opening…")

        threading.Thread(target=finish, daemon=True).start()
        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/api/progress", timeout=20) as stream:
            events = [json.loads(line[6:]) for line in stream.read().decode().splitlines() if line.startswith("data: ")]
        assert [event["step"] for event in events] == ["startup", "supervisor.surreal", "ready"]
        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/?screen=setting-up", timeout=20) as page:
            assert page.status == 200
    finally:
        server.stop()
    server.stop()  # safe to repeat
    with pytest.raises(OSError):
        urllib.request.urlopen(f"http://127.0.0.1:{server.port}/", timeout=3)


def test_the_page_opens_on_the_setting_up_screen_when_asked():
    wizard = (STATIC / "wizard.js").read_text(encoding="utf-8")
    assert "get('screen') === 'setting-up'" in wizard
    # One subscription routine, used after saving and by the helper window.
    assert wizard.count("new EventSource('/api/progress')") == 1


# ---- the launcher opens and closes the helper ---------------------------------


def _context(tmp_path):
    from desktop import app

    ctx = app._new_context()
    ctx._first_run = True
    ctx._cfg_path = tmp_path / "config.toml"
    ctx._load_or_create = lambda path: object()
    ctx.progress_bus = ProgressBus(log_path=tmp_path / "progress.jsonl")
    return app, ctx


def test_first_run_opens_the_progress_window_and_closes_it_exactly_once(tmp_path, monkeypatch):
    app, ctx = _context(tmp_path)
    calls = []
    server = types.SimpleNamespace(port=4321, stop=lambda: calls.append("server stopped"))
    process = object()
    monkeypatch.setattr("desktop.first_run.server.run_wizard_blocking", lambda *a, **k: server)
    monkeypatch.setattr(helper, "spawn", lambda port, theme=None: calls.append(f"spawn {port}") or process)
    monkeypatch.setattr(helper, "close", lambda proc: calls.append("closed" if proc is process else "closed other"))

    app._phase_wizard_if_first_run(ctx)
    assert calls == ["spawn 4321"]

    app._close_setup_progress(ctx)
    app._close_setup_progress(ctx)
    assert calls == ["spawn 4321", "closed", "server stopped"]


def test_later_launches_open_no_progress_window(tmp_path, monkeypatch):
    app, ctx = _context(tmp_path)
    ctx._first_run = False
    monkeypatch.setattr(helper, "spawn", lambda port, theme=None: pytest.fail("no wizard, no helper"))
    app._phase_wizard_if_first_run(ctx)
    app._close_setup_progress(ctx)  # nothing to close


def test_the_progress_window_closes_when_the_main_window_opens_and_when_startup_fails():
    source = (Path(helper.__file__).parent / "app.py").read_text(encoding="utf-8")
    opening = source[source.index("def _phase_open_window") :]
    # Before the call that opens the main window (and blocks until it closes).
    assert "_close_setup_progress(ctx)" in opening[: opening.index("        open_window(\n")]
    running = source[source.index("def run() -> int:") :]
    assert "finally:" in running and "_close_setup_progress(ctx)" in running
