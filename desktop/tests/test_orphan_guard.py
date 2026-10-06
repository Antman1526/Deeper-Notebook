"""v0.8.130 — the app's services do not outlive a launcher that dies.

Every service the launcher starts is its own session, so a launcher that is
killed or crashes (no chance to run its cleanup) used to leave SurrealDB, the
API, the worker, the web server and the model servers running and holding their
ports until the next launch swept some of them. Seen in a packaged run on
2026-10-05. The orphan guard is a small process that holds the read end of a
pipe from the launcher and stops the registered services when that pipe closes,
which happens however the launcher goes.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from desktop import orphan_guard

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

REPOSITORY = Path(__file__).resolve().parents[2]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _gone(pid: int, within: float = 15.0) -> bool:
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        try:
            if os.waitpid(pid, os.WNOHANG)[0] == pid:
                return True
        except ChildProcessError:
            if not _alive(pid):
                return True
        time.sleep(0.1)
    return False


def _service(code: str = "import time; time.sleep(120)") -> subprocess.Popen:
    """A stand-in for a launcher child: its own session, as the supervisor starts them."""
    return subprocess.Popen([sys.executable, "-c", code], start_new_session=True)


def _guard(log: Path, grace: str = "2") -> tuple[subprocess.Popen, int]:
    read_end, write_end = os.pipe()
    process = subprocess.Popen(
        [sys.executable, "-m", "desktop", orphan_guard.FLAG, str(log), grace],
        stdin=read_end,
        cwd=REPOSITORY,
        start_new_session=True,
    )
    os.close(read_end)
    return process, write_end


def test_services_are_stopped_when_the_launcher_vanishes(tmp_path):
    log = tmp_path / "orphan-guard.log"
    service = _service()
    guard, pipe = _guard(log)
    try:
        os.write(pipe, f"pid {service.pid}\n".encode())
        time.sleep(1.0)
        assert _alive(service.pid), "nothing is touched while the launcher lives"
        os.close(pipe)  # what the kernel does when the launcher dies, however it dies
        assert _gone(service.pid)
        assert guard.wait(timeout=20) == 0
        assert str(service.pid) in log.read_text()
    finally:
        if service.poll() is None:
            service.kill()


def test_a_service_that_ignores_the_polite_signal_is_killed(tmp_path):
    stubborn = _service(
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)"
    )
    guard, pipe = _guard(tmp_path / "guard.log", grace="1")
    try:
        time.sleep(0.8)  # let it install its handler
        os.write(pipe, f"pid {stubborn.pid}\n".encode())
        time.sleep(0.5)
        os.close(pipe)
        assert _gone(stubborn.pid)
        assert guard.wait(timeout=20) == 0
    finally:
        if stubborn.poll() is None:
            stubborn.kill()


def test_the_whole_group_goes_including_what_a_service_started(tmp_path):
    pid_file = tmp_path / "grandchild.pid"
    parent = _service(
        "import subprocess, sys, time;"
        "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']);"
        f"open({str(pid_file)!r}, 'w').write(str(g.pid)); time.sleep(120)"
    )
    guard, pipe = _guard(tmp_path / "guard.log")
    try:
        deadline = time.monotonic() + 15
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        grandchild = int(pid_file.read_text())
        os.write(pipe, f"pid {parent.pid}\n".encode())
        time.sleep(0.5)
        os.close(pipe)
        assert _gone(parent.pid)
        assert _gone(grandchild)
        guard.wait(timeout=20)
    finally:
        if parent.poll() is None:
            parent.kill()


def test_a_process_that_merely_reuses_a_recorded_number_is_left_alone():
    bystander = _service()
    try:
        # Recorded with another process's identity: the number matches, the process does not.
        entries = {bystander.pid: orphan_guard.Entry(token="Mon Jan  1 00:00:00 2001", leader=True)}
        assert orphan_guard.sweep(entries, grace=1.0, log=lambda _line: None) == 0
        assert _alive(bystander.pid)
    finally:
        bystander.kill()
        bystander.wait()


def test_a_running_process_has_a_stable_identity_and_a_dead_one_has_none():
    assert orphan_guard.process_token(os.getpid())
    assert orphan_guard.process_token(os.getpid()) == orphan_guard.process_token(os.getpid())
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    assert orphan_guard.process_token(finished.pid) is None


def test_the_launcher_side_is_inert_until_started_and_never_raises(monkeypatch, tmp_path):
    orphan_guard.register(12345)  # not started: nothing happens
    orphan_guard.finish()

    def refuse(*_args, **_kwargs):
        raise OSError("cannot start")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    assert orphan_guard.start(tmp_path / "guard.log") is False
    orphan_guard.register(12345)


def test_started_from_the_launcher_it_stops_what_was_registered(tmp_path):
    service = _service()
    try:
        assert orphan_guard.start(tmp_path / "guard.log", grace=2.0) is True
        orphan_guard.register(service.pid)
        time.sleep(1.0)
        assert _alive(service.pid)
        orphan_guard.finish()  # the pipe closes, as it would if this process died
        assert _gone(service.pid)
    finally:
        orphan_guard.finish()
        if service.poll() is None:
            service.kill()


def test_packaged_app_relaunches_its_own_binary(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Apps/Deeper Notebook")
    assert orphan_guard.command_for(Path("/logs/g.log"), 8.0)[:2] == ["/Apps/Deeper Notebook", orphan_guard.FLAG]


def test_every_supervised_service_and_the_mlx_server_are_registered():
    desktop = Path(orphan_guard.__file__).parent
    launcher = (desktop / "launcher.py").read_text(encoding="utf-8")
    spawned = launcher.index("self._procs.append(proc)")
    assert "orphan_guard" in launcher[spawned : spawned + 400]
    assert "orphan_guard" in (desktop / "providers" / "mlx.py").read_text(encoding="utf-8")
    app = (desktop / "app.py").read_text(encoding="utf-8")
    assert app.index("_phase_start_orphan_guard(ctx)") < app.index("    _phase_start_supervisor(ctx)\n")
    entry = (desktop / "__main__.py").read_text(encoding="utf-8")
    assert entry.index("orphan_guard") < entry.index("from desktop.app import run")


# ---- a second net at the next launch -----------------------------------------
# The guard covers a launcher that dies. This covers the guard itself not being
# there (it could not start, or it was killed too): the launcher writes down what
# it starts, and the next launch stops whatever a dead launcher left recorded.


def _dead_pid() -> int:
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    return finished.pid


def test_the_next_launch_stops_what_a_dead_launcher_left_recorded(tmp_path):
    record = tmp_path / "launcher-children.tsv"
    service = _service()
    try:
        token = orphan_guard.process_token(service.pid)
        record.write_text(
            f"launcher\t{_dead_pid()}\tMon Jan  1 00:00:00 2001\n"
            f"pid\t{service.pid}\t1\t{token}\n",
            encoding="utf-8",
        )
        lines = []
        assert orphan_guard.sweep_recorded(record, grace=2.0, log=lines.append) == 1
        assert _gone(service.pid)
        assert not record.exists(), "a swept record is not swept twice"
        assert any(str(service.pid) in line for line in lines)
    finally:
        if service.poll() is None:
            service.kill()


def test_a_record_belonging_to_a_launcher_that_is_still_running_is_never_touched(tmp_path):
    record = tmp_path / "launcher-children.tsv"
    service = _service()
    try:
        me = orphan_guard.process_token(os.getpid())
        record.write_text(
            f"launcher\t{os.getpid()}\t{me}\npid\t{service.pid}\t1\t{orphan_guard.process_token(service.pid)}\n",
            encoding="utf-8",
        )
        assert orphan_guard.sweep_recorded(record, grace=1.0, log=lambda _l: None) == 0
        assert _alive(service.pid), "another running copy of the app keeps its services"
        assert record.exists()
    finally:
        service.kill()
        service.wait()


def test_a_missing_or_damaged_record_is_ignored(tmp_path):
    assert orphan_guard.sweep_recorded(tmp_path / "absent.tsv", grace=1.0, log=lambda _l: None) == 0
    damaged = tmp_path / "damaged.tsv"
    damaged.write_text("pid\tnot-a-number\t1\tx\n\x00garbage\n", encoding="utf-8")
    assert orphan_guard.sweep_recorded(damaged, grace=1.0, log=lambda _l: None) == 0


def test_the_launcher_records_what_it_registers(tmp_path):
    record = tmp_path / "launcher-children.tsv"
    service = _service()
    try:
        assert orphan_guard.start(tmp_path / "guard.log", grace=2.0, record_path=record) is True
        orphan_guard.register(service.pid)
        lines = record.read_text(encoding="utf-8").splitlines()
        assert lines[0].split("\t")[:2] == ["launcher", str(os.getpid())]
        assert lines[1].split("\t")[:3] == ["pid", str(service.pid), "1"]
        orphan_guard.finish()
        assert _gone(service.pid)
    finally:
        orphan_guard.finish()
        if service.poll() is None:
            service.kill()


def test_starting_never_overwrites_a_running_launchers_record(tmp_path, monkeypatch):
    record = tmp_path / "launcher-children.tsv"
    other = _service()  # stands in for another running copy of the app
    ours = _service()
    try:
        original = f"launcher\t{other.pid}\t{orphan_guard.process_token(other.pid)}\npid\t999999\t1\tx\n"
        record.write_text(original, encoding="utf-8")
        assert orphan_guard.start(tmp_path / "guard.log", grace=1.0, record_path=record) is True
        # Never register this test process itself: the guard would stop the test run.
        orphan_guard.register(ours.pid)  # goes to the guard, not to the other launcher's file
        assert record.read_text(encoding="utf-8") == original
    finally:
        orphan_guard.finish()
        other.kill()
        other.wait()
        if ours.poll() is None:
            ours.kill()
        ours.wait()


# ---- Windows: the same protocol with Windows tools (exercised with stand-ins) --


def test_windows_identity_and_stop_use_windows_tools(monkeypatch):
    calls = []

    def fake_run(args, **_kwargs):
        calls.append(list(args))
        if args[0] == "powershell":
            return subprocess.CompletedProcess(args, 0, stdout="133712345678901234\r\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(orphan_guard.sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert orphan_guard.process_token(4321) == "133712345678901234"
    entry = orphan_guard.Entry(token="133712345678901234", leader=True)
    assert orphan_guard._signal(4321, entry, signal.SIGTERM) is True
    assert calls[-1] == ["taskkill", "/T", "/PID", "4321"]
    assert orphan_guard._signal(4321, entry, getattr(signal, "SIGKILL", 9)) is True
    assert calls[-1] == ["taskkill", "/F", "/T", "/PID", "4321"]

    # A different process behind the same number, or no way to tell: hands off.
    assert orphan_guard._signal(4321, orphan_guard.Entry(token="1", leader=True), signal.SIGTERM) is False
    monkeypatch.setattr(subprocess, "run", lambda args, **k: subprocess.CompletedProcess(args, 1, stdout="", stderr=""))
    assert orphan_guard.process_token(4321) is None
    assert orphan_guard._signal(4321, entry, signal.SIGTERM) is False
