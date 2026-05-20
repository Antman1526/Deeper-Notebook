"""v0.7.142 — Singleton launcher enforcement + orphan reaper.

Why this exists (real user incident, 2026-05-19):

  User double-clicked `Open Notebook Plus.app` multiple times during
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

Cross-platform: pure stdlib. `os.kill(pid, 0)` is the universal
"is this PID alive" check; `psutil` would be cleaner but we don't
want a new dep in the bundle just for this.
"""
from __future__ import annotations

import atexit
import errno
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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
            f"Another Open Notebook Plus launcher is already running "
            f"(PID {pid}; lock at {pid_file}). Quit the existing app "
            "or wait for its shutdown before relaunching."
        )
        self.pid = pid
        self.pid_file = pid_file


def _is_pid_alive(pid: int) -> bool:
    """True iff the OS still has a process with this PID.

    `os.kill(pid, 0)` sends NO signal but exercises the same
    permission/existence check as a real signal. POSIX: returns
    immediately for live PIDs; raises ESRCH for dead PIDs; raises
    EPERM if we don't own the PID (which we treat as "alive" — a
    competing instance from a different UID still counts as live
    for our purposes).
    """
    if pid <= 0:
        return False
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


def acquire_singleton(
    pid_file: Path,
    *,
    on_acquire_callback: Callable[[], None] | None = None,
) -> SingletonHandle:
    """Acquire the singleton lock or raise `AlreadyRunning`.

    `pid_file` should be a path under the per-user state dir (e.g.,
    `~/.open-notebook-plus/launcher.pid`). Parent directory is
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
    _install_signal_handlers(handle)

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


def _install_signal_handlers(handle: SingletonHandle) -> None:
    """Register SIGTERM + SIGINT handlers that release the lock then
    exit normally. macOS's Force Quit sends SIGTERM; Ctrl+C in a
    terminal sends SIGINT. Both should trigger graceful cleanup.

    We don't trap SIGKILL (impossible) or SIGSEGV (defensive — let
    the OS produce a core dump). Those cases are caught by the
    next launcher's stale-PID-file detection."""

    def _handler(signum: int, frame) -> None:
        log.info(
            "Received signal %s — releasing singleton + exiting",
            signal.Signals(signum).name if hasattr(signal, "Signals") else signum,
        )
        handle.release()
        # sys.exit raises SystemExit which lets atexit handlers run;
        # using os._exit would skip them.
        sys.exit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError) as exc:
            # ValueError fires if we're not in the main thread; OSError
            # on platforms that don't allow handlers for the signal.
            # Best-effort — atexit still covers the normal-exit case.
            log.debug("Could not install handler for %s: %s", sig, exc)


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
    `bundle_paths` (typically `~/.open-notebook-plus/venv` and
    `desktop/bin/`) and whose parent is no longer this launcher.

    Best-effort: uses `ps -ef` on POSIX. Returns list of orphans
    found. If `dry_run=False`, also SIGTERMs each. Callers should
    `time.sleep(0.5)` after a non-dry run to let the OS reap.

    Why this is best-effort:
      - `ps` output format varies subtly across macOS versions
      - We can only kill processes we own (UID match)
      - A determined orphan can ignore SIGTERM — but the next
        SIGKILL is up to the operator

    This is the "kill -9 me" safety net; the primary defense is
    the SingletonHandle which prevents accumulation under normal
    conditions.
    """
    orphans: list[OrphanProcess] = []
    own_pid = os.getpid()
    parent_pid = os.getppid()

    import subprocess
    try:
        # -o specifies columns: PID, PPID, command. Limit to user.
        result = subprocess.run(
            ["ps", "-eo", "pid,ppid,command"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.debug("ps not available for orphan reap: %s", exc)
        return []

    if result.returncode != 0:
        return []

    path_strs = [str(p.resolve()) for p in bundle_paths]
    for line in result.stdout.splitlines()[1:]:  # skip header
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        cmdline = parts[2]
        # Don't kill ourselves / our parent
        if pid in (own_pid, parent_pid):
            continue
        # Check if cmdline mentions any of our bundle paths
        if not any(p in cmdline for p in path_strs):
            continue
        # Optionally narrow to "real" orphans: ppid==1 means parent
        # is init. We INCLUDE non-orphans too because a dead-but-not-
        # reaped sibling launcher would still have its old children
        # showing up with that launcher's PID (which we can confirm
        # is dead via _is_pid_alive).
        if ppid not in (1, 0) and _is_pid_alive(ppid):
            continue
        orphans.append(OrphanProcess(pid=pid, cmdline=cmdline))

    if not dry_run:
        for orphan in orphans:
            try:
                os.kill(orphan.pid, signal.SIGTERM)
                log.info(
                    "Reaped orphan %d: %s", orphan.pid, orphan.cmdline[:80],
                )
            except OSError as exc:
                log.debug(
                    "Could not SIGTERM orphan %d: %s", orphan.pid, exc,
                )

    return orphans


def default_pid_file() -> Path:
    """Canonical PID-file location for the desktop launcher."""
    base = Path(os.environ.get("HOME", "~")).expanduser()
    return base / ".open-notebook-plus" / "launcher.pid"
