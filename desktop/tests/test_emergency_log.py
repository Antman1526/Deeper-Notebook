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
from contextlib import contextmanager
from pathlib import Path

import pytest


def test_emergency_log_writes_to_launcher_log(tmp_path, monkeypatch):
    """Plant a fake HOME; verify _emergency_log writes the exception to
    the non-conflicting recovery log."""
    monkeypatch.setenv("HOME", str(tmp_path))
    from desktop.__main__ import _emergency_log

    try:
        raise RuntimeError("simulated early-init failure")
    except RuntimeError as exc:
        _emergency_log(exc)

    log_path = tmp_path / ".deeper-notebook-recovery" / "logs" / "launcher.log"
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
    from desktop.data_root import open_recovery_log_directory

    log_path = tmp_path / ".deeper-notebook-recovery" / "logs" / "launcher.log"
    with open_recovery_log_directory(home=tmp_path):
        pass
    log_path.write_text("PREVIOUS-LOG-CONTENT\n")

    try:
        raise ValueError("second failure")
    except ValueError as exc:
        _emergency_log(exc)

    text = log_path.read_text()
    assert "PREVIOUS-LOG-CONTENT" in text  # prior content preserved
    assert "second failure" in text  # new failure appended


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

    log_dir = tmp_path / ".deeper-notebook-recovery" / "logs"
    assert not log_dir.exists()  # fresh

    try:
        raise OSError("disk full")
    except OSError as exc:
        _emergency_log(exc)

    assert log_dir.exists()
    assert (log_dir / "launcher.log").exists()


def test_emergency_log_does_not_reenter_failed_data_root_resolution(
    tmp_path, monkeypatch
):
    from desktop import __main__ as entrypoint

    def blocked_root():
        raise AssertionError("emergency logging reentered the failed resolver")

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr("desktop.data_root.active_data_root", blocked_root)

    original = RuntimeError("simulated early failure")
    entrypoint._emergency_log(original)

    log_path = tmp_path / ".deeper-notebook-recovery" / "logs" / "launcher.log"
    assert "simulated early failure" in log_path.read_text(encoding="utf-8")
    assert not (tmp_path / ".deeper-notebook").exists()
    assert not (tmp_path / ".open-notebook-plus").exists()


def test_emergency_log_refuses_symlinked_recovery_directory(
    tmp_path, monkeypatch, capsys
):
    from desktop import __main__ as entrypoint

    canonical = tmp_path / ".deeper-notebook"
    canonical.mkdir()
    (tmp_path / ".deeper-notebook-recovery").symlink_to(
        canonical,
        target_is_directory=True,
    )
    monkeypatch.setenv("HOME", str(tmp_path))

    entrypoint._emergency_log(RuntimeError("do not follow recovery link"))

    assert not (canonical / "logs" / "launcher.log").exists()
    assert "Launcher early-init failure" in capsys.readouterr().err


def test_emergency_log_dirfd_cannot_be_redirected_after_open(
    tmp_path, monkeypatch, capsys
):
    from desktop import __main__ as entrypoint
    from desktop import data_root

    canonical = tmp_path / ".deeper-notebook"
    canonical.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    real_open = data_root.open_recovery_log_directory
    held = tmp_path / ".logs-held"

    @contextmanager
    def swapped_log_directory():
        with real_open() as directory:
            directory.path.rename(held)
            directory.path.symlink_to(canonical, target_is_directory=True)
            yield directory

    monkeypatch.setattr(
        entrypoint,
        "open_recovery_log_directory",
        swapped_log_directory,
    )
    entrypoint._emergency_log(RuntimeError("descriptor-bound"))

    assert not (canonical / "launcher.log").exists()
    assert "descriptor-bound" in (held / "launcher.log").read_text(encoding="utf-8")
    assert "Launcher early-init failure" in capsys.readouterr().err


def test_recovery_log_adopts_and_appends_to_existing_owned_file(tmp_path):
    from desktop.data_root import (
        append_recovery_log,
        open_recovery_log_directory,
    )

    log_path = tmp_path / ".deeper-notebook-recovery" / "logs" / "launcher.log"
    with open_recovery_log_directory(home=tmp_path):
        pass
    log_path.write_bytes(b"existing-log\n")

    with open_recovery_log_directory(home=tmp_path) as directory:
        append_recovery_log(directory, "launcher.log", b"new-entry\n")

    assert log_path.read_bytes() == b"existing-log\nnew-entry\n"
