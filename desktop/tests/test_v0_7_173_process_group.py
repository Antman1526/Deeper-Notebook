"""v0.7.173 — Spawn launcher children into their own process group
so `stop_all` kills the whole subtree including grandchildren.

Background: prior to v0.7.173, `_spawn` called bare `subprocess.Popen`
and `stop_all` only sent SIGTERM to the immediate child. Next.js
forks per-request workers (`next-server (v16.2.6)`) that reparent to
PID 1 when the parent dies — leaving zombies that accumulated between
launches. The user has personally seen this orphan pattern.

Fix: `start_new_session=True` (POSIX) / `CREATE_NEW_PROCESS_GROUP`
(Windows) at spawn time + `os.killpg(pgid, SIGTERM)` /
`os.kill(pgid, CTRL_BREAK_EVENT)` at shutdown.

These tests pin the AST-level contract — the actual subprocess
behavior is hard to assert without a real Popen, but a future
refactor that drops the kwarg or reverts to a bare terminate()
fails deterministically here.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _read_launcher() -> str:
    return (ROOT / "desktop" / "launcher.py").read_text(encoding="utf-8")


def test_spawn_uses_start_new_session_on_posix():
    """v0.7.173: `_spawn` must pass `start_new_session=True` to
    subprocess.Popen on non-Windows so the child becomes a process
    group leader. Otherwise SIGTERM to the leader doesn't reach
    grandchildren (which is exactly the next-server orphan bug)."""
    src = _read_launcher()
    assert 'popen_kwargs["start_new_session"] = True' in src, (
        "v0.7.173 regression: launcher no longer sets "
        "start_new_session=True. Grandchildren forked by Next.js / "
        "content-core / llama-cpp will reparent to PID 1 and survive "
        "past .app close — the next-server zombies will return."
    )


def test_spawn_uses_create_new_process_group_on_windows():
    """v0.7.173: Windows equivalent — CREATE_NEW_PROCESS_GROUP so
    we can send CTRL_BREAK_EVENT at shutdown."""
    src = _read_launcher()
    assert "CREATE_NEW_PROCESS_GROUP" in src, (
        "v0.7.173 regression: Windows process-group setup missing. "
        "stop_all's CTRL_BREAK_EVENT path requires the child to be "
        "a group leader."
    )


def test_stop_all_uses_killpg_on_posix():
    """v0.7.173: `stop_all` must call os.killpg(pid, SIGTERM) on
    POSIX (not just p.terminate()). killpg with the leader's PID
    takes out the entire process group — grandchildren too — in
    one signal."""
    src = _read_launcher()
    assert "os.killpg(pid, signal.SIGTERM)" in src, (
        "v0.7.173 regression: stop_all reverted to bare p.terminate(). "
        "That only signals the immediate child; grandchildren survive."
    )


def test_stop_all_falls_back_to_terminate_on_killpg_failure():
    """v0.7.173: the killpg path must have a fallback to plain
    p.terminate() so tests with MagicMock(spec=Popen) (no real pgid)
    still work AND so a runtime ProcessLookupError doesn't crash
    the shutdown. The existing v0.7.82 fix relied on terminate
    being callable without per-test mocking; that contract must
    be preserved."""
    src = _read_launcher()
    # The except chain must catch the relevant errors AND fall back
    # to terminate.
    assert "ProcessLookupError" in src
    assert "p.terminate()" in src
    # And the killpg call must be inside a try block (not bare).
    idx = src.index("os.killpg(pid, signal.SIGTERM)")
    region = src[idx - 300 : idx + 300]
    assert "try:" in region


def test_signal_module_imported():
    """v0.7.173: `import signal` must be present (sibling import to
    `os` which we use for `os.killpg`)."""
    src = _read_launcher()
    assert "import signal" in src, (
        "v0.7.173 regression: signal module no longer imported. "
        "killpg + SIGTERM + CTRL_BREAK_EVENT references will NameError "
        "at shutdown."
    )
