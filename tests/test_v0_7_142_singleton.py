"""v0.7.142 — singleton + orphan-reaper unit tests.

The user's incident that prompted this code:
  - Double-clicked `Open Notebook Plus.app` ~5 times during debugging
  - Each click started a fresh launcher with new dynamic ports
  - Closing a Chromium window left the launcher running
  - Ended up with 4 zombie Next.js + 3 zombie workers from May 11
  - "Unable to Connect to API Server" screen pointed at a dead API

These tests pin the singleton's promised behaviors so future edits
to desktop/singleton.py can't silently regress.

All tests use real OS calls (os.kill, file I/O) — no mocking of the
PID-liveness check, because the whole point of this module is that
the OS check works. Hermetic via pytest's `tmp_path` fixture.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------- #
# _is_pid_alive — the foundation everything else relies on
# ---------------------------------------------------------------------- #


class TestIsPidAlive:
    def test_current_process_is_alive(self):
        from desktop.singleton import _is_pid_alive
        assert _is_pid_alive(os.getpid()) is True

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows has no POSIX init PID")
    def test_init_process_is_alive(self):
        """PID 1 is always alive on POSIX systems."""
        from desktop.singleton import _is_pid_alive
        assert _is_pid_alive(1) is True

    def test_negative_pid_is_dead(self):
        from desktop.singleton import _is_pid_alive
        assert _is_pid_alive(-1) is False
        assert _is_pid_alive(0) is False

    def test_very_large_pid_is_dead(self):
        """A PID that no process could plausibly hold — should be dead."""
        from desktop.singleton import _is_pid_alive
        # PID space on macOS is 0-99998 by default; 9_999_999 is safe.
        assert _is_pid_alive(9_999_999) is False

    def test_windows_uses_non_destructive_process_query(self, monkeypatch):
        """Windows must not use ``os.kill(pid, 0)`` as a liveness probe."""
        import desktop.singleton as singleton

        queried: list[int] = []
        monkeypatch.setattr(singleton.sys, "platform", "win32")
        monkeypatch.setattr(
            singleton,
            "_is_windows_pid_alive",
            lambda pid: queried.append(pid) or True,
        )

        assert singleton._is_pid_alive(1) is True
        assert queried == [1]


# ---------------------------------------------------------------------- #
# _read_pid_file — defensive parser
# ---------------------------------------------------------------------- #


class TestReadPidFile:
    def test_missing_file_returns_none(self, tmp_path):
        from desktop.singleton import _read_pid_file
        assert _read_pid_file(tmp_path / "missing.pid") is None

    def test_valid_pid_round_trips(self, tmp_path):
        from desktop.singleton import _read_pid_file
        pf = tmp_path / "valid.pid"
        pf.write_text("12345")
        assert _read_pid_file(pf) == 12345

    def test_non_integer_returns_none(self, tmp_path):
        from desktop.singleton import _read_pid_file
        pf = tmp_path / "garbage.pid"
        pf.write_text("not a number")
        assert _read_pid_file(pf) is None

    def test_negative_or_zero_returns_none(self, tmp_path):
        from desktop.singleton import _read_pid_file
        for val in ("-1", "0"):
            pf = tmp_path / "bad.pid"
            pf.write_text(val)
            assert _read_pid_file(pf) is None

    def test_whitespace_is_tolerated(self, tmp_path):
        """Real PID files sometimes have trailing newlines."""
        from desktop.singleton import _read_pid_file
        pf = tmp_path / "whitespace.pid"
        pf.write_text("  12345  \n")
        assert _read_pid_file(pf) == 12345


# ---------------------------------------------------------------------- #
# acquire_singleton — happy path + race cases
# ---------------------------------------------------------------------- #


class TestAcquireSingleton:
    def test_acquire_writes_pid_file_with_our_pid(self, tmp_path):
        from desktop.singleton import _read_pid_file, acquire_singleton
        pid_file = tmp_path / "launcher.pid"
        handle = acquire_singleton(pid_file)
        try:
            assert pid_file.exists()
            assert _read_pid_file(pid_file) == os.getpid()
        finally:
            handle.release()

    def test_acquire_creates_parent_directory(self, tmp_path):
        from desktop.singleton import acquire_singleton
        pid_file = tmp_path / "nested" / "deep" / "launcher.pid"
        handle = acquire_singleton(pid_file)
        try:
            assert pid_file.exists()
            assert pid_file.parent.is_dir()
        finally:
            handle.release()

    def test_acquire_rejects_when_alive_lock_exists(self, tmp_path):
        """The PID file's owner is alive — second acquire must fail."""
        from desktop.singleton import (
            AlreadyRunning,
            acquire_singleton,
        )
        pid_file = tmp_path / "launcher.pid"
        # Write our own PID — definitely alive (we're running it)
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))
        with pytest.raises(AlreadyRunning) as exc_info:
            acquire_singleton(pid_file)
        # Exception should expose the live PID
        assert exc_info.value.pid == os.getpid()
        assert exc_info.value.pid_file == pid_file

    def test_acquire_cleans_up_stale_pid_and_proceeds(self, tmp_path):
        """A PID file owned by a dead process must be cleaned + reacquired."""
        from desktop.singleton import _read_pid_file, acquire_singleton
        pid_file = tmp_path / "launcher.pid"
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        # Write a PID that doesn't exist
        pid_file.write_text("9999998")
        # Acquire should silently clean + take the lock
        handle = acquire_singleton(pid_file)
        try:
            assert _read_pid_file(pid_file) == os.getpid()
        finally:
            handle.release()

    def test_acquire_handles_garbage_pid_file(self, tmp_path):
        """A corrupted PID file should be cleaned up + acquisition proceeds."""
        from desktop.singleton import _read_pid_file, acquire_singleton
        pid_file = tmp_path / "launcher.pid"
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text("not a pid")
        handle = acquire_singleton(pid_file)
        try:
            assert _read_pid_file(pid_file) == os.getpid()
        finally:
            handle.release()


# ---------------------------------------------------------------------- #
# SingletonHandle.release — idempotency + safety
# ---------------------------------------------------------------------- #


class TestSingletonRelease:
    def test_release_removes_pid_file(self, tmp_path):
        from desktop.singleton import acquire_singleton
        pid_file = tmp_path / "launcher.pid"
        handle = acquire_singleton(pid_file)
        assert pid_file.exists()
        handle.release()
        assert not pid_file.exists()

    def test_release_is_idempotent(self, tmp_path):
        """atexit + explicit release both call this — second call must be safe."""
        from desktop.singleton import acquire_singleton
        pid_file = tmp_path / "launcher.pid"
        handle = acquire_singleton(pid_file)
        handle.release()
        handle.release()  # must not raise
        handle.release()
        assert not pid_file.exists()

    def test_release_does_not_clobber_another_instances_lock(self, tmp_path):
        """Race scenario: we crashed, our PID file got cleaned up by a
        NEW launcher which acquired the lock with ITS pid. Then our
        cleanup machinery (atexit, signal handler) runs late. We must
        NOT delete the new launcher's lock."""
        from desktop.singleton import (
            SingletonHandle,
            _read_pid_file,
            acquire_singleton,
        )
        pid_file = tmp_path / "launcher.pid"
        # Simulate having held it
        original_handle = acquire_singleton(pid_file)
        # Simulate a new launcher taking over (write a different PID
        # that's actually alive — use init)
        pid_file.write_text("1")
        # Late release from original handle — must NOT remove
        original_handle.release()
        assert pid_file.exists()
        assert _read_pid_file(pid_file) == 1


# ---------------------------------------------------------------------- #
# default_pid_file — canonical location
# ---------------------------------------------------------------------- #


def test_default_pid_file_location(tmp_path, monkeypatch):
    test_home = tmp_path / "home"
    test_home.mkdir()
    monkeypatch.setenv("HOME", str(test_home))
    monkeypatch.setenv("USERPROFILE", str(test_home))
    from desktop.singleton import default_pid_file
    p = default_pid_file()
    assert p.name == "launcher.pid"
    assert p.parent.name == ".deeper-notebook"
    assert p.parent.parent == test_home


# ---------------------------------------------------------------------- #
# AlreadyRunning — message + attribute carrying
# ---------------------------------------------------------------------- #


class TestAlreadyRunning:
    def test_exception_message_is_user_friendly(self, tmp_path):
        """Caller may show this to the user in a dialog. Should be
        readable + actionable."""
        from desktop.singleton import AlreadyRunning
        pid_file = tmp_path / "launcher.pid"
        exc = AlreadyRunning(pid=12345, pid_file=pid_file)
        msg = str(exc)
        assert "12345" in msg
        assert "already running" in msg.lower()
        assert str(pid_file) in msg

    def test_exception_carries_machine_readable_pid(self, tmp_path):
        """UI code uses .pid to offer 'kill other instance' affordances."""
        from desktop.singleton import AlreadyRunning
        exc = AlreadyRunning(pid=42, pid_file=tmp_path / "x.pid")
        assert exc.pid == 42
        assert isinstance(exc.pid, int)


# ---------------------------------------------------------------------- #
# reap_orphans — best-effort but correct
# ---------------------------------------------------------------------- #


class TestReapOrphans:
    def test_dry_run_does_not_kill_anything(self, tmp_path):
        """The dry_run flag is for diagnostic scans — must return
        candidates without sending signals. Used by `make status`
        and the test suite itself."""
        from desktop.singleton import reap_orphans
        # Scan with paths that won't match anything — should return []
        orphans = reap_orphans(
            bundle_paths=[tmp_path / "nonexistent"],
            dry_run=True,
        )
        assert orphans == []

    def test_does_not_target_self_or_parent(self, tmp_path):
        """Even if our own cmdline matches a bundle_path, we must NOT
        appear in the orphan list — the test runner is alive!"""
        # Use python's actual install path — guaranteed to match
        # /something/ in our own cmdline (python interpreter path)
        import sys

        from desktop.singleton import reap_orphans
        python_path = Path(sys.executable).parent
        orphans = reap_orphans(bundle_paths=[python_path], dry_run=True)
        own_pid = os.getpid()
        parent_pid = os.getppid()
        for orphan in orphans:
            assert orphan.pid != own_pid
            assert orphan.pid != parent_pid

    def test_returns_empty_list_when_no_matches(self, tmp_path):
        from desktop.singleton import reap_orphans
        orphans = reap_orphans(
            bundle_paths=[tmp_path / "definitely-not-a-real-path-v0_7_142"],
            dry_run=True,
        )
        assert orphans == []


# ---------------------------------------------------------------------- #
# End-to-end — full acquire/release cycle survives atexit registration
# ---------------------------------------------------------------------- #


def test_acquire_followed_by_release_leaves_no_file(tmp_path):
    """The whole point: after legitimate shutdown, the PID file is
    gone — so the NEXT launch's stale-check sees no file and proceeds
    without warning."""
    from desktop.singleton import acquire_singleton
    pid_file = tmp_path / "launcher.pid"
    handle = acquire_singleton(pid_file)
    assert pid_file.exists()
    handle.release()
    assert not pid_file.exists()


def test_two_sequential_acquires_work(tmp_path):
    """After release, a fresh acquire must succeed without complaint —
    this is the daily-use pattern (start, work, Cmd+Q, start again)."""
    from desktop.singleton import acquire_singleton
    pid_file = tmp_path / "launcher.pid"
    h1 = acquire_singleton(pid_file)
    h1.release()
    h2 = acquire_singleton(pid_file)
    try:
        assert pid_file.exists()
    finally:
        h2.release()


def test_acquire_callback_runs_after_lock_held(tmp_path):
    """on_acquire_callback is the place to do setup that REQUIRES the
    lock (e.g., overwriting state files). Must run AFTER the lock is
    written."""
    from desktop.singleton import _read_pid_file, acquire_singleton
    pid_file = tmp_path / "launcher.pid"
    callback_saw_pid: dict[str, int | None] = {"pid": None}

    def callback() -> None:
        callback_saw_pid["pid"] = _read_pid_file(pid_file)

    handle = acquire_singleton(pid_file, on_acquire_callback=callback)
    try:
        # By the time the callback ran, our PID was already written
        assert callback_saw_pid["pid"] == os.getpid()
    finally:
        handle.release()


def test_callback_failure_releases_lock(tmp_path):
    """If the setup callback crashes, we shouldn't be left with an
    orphan PID file blocking the next launch."""
    from desktop.singleton import acquire_singleton
    pid_file = tmp_path / "launcher.pid"

    def boom() -> None:
        raise ValueError("simulated setup failure")

    with pytest.raises(RuntimeError, match="post-acquire callback failed"):
        acquire_singleton(pid_file, on_acquire_callback=boom)
    # Lock should have been released as part of the failure cleanup
    assert not pid_file.exists()
