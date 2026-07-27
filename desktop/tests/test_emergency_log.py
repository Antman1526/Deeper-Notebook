"""ONP v0.6.33 — Regression tests for the early-init emergency-log path.

Before this fix, an exception thrown by _new_context() or
_phase_load_config() (e.g. a bug in those phases, missing $HOME on a
weirdly-configured machine, a permission denied on the logs dir) produced
a frozen-launcher crash with NOTHING for the user to see:
  - No terminal (PyWebView .app double-clicked from Finder)
  - No launcher.log (FileHandler not attached yet — that happens IN
    _phase_load_config)
  - Just a dock-bouncing icon that quit immediately

The emergency-log path in __main__.py writes to a fixed path that doesn't
depend on any of the modules that might have failed.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_emergency_log_writes_to_launcher_log(tmp_path, monkeypatch):
    """Plant a fake HOME; verify _emergency_log writes the exception to
    ~/.deeper-notebook/logs/launcher.log."""
    monkeypatch.setenv("HOME", str(tmp_path))
    from desktop.__main__ import _emergency_log

    try:
        raise RuntimeError("simulated early-init failure")
    except RuntimeError as exc:
        _emergency_log(exc)

    log_path = tmp_path / ".deeper-notebook" / "logs" / "launcher.log"
    assert log_path.exists()
    text = log_path.read_text()
    assert "EARLY-INIT FAILURE" in text
    assert "simulated early-init failure" in text
    assert "RuntimeError" in text


def test_emergency_log_appends_to_existing_file(tmp_path, monkeypatch):
    """Multiple early-init failures should accumulate in launcher.log,
    not overwrite each other."""
    monkeypatch.setenv("HOME", str(tmp_path))
    from desktop.__main__ import _emergency_log

    log_path = tmp_path / ".deeper-notebook" / "logs" / "launcher.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("PREVIOUS-LOG-CONTENT\n")

    try:
        raise ValueError("second failure")
    except ValueError as exc:
        _emergency_log(exc)

    text = log_path.read_text()
    assert "PREVIOUS-LOG-CONTENT" in text  # prior content preserved
    assert "second failure" in text       # new failure appended


def test_emergency_log_swallows_its_own_failure(monkeypatch, capsys):
    """If even the emergency-log write fails (e.g. log dir unwritable),
    we must NOT raise — we'd lose the original exception's exit code."""
    # Point HOME at a path that can't be a parent directory
    monkeypatch.setenv("HOME", "/dev/null")
    from desktop.__main__ import _emergency_log

    # Should not raise even though /dev/null/.deeper-notebook fails to mkdir
    try:
        raise RuntimeError("the real error")
    except RuntimeError as exc:
        _emergency_log(exc)  # no exception


def test_emergency_log_creates_logs_dir_if_missing(tmp_path, monkeypatch):
    """Fresh install: the logs dir doesn't exist yet. _emergency_log must
    create it before writing."""
    monkeypatch.setenv("HOME", str(tmp_path))
    from desktop.__main__ import _emergency_log

    log_dir = tmp_path / ".deeper-notebook" / "logs"
    assert not log_dir.exists()  # fresh

    try:
        raise OSError("disk full")
    except OSError as exc:
        _emergency_log(exc)

    assert log_dir.exists()
    assert (log_dir / "launcher.log").exists()
