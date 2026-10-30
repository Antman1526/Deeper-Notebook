"""v0.8.130 — restarting a model service must not crash on Windows.

`restart_sidecar` stopped the old process with os.getpgid/os.killpg, which do not
exist on Windows: the call raised AttributeError, which the surrounding
`except (OSError, ProcessLookupError)` did not catch, so the restart crashed
instead of stopping the service. stop_all() already had a Windows branch
(taskkill); the restart path now uses the same thing.
"""

import signal
import subprocess
import types

import pytest

from desktop import launcher


def _proc(pid=4321):
    return types.SimpleNamespace(pid=pid)


def test_windows_stops_the_tree_with_taskkill(monkeypatch):
    calls = []
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    monkeypatch.delattr(launcher.os, "getpgid", raising=False)
    monkeypatch.delattr(launcher.os, "killpg", raising=False)
    monkeypatch.setattr(
        subprocess, "run",
        lambda args, **kw: calls.append(args) or types.SimpleNamespace(returncode=0),
    )

    launcher._signal_sidecar_tree(_proc(), signal.SIGTERM)
    assert calls == [["taskkill", "/T", "/PID", "4321"]]

    calls.clear()
    launcher._signal_sidecar_tree(_proc(), getattr(signal, "SIGKILL", 9))
    assert calls == [["taskkill", "/F", "/T", "/PID", "4321"]]


def test_windows_reports_a_process_it_could_not_signal_the_way_the_caller_expects(monkeypatch):
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: types.SimpleNamespace(returncode=128))
    with pytest.raises(OSError):  # the restart path falls back to terminate() on OSError
        launcher._signal_sidecar_tree(_proc(), signal.SIGTERM)

    def missing(*_a, **_k):
        raise FileNotFoundError("taskkill")

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(OSError):
        launcher._signal_sidecar_tree(_proc(), signal.SIGTERM)


def test_posix_still_signals_the_process_group(monkeypatch):
    seen = []
    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    monkeypatch.setattr(launcher.os, "getpgid", lambda pid: pid + 1)
    monkeypatch.setattr(launcher.os, "killpg", lambda pgid, sig: seen.append((pgid, sig)))
    launcher._signal_sidecar_tree(_proc(100), signal.SIGTERM)
    assert seen == [(101, signal.SIGTERM)]


def test_the_restart_path_uses_it_for_both_the_polite_and_the_firm_signal():
    source = open(launcher.__file__, encoding="utf-8").read()
    restart = source[source.index("def restart_sidecar") :]
    restart = restart[: restart.index("\n    def ", 10)]
    assert restart.count("_signal_sidecar_tree(") == 2
    # Calls, not the word in a comment.
    assert "getpgid(" not in restart and "killpg(" not in restart
