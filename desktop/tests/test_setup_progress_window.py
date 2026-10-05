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
    assert helper.parse_args([helper.FLAG, "4321", "77"]) == (4321, 77)
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
    monkeypatch.setattr(helper, "spawn", lambda port: calls.append(f"spawn {port}") or process)
    monkeypatch.setattr(helper, "close", lambda proc: calls.append("closed" if proc is process else "closed other"))

    app._phase_wizard_if_first_run(ctx)
    assert calls == ["spawn 4321"]

    app._close_setup_progress(ctx)
    app._close_setup_progress(ctx)
    assert calls == ["spawn 4321", "closed", "server stopped"]


def test_later_launches_open_no_progress_window(tmp_path, monkeypatch):
    app, ctx = _context(tmp_path)
    ctx._first_run = False
    monkeypatch.setattr(helper, "spawn", lambda port: pytest.fail("no wizard, no helper"))
    app._phase_wizard_if_first_run(ctx)
    app._close_setup_progress(ctx)  # nothing to close


def test_the_progress_window_closes_when_the_main_window_opens_and_when_startup_fails():
    source = (Path(helper.__file__).parent / "app.py").read_text(encoding="utf-8")
    opening = source[source.index("def _phase_open_window") :]
    # Before the call that opens the main window (and blocks until it closes).
    assert "_close_setup_progress(ctx)" in opening[: opening.index("        open_window(\n")]
    running = source[source.index("def run() -> int:") :]
    assert "finally:" in running and "_close_setup_progress(ctx)" in running
