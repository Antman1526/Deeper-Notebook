"""v0.8.130 — a window that shows first-launch setup while it happens.

The first-run wizard has a "Setting up" screen with a live list of startup steps,
but it was never seen: the wizard window closed the instant settings were saved,
and the launcher's startup phases only ran after that. First-launch setup takes
minutes (a Python environment, dependencies, model servers), and for all of it
the user had no window at all.

The startup phases must stay on the launcher's main thread: the supervisor
installs its signal handlers there (they are what stops the child services when
the app is told to quit), and its "already running" dialog is a native one. The
web view needs a main thread too. So the progress screen runs in a second
process: this module, started by the launcher with the wizard server's port. It
only displays; it starts no services and takes no lock.

The launcher closes it when the main window is about to open. If the launcher
dies first, the helper notices and closes itself rather than sit on screen
forever.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time

log = logging.getLogger(__name__)

FLAG = "--setup-progress-window"
_PARENT_POLL_SECONDS = 1.0


def parse_args(argv: list[str]) -> tuple[int, int] | None:
    """(port, launcher pid) when this process was started as the helper."""
    if len(argv) != 3 or argv[0] != FLAG:
        return None
    try:
        port, parent_pid = int(argv[1]), int(argv[2])
    except ValueError:
        return None
    if not 0 < port < 65536 or parent_pid <= 0:
        return None
    return port, parent_pid


def command_for(port: int, parent_pid: int) -> list[str]:
    arguments = [FLAG, str(port), str(parent_pid)]
    if getattr(sys, "frozen", False):
        # The packaged app: its own binary is the only interpreter with a web view.
        return [sys.executable, *arguments]
    return [sys.executable, "-m", "desktop", *arguments]


def spawn(port: int) -> subprocess.Popen | None:
    """Start the helper. Never raises: a launch must not fail for want of it."""
    try:
        return subprocess.Popen(
            command_for(port, os.getpid()),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:  # noqa: BLE001 — display only; the launch goes on
        log.warning("setup progress window not started: %s", exc)
        return None


def close(process: subprocess.Popen | None) -> None:
    """Stop the helper. Safe to call twice, and with nothing to stop."""
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    except Exception as exc:  # noqa: BLE001
        log.debug("setup progress window did not stop cleanly: %s", exc)


def parent_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        # A finished child of ours stays a zombie until reaped; reap it if so.
        try:
            if os.waitpid(pid, os.WNOHANG)[0] == pid:
                return False
        except ChildProcessError:
            pass
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def main(argv: list[str]) -> int:
    parsed = parse_args(argv)
    if parsed is None:
        return 2
    port, parent_pid = parsed

    import webview

    window = webview.create_window(
        "Deeper Notebook",
        f"http://127.0.0.1:{port}/?screen=setting-up",
        width=720,
        height=540,
    )

    def _leave_with_the_launcher() -> None:
        while parent_alive(parent_pid):
            time.sleep(_PARENT_POLL_SECONDS)
        try:
            window.destroy()
        except Exception:  # noqa: BLE001 — the window may already be gone
            pass
        # A web view loop can outlive its last window; do not linger.
        os._exit(0)

    threading.Thread(target=_leave_with_the_launcher, daemon=True).start()
    webview.start()
    return 0
