"""ONP v0.6.26 — Regression test for desktop.app.run() orphan-cleanup.

Before this fix, an exception in any phase between _phase_start_supervisor
and _phase_open_window left the Supervisor's children running after the
launcher died. The user would then hit "port already in use" the next time
they relaunched and have to `kill -9` the orphaned uvicorn / surreal /
next-server / llamacpp / piper / whisper processes by hand.

This test patches the phases to:
  1. Run a fake supervisor that records stop_all() calls
  2. Inject a failure in a post-supervisor phase
  3. Assert stop_all() WAS called before run() re-raises
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _attach_fake_sv(ctx) -> MagicMock:
    """Helper: install a MagicMock supervisor on ctx — simulates the result
    of a successful _phase_start_supervisor."""
    fake_sv = MagicMock()
    fake_sv.stop_all = MagicMock()
    ctx.sv = fake_sv
    return fake_sv


def _patch_pre_phases(mp):
    """Stub out all pre-supervisor phases — they require real config/disk/etc."""
    for name in [
        "_phase_detect_data_root_recovery",
        "_phase_load_config",
        "_phase_wizard_if_first_run",
        "_phase_bootstrap_runtime",
        "_phase_download_models",
        "_phase_select_provider",
        "_phase_detect_openchronicle",
        "_phase_register_memory_commands",
    ]:
        mp.setattr(f"desktop.app.{name}", lambda _ctx: None)


def _patch_post_phases(mp, **overrides):
    """Stub each post-supervisor phase to a no-op by default; overrides[name] replaces it."""
    for name in [
        "_phase_auto_register",
        "_phase_start_model_manager",
        "_phase_start_memory_dashboard",
        "_phase_install_tray",
        "_phase_open_window",
    ]:
        impl = overrides.get(name, lambda _ctx: None)
        mp.setattr(f"desktop.app.{name}", impl)


@pytest.mark.parametrize(
    "failing_phase",
    [
        "_phase_auto_register",
        "_phase_start_model_manager",
        "_phase_start_memory_dashboard",
        "_phase_install_tray",
        "_phase_open_window",
    ],
)
def test_run_calls_stop_all_when_post_supervisor_phase_raises(
    monkeypatch, failing_phase
):
    """Each post-supervisor phase, if it raises, must trigger sv.stop_all()
    so SurrealDB / FastAPI / Next.js children aren't orphaned on the user's
    machine."""
    from desktop import app as app_mod

    # The supervisor starts successfully and attaches to ctx
    sv_holder = {}

    def _fake_start_supervisor(ctx):
        sv_holder["sv"] = _attach_fake_sv(ctx)

    monkeypatch.setattr(app_mod, "_phase_start_supervisor", _fake_start_supervisor)

    _patch_pre_phases(monkeypatch)

    # One phase raises; the rest are no-ops
    def _boom(_ctx):
        raise RuntimeError("simulated phase failure")

    _patch_post_phases(monkeypatch, **{failing_phase: _boom})

    with pytest.raises(RuntimeError, match=r"simulated phase failure"):
        app_mod.run()

    # The crucial assertion: stop_all WAS called before re-raise
    assert sv_holder["sv"].stop_all.called, (
        f"stop_all() was NOT called after {failing_phase} raised — "
        "supervisor children would be orphaned"
    )


def test_run_does_not_call_stop_all_on_success(monkeypatch):
    """Sanity check: on the happy path, run() returns 0 without invoking
    the cleanup branch. (open_window's own finally handles the normal
    teardown — we don't want to double-call it.)"""
    from desktop import app as app_mod

    sv_holder = {}

    def _fake_start_supervisor(ctx):
        sv_holder["sv"] = _attach_fake_sv(ctx)

    monkeypatch.setattr(app_mod, "_phase_start_supervisor", _fake_start_supervisor)

    _patch_pre_phases(monkeypatch)
    _patch_post_phases(monkeypatch)  # all no-ops

    assert app_mod.run() == 0
    assert not sv_holder["sv"].stop_all.called, (
        "happy path should leave stop_all to _phase_open_window's own finally"
    )


def test_run_swallows_stop_all_error_but_reraises_original(monkeypatch):
    """If stop_all itself raises during cleanup, we still propagate the
    ORIGINAL exception (not the stop_all error). Critical for debugability —
    a flaky teardown shouldn't mask the real failure."""
    from desktop import app as app_mod

    def _fake_start_supervisor(ctx):
        sv = _attach_fake_sv(ctx)
        sv.stop_all.side_effect = OSError("teardown also broken")

    monkeypatch.setattr(app_mod, "_phase_start_supervisor", _fake_start_supervisor)
    _patch_pre_phases(monkeypatch)

    def _boom(_ctx):
        raise ValueError("the real reason")

    _patch_post_phases(monkeypatch, _phase_install_tray=_boom)

    with pytest.raises(ValueError, match=r"the real reason"):
        app_mod.run()


def test_run_window_startup_exception_tears_down_each_runtime_exactly_once(
    monkeypatch, tmp_path
):
    """The window phase and run() exception guard share one teardown owner."""
    from desktop import app as app_mod
    from desktop import window as desktop_window

    ctx = app_mod._new_context()
    supervisor_stops: list[bool] = []
    runtime_stops: list[bool] = []
    ctx.cfg = SimpleNamespace(theme="light-blue", openchronicle_choice="skip")
    ctx.progress_bus = SimpleNamespace(publish=lambda *_args, **_kwargs: None)
    ctx.log_dir = tmp_path / "logs"
    ctx.log_dir.mkdir()
    ctx.sv = SimpleNamespace(
        frontend_url="http://127.0.0.1:62001/",
        session_env={"INTERNAL_API_URL": "http://127.0.0.1:62000"},
        whisper_port=0,
        piper_port=0,
        stop_all=lambda: supervisor_stops.append(True),
    )

    monkeypatch.setattr(app_mod, "_new_context", lambda: ctx)
    monkeypatch.setattr(app_mod, "_phase_detect_app_recovery", lambda _ctx: None)
    _patch_pre_phases(monkeypatch)
    monkeypatch.setattr(app_mod, "_phase_start_supervisor", lambda _ctx: None)
    for name in [
        "_phase_auto_register",
        "_phase_start_model_manager",
        "_phase_start_memory_dashboard",
        "_phase_install_tray",
    ]:
        monkeypatch.setattr(app_mod, name, lambda _ctx: None)

    def fail_window_startup(*_args, **_kwargs):
        raise RuntimeError("window startup failed")

    monkeypatch.setattr(desktop_window, "open_window", fail_window_startup)
    monkeypatch.setattr(
        app_mod, "_stop_runtime", lambda _ctx: runtime_stops.append(True)
    )

    with pytest.raises(RuntimeError, match="window startup failed"):
        app_mod.run()

    assert supervisor_stops == [True]
    assert runtime_stops == [True]
