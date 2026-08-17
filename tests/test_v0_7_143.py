"""v0.7.143 — UI for AlreadyRunning + Windows reaper.

Two pieces, tested separately:

  1. `_handle_already_running` in desktop/app.py — shows a native
     dialog ("Quit existing instance?"). The dialog itself can't
     be tested in CI (headless), but we CAN test the post-choice
     branch logic: SIGTERM the other launcher, poll for exit,
     return True/False per outcome.

  2. `_list_processes_windows` + `_parse_wmic_csv` + `_kill_orphan`
     in desktop/singleton.py — Windows side of the cross-platform
     reaper. Tested via fixture wmic CSV output captured from a
     real Windows machine.
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------- #
# Part 1 — desktop/app.py _handle_already_running branches
# ---------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _tkinter_available(monkeypatch):
    """v0.8.99 — make these tests runnable on a Python built without Tk.

    `desktop.app._handle_already_running` imports tkinter lazily inside the
    function, and each test below patches `tkinter.Tk` / `tkinter.messagebox`.
    On an interpreter without `_tkinter` (Homebrew python@3.12 is the common
    case, and `.build-venv` uses it) the patch target itself fails to import,
    so all five tests errored — while passing under the build gate, whose
    bundled python-build-standalone ships Tk. That divergence read as flake and
    masked a genuine bug in a neighbouring suite.

    When the real tkinter is importable this fixture does nothing, so the tests
    keep exercising the true module. When it is absent we install a minimal
    stub so the branch logic is still covered rather than skipped — the dialog
    is mocked in every test anyway, so no behaviour is lost.
    """
    try:
        import tkinter  # noqa: F401
        import tkinter.messagebox  # noqa: F401
    except Exception:
        import types

        tk_stub = types.ModuleType("tkinter")
        tk_stub.Tk = MagicMock(name="Tk")
        messagebox_stub = types.ModuleType("tkinter.messagebox")
        messagebox_stub.askyesno = MagicMock(name="askyesno", return_value=False)
        tk_stub.messagebox = messagebox_stub
        monkeypatch.setitem(sys.modules, "tkinter", tk_stub)
        monkeypatch.setitem(sys.modules, "tkinter.messagebox", messagebox_stub)


class TestHandleAlreadyRunning:
    """The dialog itself can't be rendered in CI, but every branch
    after the user's choice is testable."""

    def _make_exc(self, pid: int = 99999, tmp_path: Path | None = None):
        from desktop.singleton import AlreadyRunning
        return AlreadyRunning(
            pid=pid,
            pid_file=(tmp_path or Path("/tmp")) / "launcher.pid",
        )

    def test_returns_false_when_user_cancels_via_tk(self, tmp_path):
        """User clicked No in the messagebox.askyesno — caller should
        NOT retry start_all; instead exit cleanly."""
        from desktop.app import _handle_already_running

        ctx = MagicMock()
        exc = self._make_exc(tmp_path=tmp_path)

        with patch("tkinter.Tk") as MockTk, \
             patch("tkinter.messagebox.askyesno", return_value=False):
            MockTk.return_value.withdraw = MagicMock()
            MockTk.return_value.destroy = MagicMock()
            result = _handle_already_running(exc, ctx)
        assert result is False

    def test_returns_true_when_user_accepts_and_other_pid_dies(self, tmp_path):
        """User clicked Yes, we SIGTERM the other PID, polling detects
        it died, caller should retry start_all."""
        from desktop.app import _handle_already_running

        ctx = MagicMock()
        pf = tmp_path / "launcher.pid"
        pf.write_text("99999")
        exc = self._make_exc(pid=99999, tmp_path=tmp_path)

        # Tk dialog returns True (user said Yes).
        # os.kill succeeds (we mock so we don't actually try to kill PID 99999).
        # _is_pid_alive returns True the first poll, False the second
        # (simulating the other launcher exiting).
        alive_responses = iter([True, False])

        with patch("tkinter.Tk") as MockTk, \
             patch("tkinter.messagebox.askyesno", return_value=True), \
             patch("os.kill") as mock_kill, \
             patch(
                 "desktop.singleton._is_pid_alive",
                 side_effect=lambda pid: next(alive_responses),
             ):
            MockTk.return_value.withdraw = MagicMock()
            MockTk.return_value.destroy = MagicMock()
            result = _handle_already_running(exc, ctx)
        assert result is True
        # Should have sent SIGTERM to 99999
        mock_kill.assert_called_with(99999, signal.SIGTERM)
        # Stale PID file should be cleaned up
        assert not pf.exists()

    def test_returns_false_when_kill_succeeds_but_pid_wont_die(self, tmp_path):
        """User said Yes, SIGTERM sent, but the other process is
        stuck. After 10s poll deadline, return False (caller exits
        rather than risk a port collision)."""
        from desktop.app import _handle_already_running

        ctx = MagicMock()
        exc = self._make_exc(pid=99999, tmp_path=tmp_path)

        with patch("tkinter.Tk") as MockTk, \
             patch("tkinter.messagebox.askyesno", return_value=True), \
             patch("os.kill"), \
             patch("desktop.singleton._is_pid_alive", return_value=True), \
             patch("time.monotonic", side_effect=[0.0, 11.0]):  # immediately past deadline
            MockTk.return_value.withdraw = MagicMock()
            MockTk.return_value.destroy = MagicMock()
            result = _handle_already_running(exc, ctx)
        assert result is False

    def test_returns_true_when_kill_fails_because_pid_already_dead(self, tmp_path):
        """If SIGTERM raises ESRCH (PID doesn't exist), the other
        process already cleaned up — clean the stale PID file and
        return True so caller retries."""
        from desktop.app import _handle_already_running

        ctx = MagicMock()
        pf = tmp_path / "launcher.pid"
        pf.write_text("99999")
        exc = self._make_exc(pid=99999, tmp_path=tmp_path)

        with patch("tkinter.Tk") as MockTk, \
             patch("tkinter.messagebox.askyesno", return_value=True), \
             patch("os.kill", side_effect=ProcessLookupError("no such process")):
            MockTk.return_value.withdraw = MagicMock()
            MockTk.return_value.destroy = MagicMock()
            result = _handle_already_running(exc, ctx)
        assert result is True
        assert not pf.exists()  # stale file cleaned

    def test_returns_false_when_no_dialog_primitive_available(self, tmp_path):
        """If BOTH Tk and osascript fail (truly headless / non-macOS
        Linux container), we don't auto-kill. Returning False sends
        the caller to the generic error path so the user sees the
        AlreadyRunning exception in the launcher log."""
        from desktop.app import _handle_already_running

        ctx = MagicMock()
        exc = self._make_exc(tmp_path=tmp_path)

        with patch("tkinter.Tk", side_effect=ImportError("no Tk")), \
             patch("subprocess.run", side_effect=FileNotFoundError("no osascript")):
            result = _handle_already_running(exc, ctx)
        assert result is False


# ---------------------------------------------------------------------- #
# Part 2 — Cross-platform reaper: Windows-side parsing
# ---------------------------------------------------------------------- #


class TestParseWmicCSV:
    """`wmic process ... /format:csv` has quirks (BOM, blank lines,
    alphabetical column order). The parser must handle real Windows
    output, not idealized CSV."""

    def test_handles_typical_wmic_output(self):
        from desktop.singleton import _parse_wmic_csv
        # Real-ish output: BOM + header (alphabetical) + 2 data rows.
        # ﻿ is the UTF-8 BOM wmic emits.
        sample = (
            "﻿Node,CommandLine,ParentProcessId,ProcessId\r\n"
            "\r\n"
            "MACHINE,\"C:\\Python\\python.exe foo.py\",1234,5678\r\n"
            "MACHINE,\"D:\\app\\node.exe server.js\",1,9999\r\n"
        )
        result = _parse_wmic_csv(sample)
        # Sorted by line order. Each tuple: (pid, ppid, cmdline).
        assert (5678, 1234, "C:\\Python\\python.exe foo.py") in result
        assert (9999, 1, "D:\\app\\node.exe server.js") in result

    def test_empty_input_returns_empty(self):
        from desktop.singleton import _parse_wmic_csv
        assert _parse_wmic_csv("") == []
        assert _parse_wmic_csv("﻿") == []
        assert _parse_wmic_csv("\r\n\r\n") == []

    def test_missing_header_columns_returns_empty(self):
        from desktop.singleton import _parse_wmic_csv
        # Header without the columns we need
        sample = "Node,Caption\r\nM,foo\r\n"
        assert _parse_wmic_csv(sample) == []

    def test_non_integer_pid_silently_skipped(self):
        """A malformed row shouldn't crash the whole scan."""
        from desktop.singleton import _parse_wmic_csv
        sample = (
            "﻿Node,CommandLine,ParentProcessId,ProcessId\r\n"
            "MACHINE,bad,notanint,5678\r\n"
            "MACHINE,good,1,9999\r\n"
        )
        result = _parse_wmic_csv(sample)
        assert len(result) == 1
        assert result[0] == (9999, 1, "good")

    def test_handles_blank_command_line(self):
        """Some Windows kernel processes have no CommandLine."""
        from desktop.singleton import _parse_wmic_csv
        sample = (
            "﻿Node,CommandLine,ParentProcessId,ProcessId\r\n"
            "MACHINE,,4,8\r\n"
        )
        result = _parse_wmic_csv(sample)
        assert result == [(8, 4, "")]


class TestReapOrphansDispatch:
    """`reap_orphans` should dispatch to the platform-appropriate
    process lister. We mock sys.platform to verify both paths."""

    def test_posix_path_uses_ps(self, tmp_path):
        """On POSIX, the function under test calls _list_processes_posix."""
        from desktop import singleton

        # Capture which lister was called
        called_posix = []
        called_windows = []

        def fake_posix() -> list:
            called_posix.append(True)
            return []

        def fake_windows() -> list:
            called_windows.append(True)
            return []

        with patch.object(singleton, "_list_processes_posix", fake_posix), \
             patch.object(singleton, "_list_processes_windows", fake_windows), \
             patch.object(singleton.sys, "platform", "darwin"):
            singleton.reap_orphans(bundle_paths=[tmp_path], dry_run=True)

        assert called_posix == [True]
        assert called_windows == []

    def test_windows_path_uses_wmic(self, tmp_path):
        from desktop import singleton

        called_posix = []
        called_windows = []

        def fake_posix() -> list:
            called_posix.append(True)
            return []

        def fake_windows() -> list:
            called_windows.append(True)
            return []

        with patch.object(singleton, "_list_processes_posix", fake_posix), \
             patch.object(singleton, "_list_processes_windows", fake_windows), \
             patch.object(singleton.sys, "platform", "win32"):
            singleton.reap_orphans(bundle_paths=[tmp_path], dry_run=True)

        assert called_posix == []
        assert called_windows == [True]


class TestKillOrphanDispatch:
    """`_kill_orphan` uses signal on POSIX, taskkill on Windows."""

    def test_posix_uses_signal(self):
        from desktop import singleton
        with patch.object(singleton.sys, "platform", "darwin"), \
             patch("os.kill") as mock_kill:
            singleton._kill_orphan(12345, "fake cmdline")
        mock_kill.assert_called_once_with(12345, signal.SIGTERM)

    def test_windows_uses_taskkill(self):
        from desktop import singleton
        with patch.object(singleton.sys, "platform", "win32"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            singleton._kill_orphan(12345, "fake cmdline")
        # taskkill /pid 12345 /t
        args = mock_run.call_args[0][0]
        assert args[0] == "taskkill"
        assert "12345" in args
        assert "/t" in args  # tree-kill flag

    def test_posix_signal_failure_is_silent(self):
        """ESRCH (PID already dead between scan + kill) is normal."""
        from desktop import singleton
        with patch.object(singleton.sys, "platform", "darwin"), \
             patch("os.kill", side_effect=ProcessLookupError):
            # Must not raise
            singleton._kill_orphan(12345, "fake cmdline")

    def test_windows_taskkill_failure_is_silent(self):
        from desktop import singleton
        with patch.object(singleton.sys, "platform", "win32"), \
             patch("subprocess.run", side_effect=FileNotFoundError):
            singleton._kill_orphan(12345, "fake cmdline")


# ---------------------------------------------------------------------- #
# Cross-cutting: existing posix tests must still pass
# ---------------------------------------------------------------------- #


def test_reap_orphans_still_returns_safely_when_self_matches():
    """v0.7.142 test still passes after the v0.7.143 cross-platform
    refactor — self and parent never appear in the orphan list."""
    from desktop.singleton import reap_orphans
    python_path = Path(sys.executable).parent
    orphans = reap_orphans(bundle_paths=[python_path], dry_run=True)
    own_pid = os.getpid()
    parent_pid = os.getppid()
    for o in orphans:
        assert o.pid != own_pid
        assert o.pid != parent_pid
