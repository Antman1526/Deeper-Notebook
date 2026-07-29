"""v0.7.142 — Singleton launcher enforcement + orphan reaper.

Why this exists (real user incident, 2026-05-19):

  User double-clicked `Deeper Notebook.app` multiple times during
  debugging. Each click spawned a fresh launcher process tree (uvicorn
  API + Next.js + worker + SurrealDB binary) with independent dynamic
  ports. The launchers were completely unaware of each other. Closing
  a Chromium window didn't kill the launcher behind it. After ~5
  debug cycles the user had:

    * 4 zombie Next.js processes (PIDs 35217, 37678, 85061, 94829)
    * 3 zombie surreal-commands workers from May 11
    * 1 live + several zombie API processes

  The browser window the user was looking at was attached to a zombie
  launcher whose API had since been overwritten. "Unable to Connect
  to API Server" was the symptom; the cause was process accumulation.

This module provides two primitives that, together, eliminate the
class of bug:

  1. `acquire_singleton(...)` — writes a PID file at acquire time
     and refuses to start if another live instance already holds it.
     A stale PID file (process is dead) gets cleaned up + acquisition
     proceeds. The returned `SingletonHandle` releases the lock when
     it's `.release()`'d OR when the process exits via atexit.

  2. `reap_orphans(...)` — best-effort scan for processes whose
     executable path is inside our bundled venv / runtime but whose
     parent is no longer alive (or whose grandparent is init).
     Returns a list of `(pid, cmdline)` tuples the caller can SIGTERM
     before proceeding. Defends against the case where a previous
     launcher was SIGKILLed / segfaulted before its atexit could run.

The two together cover the common cases: normal exits go through
SingletonHandle.release(); crashed launchers leave a stale PID
file that the next acquire cleans up; orphaned children whose
parent died before reaping them get caught by reap_orphans().

Cross-platform: pure stdlib. POSIX uses `os.kill(pid, 0)`; Windows
uses its query-only `OpenProcess` API because Windows does not expose
POSIX signal-zero semantics. `psutil` would be cleaner but we don't
want a new dep in the bundle just for this.
"""
from __future__ import annotations

import atexit
import errno
import logging
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from desktop.data_root import active_data_root

log = logging.getLogger(__name__)


# Public exception. Caller catches this to decide between "exit
# gracefully" (typical for a desktop app — show "Already running"
# dialog) vs "force-acquire" (rare; only the operator should choose).
class AlreadyRunning(RuntimeError):
    """Raised when another live launcher instance holds the singleton.

    `pid` is the live competitor's PID so callers can offer "kill
    other instance and continue" affordances.
    """

    def __init__(self, pid: int, pid_file: Path):
        super().__init__(
            f"Another Deeper Notebook launcher is already running "
            f"(PID {pid}; lock at {pid_file}). Quit the existing app "
            "or wait for its shutdown before relaunching."
        )
        self.pid = pid
        self.pid_file = pid_file


def _is_pid_alive(pid: int) -> bool:
    """True iff the OS still has a process with this PID.

    POSIX uses `os.kill(pid, 0)`, which sends no signal and exercises
    the same permission/existence check as a real signal. Windows uses
    a query-only process handle because `os.kill(pid, 0)` is not a safe
    equivalent there. Access denied means the process exists but belongs
    to another user, which still counts as alive for singleton purposes.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _is_windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except OSError as exc:
        # ESRCH = no such process. EPERM = exists but we don't own it
        # (still alive). Any other errno is unexpected — treat as
        # alive (conservative; better to refuse acquire than to
        # accidentally double-launch).
        if exc.errno == errno.ESRCH:
            return False
        return True
    return True


def _is_windows_pid_alive(pid: int) -> bool:
    """Query a Windows process without using ``os.kill(pid, 0)``.

    Windows does not implement POSIX signal zero semantics. In particular,
    probing PID 1 through ``os.kill`` can disrupt the runner's process group.
    ``OpenProcess`` with query-only access is non-destructive and treats an
    access-denied result as evidence that the process still exists.
    """
    import ctypes

    process_query_limited_information = 0x1000
    error_access_denied = 5
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return ctypes.get_last_error() == error_access_denied


def _read_pid_file(pid_file: Path) -> int | None:
    """Read + parse a PID file. Returns None if missing, malformed,
    or contains a non-positive integer. Caller decides what 'None'
    means in context (usually 'safe to acquire')."""
    try:
        raw = pid_file.read_text().strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.warning("Could not read PID file %s: %s", pid_file, exc)
        return None
    try:
        pid = int(raw)
    except ValueError:
        log.warning("PID file %s contains non-integer %r", pid_file, raw)
        return None
    return pid if pid > 0 else None


@dataclass
class SingletonHandle:
    """Holds the lock. Release via `.release()` or implicit atexit."""

    pid_file: Path
    _released: bool = False

    def release(self) -> None:
        """Remove the PID file. Safe to call multiple times — only the
        first call removes; subsequent calls are no-ops. Both
        explicit release and the atexit handler call this; the idempotency
        is what lets them coexist."""
        if self._released:
            return
        self._released = True
        try:
            # Read what's there: only delete if it's OUR PID. Defends
            # against the race where a SECOND launcher acquired our
            # PID file after we crashed-but-didn't-cleanup, then
            # WE come back and would otherwise erase its lock.
            existing = _read_pid_file(self.pid_file)
            if existing == os.getpid():
                self.pid_file.unlink(missing_ok=True)
            elif existing is not None:
                log.debug(
                    "Singleton release: PID file now owned by PID %d "
                    "(not us — %d); leaving alone",
                    existing, os.getpid(),
                )
        except Exception as exc:
            log.warning("Could not release singleton at %s: %s",
                        self.pid_file, exc)


@dataclass
class SignalHandlerRegistration:
    """Own the POSIX wakeup pipe used by the native-loop signal bridge."""

    wakeup_read_fd: int | None = None
    wakeup_write_fd: int | None = None
    previous_wakeup_fd: int = -1
    _closed: bool = False

    def close(self) -> None:
        """Restore the previous wakeup fd and close this registration."""
        if self._closed:
            return
        self._closed = True
        if self.wakeup_write_fd is not None:
            try:
                signal.set_wakeup_fd(self.previous_wakeup_fd)
            except (OSError, ValueError):
                pass
            try:
                os.write(self.wakeup_write_fd, b"\0")
            except OSError:
                pass
        for descriptor in (self.wakeup_write_fd, self.wakeup_read_fd):
            if descriptor is None:
                continue
            try:
                os.close(descriptor)
            except OSError:
                pass


def acquire_singleton(
    pid_file: Path,
    *,
    on_acquire_callback: Callable[[], None] | None = None,
    on_signal_cleanup: Callable[[int], None] | None = None,
) -> SingletonHandle:
    """Acquire the singleton lock or raise `AlreadyRunning`.

    `pid_file` should be a path under the per-user state dir (e.g.,
    `~/.deeper-notebook/launcher.pid`). Parent directory is
    created if missing.

    Behavior:
      - If `pid_file` is missing or stale (PID inside is dead): take
        the lock, write our PID, return a SingletonHandle.
      - If `pid_file` contains a live PID: raise AlreadyRunning(pid).

    Race-safety: we use exclusive O_CREAT to write the new PID file.
    Two launchers starting at the same instant — exactly one wins
    the create-exclusive; the loser sees the new file and treats it
    as a live competitor.
    """
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    # Check if an existing PID file is alive. If so, fail fast.
    # If stale, remove it. Either way, fall through to acquire.
    existing_pid = _read_pid_file(pid_file)
    if existing_pid is not None:
        if _is_pid_alive(existing_pid):
            raise AlreadyRunning(existing_pid, pid_file)
        log.info(
            "Removing stale PID file %s (PID %d is no longer alive)",
            pid_file, existing_pid,
        )
        try:
            pid_file.unlink(missing_ok=True)
        except OSError as exc:
            # Some other process may have raced us — recheck.
            log.warning("Could not remove stale PID file: %s", exc)
            existing_pid = _read_pid_file(pid_file)
            if existing_pid is not None and _is_pid_alive(existing_pid):
                raise AlreadyRunning(existing_pid, pid_file) from exc
    elif pid_file.exists():
        # File present but unparseable (corrupted, partially-written,
        # left over from an old format). Treat as stale — clean up so
        # the O_EXCL acquire below doesn't trip on it. This is the
        # garbage-PID-file recovery path that test
        # `test_acquire_handles_garbage_pid_file` pins.
        log.info(
            "Removing unparseable PID file %s (no readable PID inside)",
            pid_file,
        )
        try:
            pid_file.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Could not remove garbage PID file: %s", exc)

    # Exclusive create — race-safe. If another launcher won the create,
    # we'll get FileExistsError and treat them as the live competitor.
    try:
        fd = os.open(
            str(pid_file),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o644,
        )
    except FileExistsError as exc:
        # Someone beat us to it between the stale-check and now.
        # Read who owns it and treat them as live.
        racer_pid = _read_pid_file(pid_file)
        if racer_pid is not None:
            raise AlreadyRunning(racer_pid, pid_file) from exc
        # Can't read it — surface the original error
        raise

    try:
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # Best-effort fsync; not all filesystems support it
                pass
    except Exception:
        # Clean up the partial file on write failure
        try:
            pid_file.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    handle = SingletonHandle(pid_file=pid_file)

    # Wire up automatic cleanup. atexit fires on normal sys.exit() +
    # clean shutdown; signal handlers cover SIGTERM (macOS Force Quit,
    # kill from another process). SIGKILL can't be trapped — that's
    # what reap_orphans is for.
    atexit.register(handle.release)
    _install_signal_handlers(
        handle,
        on_signal_cleanup=on_signal_cleanup,
    )

    if on_acquire_callback is not None:
        try:
            on_acquire_callback()
        except Exception as exc:
            # Callback failed; release the lock so we don't pin it
            handle.release()
            raise RuntimeError(
                f"Singleton acquired but post-acquire callback failed: {exc}"
            ) from exc

    return handle


def _install_signal_handlers(
    handle: SingletonHandle,
    *,
    on_signal_cleanup: Callable[[int], None] | None = None,
) -> SignalHandlerRegistration:
    """Register SIGTERM + SIGINT handlers that release the lock then
    exit normally. macOS's Force Quit sends SIGTERM; Ctrl+C in a
    terminal sends SIGINT. Both should trigger graceful cleanup.

    We don't trap SIGKILL (impossible) or SIGSEGV (defensive — let
    the OS produce a core dump). Those cases are caught by the
    next launcher's stale-PID-file detection."""

    shutdown_lock = threading.Lock()
    shutdown_started = False

    def _shutdown(signum: int) -> None:
        nonlocal shutdown_started
        with shutdown_lock:
            if shutdown_started:
                return
            shutdown_started = True
        log.info(
            "Received signal %s — cleaning runtime + exiting",
            signal.Signals(signum).name if hasattr(signal, "Signals") else signum,
        )
        try:
            if on_signal_cleanup is not None:
                on_signal_cleanup(signum)
        except BaseException:
            log.exception("Signal-triggered runtime cleanup failed")
        finally:
            handle.release()
            # Native Cocoa/WebKit loops may catch SystemExit raised by a Python
            # signal handler. Runtime cleanup and singleton release have both
            # completed, so terminate unconditionally instead of relying on
            # the native event loop to unwind back through desktop.app.run().
            logging.shutdown()
            os._exit(128 + signum)

    def _handler(signum: int, frame) -> None:
        _shutdown(signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError) as exc:
            # ValueError fires if we're not in the main thread; OSError
            # on platforms that don't allow handlers for the signal.
            # Best-effort — atexit still covers the normal-exit case.
            log.debug("Could not install handler for %s: %s", sig, exc)

    registration = SignalHandlerRegistration()
    if sys.platform == "win32" or not hasattr(signal, "set_wakeup_fd"):
        return registration

    read_fd: int | None = None
    write_fd: int | None = None
    try:
        read_fd, write_fd = os.pipe()
        os.set_blocking(write_fd, False)
        previous_wakeup_fd = signal.set_wakeup_fd(
            write_fd,
            warn_on_full_buffer=False,
        )
    except (OSError, ValueError) as exc:
        log.debug("Could not install native-loop signal bridge: %s", exc)
        for descriptor in (write_fd, read_fd):
            if descriptor is None:
                continue
            try:
                os.close(descriptor)
            except OSError:
                pass
        return registration

    registration = SignalHandlerRegistration(
        wakeup_read_fd=read_fd,
        wakeup_write_fd=write_fd,
        previous_wakeup_fd=previous_wakeup_fd,
    )

    def _wakeup_loop() -> None:
        assert read_fd is not None
        while True:
            try:
                payload = os.read(read_fd, 64)
            except OSError:
                return
            if not payload:
                return
            for encoded_signal in payload:
                if encoded_signal in (signal.SIGTERM, signal.SIGINT):
                    _shutdown(encoded_signal)
                    return

    threading.Thread(
        target=_wakeup_loop,
        name="native-signal-shutdown",
        daemon=True,
    ).start()
    return registration


# ---------------------------------------------------------------------- #
# Orphan reaper — defends against prior crashed launchers that died
# before their atexit could run, leaving children orphaned to init.
# ---------------------------------------------------------------------- #


@dataclass
class OrphanProcess:
    pid: int
    cmdline: str


def reap_orphans(
    *,
    bundle_paths: list[Path],
    dry_run: bool = False,
) -> list[OrphanProcess]:
    """Find processes whose executable path lives inside any of
    `bundle_paths` (typically `~/.deeper-notebook/venv` and
    `desktop/bin/`) and whose parent is no longer this launcher.

    Cross-platform: uses `ps -ef` on POSIX, `tasklist /v /fo csv` on
    Windows. Returns list of orphans found. If `dry_run=False`, also
    SIGTERMs each (POSIX) or `taskkill /pid` (Windows). Callers
    should `time.sleep(0.5)` after a non-dry run to let the OS reap.

    Why this is best-effort:
      - process-listing format varies subtly across OS versions
      - we can only kill processes we own (UID match on POSIX,
        same-session match on Windows)
      - a determined orphan can ignore SIGTERM — the next SIGKILL
        is up to the operator

    This is the "kill -9 me" / Force-Quit safety net; the primary
    defense is the SingletonHandle which prevents accumulation
    under normal conditions.
    """
    # v0.7.143 — dispatch to platform-specific scanner. Both return
    # the same (pid, ppid, cmdline) tuple shape; the filtering +
    # kill loop below is shared.
    if sys.platform == "win32":
        candidates = _list_processes_windows()
    else:
        candidates = _list_processes_posix()

    if not candidates:
        return []

    orphans: list[OrphanProcess] = []
    own_pid = os.getpid()
    parent_pid = os.getppid()
    path_strs = [str(p.resolve()) for p in bundle_paths]

    for pid, ppid, cmdline in candidates:
        # Don't kill ourselves / our parent
        if pid in (own_pid, parent_pid):
            continue
        # Check if cmdline mentions any of our bundle paths
        if not any(p in cmdline for p in path_strs):
            continue
        # Narrow to "real" orphans: ppid in {0, 1} (init/system) or
        # the parent PID is no longer alive (dead sibling launcher).
        # If the parent is alive AND not us, leave it alone — that's
        # a different running instance's child.
        if ppid not in (0, 1) and _is_pid_alive(ppid):
            continue
        orphans.append(OrphanProcess(pid=pid, cmdline=cmdline))

    if not dry_run:
        for orphan in orphans:
            _kill_orphan(orphan.pid, orphan.cmdline)

    return orphans


def _list_processes_posix() -> list[tuple[int, int, str]]:
    """Return [(pid, ppid, cmdline), ...] using `ps -eo`. Empty list on
    any failure (ps not available, parse error, timeout)."""
    import subprocess
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,ppid,command"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.debug("ps not available for orphan reap: %s", exc)
        return []
    if result.returncode != 0:
        return []
    out: list[tuple[int, int, str]] = []
    for line in result.stdout.splitlines()[1:]:  # skip header
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        out.append((pid, ppid, parts[2]))
    return out


def _list_processes_windows() -> list[tuple[int, int, str]]:
    """Windows equivalent of _list_processes_posix.

    Uses `wmic process get ProcessId,ParentProcessId,CommandLine /format:csv`
    which is universally available since Windows 7. (Newer versions
    deprecated wmic in favor of Get-CimInstance, but wmic still works
    and is faster to invoke than spawning PowerShell.)

    CSV columns: Node, CommandLine, ParentProcessId, ProcessId
    Note that wmic prefixes with a Node column (the hostname) and the
    column order may not match the requested order — we use header
    parsing to be defensive.

    If wmic isn't on PATH (Windows Server Core, very stripped-down
    container images), we fall back to `tasklist /v /fo csv` which
    gives us the PID + command but NOT the PPID. In that fallback
    case, the ppid-aliveness check is skipped (we treat all matches
    as candidates) — slightly more aggressive but still constrained
    to our bundle paths.
    """
    import csv
    import io
    import subprocess

    # First attempt: wmic with PPID for proper orphan detection.
    try:
        result = subprocess.run(
            [
                "wmic", "process", "get",
                "ProcessId,ParentProcessId,CommandLine",
                "/format:csv",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return _parse_wmic_csv(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.debug("wmic unavailable: %s; falling back to tasklist", exc)

    # Fallback: tasklist (no PPID).
    try:
        result = subprocess.run(
            ["tasklist", "/v", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.debug("tasklist also unavailable: %s", exc)
        return []
    if result.returncode != 0:
        return []

    out: list[tuple[int, int, str]] = []
    reader = csv.reader(io.StringIO(result.stdout))
    for row in reader:
        if len(row) < 2:
            continue
        try:
            pid = int(row[1])
        except (ValueError, IndexError):
            continue
        # tasklist columns vary across Windows versions; we just want
        # the image name + window title which together usually contain
        # enough of the cmdline for our path-match.
        cmdline_proxy = " ".join(c for c in row if c)
        # PPID unknown — pass 0 (init) so the ppid-liveness check
        # treats this as a candidate regardless. Caller's bundle-path
        # filter still constrains us.
        out.append((pid, 0, cmdline_proxy))
    return out


def _parse_wmic_csv(text: str) -> list[tuple[int, int, str]]:
    """Parse `wmic ... /format:csv` output.

    wmic CSV is quirky: it emits a BOM, has blank lines between
    records, and column order doesn't match the requested order
    (it's alphabetical: CommandLine, Node, ParentProcessId, ProcessId).
    We read the header row to map column names → indices.
    """
    import csv
    import io

    text = text.lstrip("﻿").strip()
    if not text:
        return []
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if r and any(cell.strip() for cell in r)]
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    try:
        i_pid = header.index("ProcessId")
        i_ppid = header.index("ParentProcessId")
        i_cmd = header.index("CommandLine")
    except ValueError as exc:
        log.debug("Unexpected wmic CSV header %r: %s", header, exc)
        return []

    out: list[tuple[int, int, str]] = []
    for row in rows[1:]:
        if len(row) <= max(i_pid, i_ppid, i_cmd):
            continue
        try:
            pid = int(row[i_pid].strip())
            ppid = int(row[i_ppid].strip())
        except ValueError:
            continue
        out.append((pid, ppid, row[i_cmd].strip() or ""))
    return out


def _kill_orphan(pid: int, cmdline: str) -> None:
    """Send SIGTERM (POSIX) or `taskkill /pid` (Windows). Best-effort —
    log failures at debug since the orphan may have died on its own
    between our enumeration + kill call."""
    truncated = cmdline[:80]
    if sys.platform == "win32":
        import subprocess
        try:
            subprocess.run(
                ["taskkill", "/pid", str(pid), "/t"],
                capture_output=True, text=True, timeout=5,
            )
            log.info("Reaped orphan %d: %s", pid, truncated)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log.debug("Could not taskkill %d: %s", pid, exc)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
            log.info("Reaped orphan %d: %s", pid, truncated)
        except OSError as exc:
            log.debug("Could not SIGTERM orphan %d: %s", pid, exc)


def default_pid_file() -> Path:
    """Canonical PID-file location for the desktop launcher."""
    return active_data_root() / "launcher.pid"
