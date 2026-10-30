"""v0.8.130 — stop the app's services when the launcher dies without cleaning up.

Every service the supervisor starts is its own session (so a quit can stop each
whole group). The price is that nothing stops them if the launcher is killed or
crashes: no signal reaches another session, the launcher's own cleanup never
runs, and SurrealDB, the API, the worker, the web server and the model servers
keep running and holding their ports. The only remedy was a sweep at the next
launch, which matches by command line and sends one polite signal. Seen in a
packaged run on 2026-10-05: the launcher vanished without a log line and seven
services were still up an hour later.

The guard is a second process. The launcher keeps the write end of a pipe and
the guard reads the other end; the launcher writes the pid of each service it
starts. When the launcher goes, for any reason, the kernel closes its end and
the guard's read returns end-of-file. The guard then stops what was registered:
politely, then firmly.

It always sweeps at end-of-file, a clean quit included. After a clean quit the
services are already gone and the sweep finds nothing; not trusting a "goodbye"
message means a launcher that exits without stopping its children is covered too.

Process numbers are reused, so each one is recorded with the process's start
time, and a number that now belongs to a different process is left alone.

A second net: the launcher also writes what it starts to a small record file,
headed by its own identity. The next launch stops whatever a launcher that is no
longer running left recorded there. That covers the guard itself being absent.
A record whose launcher is still running belongs to another copy of the app and
is never read for stopping, nor overwritten.

Windows uses the same protocol with Windows tools (PowerShell for a process's
start time, `taskkill /T` to stop a tree). That branch is exercised by tests with
stand-ins only; it has not been run on a real Windows machine. If a start time
cannot be read, nothing is ever stopped.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

FLAG = "--orphan-guard"
DEFAULT_GRACE_SECONDS = 8.0

# ---- launcher side -----------------------------------------------------------

_lock = threading.Lock()
_write_end: int | None = None
_record_path: Path | None = None


def command_for(log_path: Path, grace: float) -> list[str]:
    arguments = [FLAG, str(log_path), str(grace)]
    if getattr(sys, "frozen", False):
        # The packaged app: its own binary is the only interpreter there is
        # before the Python environment has been provisioned.
        return [sys.executable, *arguments]
    return [sys.executable, "-m", "desktop", *arguments]


def _detached() -> dict:
    """Popen arguments that keep the guard out of the launcher's group."""
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
        return {"creationflags": flags}
    return {"start_new_session": True}


def start(
    log_path: Path,
    grace: float = DEFAULT_GRACE_SECONDS,
    record_path: Path | None = None,
) -> bool:
    """Start the guard. Never raises: a launch must not fail for want of it."""
    global _write_end, _record_path
    with _lock:
        if _write_end is not None:
            return True
        _record_path = _claim_record(record_path)
        read_end = write_end = None
        try:
            read_end, write_end = os.pipe()
            subprocess.Popen(
                command_for(log_path, grace),
                stdin=read_end,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                # Out of the launcher's group, so stopping a service group, or
                # the launcher's own, never takes the guard with it. The write
                # end is not inherited (close_fds), or end-of-file would never come.
                close_fds=True,
                **_detached(),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("orphan guard not started: %s", exc)
            for end in (read_end, write_end):
                if end is not None:
                    try:
                        os.close(end)
                    except OSError:
                        pass
            return False
        os.close(read_end)
        _write_end = write_end
        return True


def register(pid: object) -> None:
    """Tell the guard about a service. A no-op when no guard is running."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return
    with _lock:
        if _write_end is None:
            return
        try:
            os.write(_write_end, f"pid {pid}\n".encode("ascii"))
        except OSError as exc:
            log.debug("orphan guard did not take pid %s: %s", pid, exc)
        if _record_path is not None:
            try:
                with _record_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        f"pid\t{pid}\t{1 if _is_leader(pid) else 0}\t{process_token(pid) or ''}\n"
                    )
            except OSError as exc:
                log.debug("orphan record did not take pid %s: %s", pid, exc)


def finish() -> None:
    """Close the pipe. The guard sweeps (and finds nothing after a clean stop)."""
    global _write_end, _record_path
    with _lock:
        end, _write_end = _write_end, None
        _record_path = None
    if end is not None:
        try:
            os.close(end)
        except OSError:
            pass


# ---- guard side ----------------------------------------------------------------


@dataclass(frozen=True)
class Entry:
    token: str | None  # the process's start time when it was registered
    leader: bool  # it leads its own process group, as supervised services do


def process_token(pid: int) -> str | None:
    """The start time of a running process, or None if there is no such process."""
    if sys.platform == "win32":
        command = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"(Get-Process -Id {int(pid)} -ErrorAction Stop).StartTime.ToFileTimeUtc()",
        ]
    else:
        command = ["ps", "-o", "lstart=", "-p", str(pid)]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=10, check=False
        )
    except Exception:  # noqa: BLE001
        return None
    if result.returncode != 0:
        return None
    token = (result.stdout or "").strip()
    return token or None


def _is_leader(pid: int) -> bool:
    if sys.platform == "win32":
        return True  # `taskkill /T` stops the tree whatever the process is
    try:
        return os.getpgid(pid) == pid
    except OSError:
        return False


def _signal_windows(pid: int, entry: Entry, signum: int) -> bool:
    # No start time, no certainty about whose process this is: hands off.
    now = process_token(pid)
    if now is None or entry.token is None or now != entry.token:
        return False
    if signum == 0:
        return True
    forced = signum != signal.SIGTERM
    try:
        result = subprocess.run(
            ["taskkill", *(["/F"] if forced else []), "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return False
    return result.returncode == 0


def _signal(pid: int, entry: Entry, signum: int) -> bool:
    """Signal a registered service. False when there was nothing of ours to signal."""
    if sys.platform == "win32":
        return _signal_windows(pid, entry, signum)
    now = process_token(pid)
    if now is not None and now != entry.token:
        return False  # the number belongs to another process now
    try:
        if entry.leader:
            # Reaches what the service started too. With the leader gone the
            # group can still hold its children; with nobody left this raises.
            os.killpg(pid, signum)
        elif now is not None:
            os.kill(pid, signum)
        else:
            return False
    except (ProcessLookupError, PermissionError):
        return False
    return True


def sweep(
    entries: dict[int, Entry], grace: float, log: Callable[[str], None]
) -> int:
    """Stop every registered service still running. Returns how many were found."""
    found = [pid for pid, entry in entries.items() if _signal(pid, entry, signal.SIGTERM)]
    if not found:
        return 0
    log(f"launcher gone; stopping {len(found)} service(s): {sorted(found)}")
    deadline = time.monotonic() + max(grace, 0.0)
    remaining = list(found)
    while remaining and time.monotonic() < deadline:
        time.sleep(0.2)
        remaining = [pid for pid in remaining if _signal(pid, entries[pid], 0)]
    for pid in remaining:
        if _signal(pid, entries[pid], signal.SIGKILL):
            log(f"service {pid} ignored the request to stop; killed")
    return len(found)


# ---- the record: a second net at the next launch -------------------------------


def _read_record(path: Path) -> tuple[tuple[int, str] | None, dict[int, Entry]]:
    launcher: tuple[int, str] | None = None
    entries: dict[int, Entry] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, {}
    for line in text.splitlines()[:1024]:
        parts = line.split("\t")
        try:
            if parts[0] == "launcher" and len(parts) >= 3:
                launcher = (int(parts[1]), parts[2])
            elif parts[0] == "pid" and len(parts) >= 4 and parts[3]:
                entries[int(parts[1])] = Entry(token=parts[3], leader=parts[2] == "1")
        except ValueError:
            continue
    return launcher, entries


def _launcher_running(launcher: tuple[int, str] | None) -> bool:
    if launcher is None:
        return False
    pid, token = launcher
    return bool(token) and process_token(pid) == token


def _claim_record(path: Path | None) -> Path | None:
    """Start this launcher's record, unless another running launcher owns the file."""
    if path is None:
        return None
    try:
        launcher, _ = _read_record(path)
        if _launcher_running(launcher) and launcher[0] != os.getpid():
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"launcher\t{os.getpid()}\t{process_token(os.getpid()) or ''}\n",
            encoding="utf-8",
        )
        return path
    except OSError as exc:
        log.debug("orphan record not started: %s", exc)
        return None


def sweep_recorded(path: Path, grace: float, log: Callable[[str], None]) -> int:
    """Stop what a launcher that is no longer running left recorded.

    Returns how many services were found. A record whose launcher is still
    running is another copy of the app: it is left exactly as it is.
    """
    launcher, entries = _read_record(path)
    if launcher is None and not entries:
        return 0
    if _launcher_running(launcher):
        return 0
    found = sweep(entries, grace, log) if entries else 0
    try:
        path.unlink()
    except OSError:
        pass
    return found


def parse_args(argv: list[str]) -> tuple[Path, float] | None:
    if len(argv) != 3 or argv[0] != FLAG:
        return None
    try:
        grace = float(argv[2])
    except ValueError:
        return None
    if not 0 <= grace <= 600:
        return None
    return Path(argv[1]), grace


def main(argv: list[str]) -> int:
    parsed = parse_args(argv)
    if parsed is None:
        return 2
    log_path, grace = parsed

    def write_log(line: str) -> None:
        try:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
        except OSError:
            pass

    # The launcher being told to quit must not take the guard with it.
    for name in ("SIGTERM", "SIGINT", "SIGHUP", "SIGBREAK"):
        signum = getattr(signal, name, None)
        if signum is None:
            continue
        try:
            signal.signal(signum, signal.SIG_IGN)
        except (ValueError, OSError):
            pass

    entries: dict[int, Entry] = {}
    with os.fdopen(0, "rb", buffering=0) as pipe:
        pending = b""
        while True:
            try:
                chunk = pipe.read(4096)
            except OSError:
                break
            if not chunk:
                break  # end-of-file: the launcher is gone
            pending += chunk
            *lines, pending = pending.split(b"\n")
            for line in lines:
                parts = line.decode("ascii", "replace").split()
                if len(parts) == 2 and parts[0] == "pid" and parts[1].isdigit():
                    pid = int(parts[1])
                    entries[pid] = Entry(token=process_token(pid), leader=_is_leader(pid))

    sweep(entries, grace, write_log)
    return 0
