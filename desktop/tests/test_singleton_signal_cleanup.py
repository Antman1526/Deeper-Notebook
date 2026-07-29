from __future__ import annotations

import os
import signal
import threading
from pathlib import Path

from desktop import singleton


def test_signal_handler_cleans_runtime_before_unconditional_exit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    handlers: dict[int, object] = {}
    cleanup_calls: list[int] = []
    exit_codes: list[int] = []
    pid_file = tmp_path / "launcher.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    handle = singleton.SingletonHandle(pid_file=pid_file)

    monkeypatch.setattr(
        singleton.signal,
        "signal",
        lambda requested_signal, handler: handlers.__setitem__(
            requested_signal, handler
        ),
    )
    monkeypatch.setattr(singleton.os, "_exit", exit_codes.append)

    registration = singleton._install_signal_handlers(
        handle,
        on_signal_cleanup=lambda signum: cleanup_calls.append(signum),
    )
    try:
        handler = handlers[signal.SIGTERM]
        handler(signal.SIGTERM, None)
    finally:
        registration.close()

    assert cleanup_calls == [signal.SIGTERM]
    assert not pid_file.exists()
    assert exit_codes == [128 + signal.SIGTERM]


def test_wakeup_fd_dispatches_cleanup_without_python_handler_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cleanup_finished = threading.Event()
    shutdown_finished = threading.Event()
    exit_codes: list[int] = []
    pid_file = tmp_path / "launcher.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    handle = singleton.SingletonHandle(pid_file=pid_file)

    def record_exit(code: int) -> None:
        exit_codes.append(code)
        shutdown_finished.set()

    monkeypatch.setattr(singleton.os, "_exit", record_exit)

    registration = singleton._install_signal_handlers(
        handle,
        on_signal_cleanup=lambda _signum: cleanup_finished.set(),
    )
    try:
        assert registration.wakeup_write_fd is not None
        os.write(
            registration.wakeup_write_fd,
            bytes([signal.SIGTERM]),
        )
        assert cleanup_finished.wait(timeout=1)
        assert shutdown_finished.wait(timeout=1)
    finally:
        registration.close()

    assert not pid_file.exists()
    assert exit_codes == [128 + signal.SIGTERM]
