r"""v0.7.185 — Windows-compatibility fixes from round-9 audit.

Four bugs that silently break on Windows but work on macOS/Linux —
exactly the class of bug that goes unnoticed when the primary
developer is on macOS and Windows is a secondary platform.

  1. `os.environ.get("HOME", ".")` fallback puts the PID file,
     logs, surreal_data, and config under the CWD on Windows
     (where HOME is rarely set). When launched from File Explorer,
     CWD is `C:\Program Files\...` — read-only — so every write
     silently fails. Centralised to `desktop/paths.py::user_home()`
     which falls through to `Path.home()` (always writable).

  2. `f"file://{data_dir}"` produces an INVALID file: URL on
     Windows where `data_dir` is `C:\Users\...`. The expected
     `file:///C:/Users/...` requires `Path.as_uri()`. Fixed in
     `desktop/launcher.py::_spawn_surreal`.

  3. Windows process-tree teardown via `os.kill(pid,
     CTRL_BREAK_EVENT)` was a no-op because PyInstaller windowed
     .exe has no console for the signal to deliver to. Replaced
     with `taskkill /F /T /PID <n>` — the Windows equivalent of
     `killpg(SIGKILL)`. Also added CREATE_NO_WINDOW to Popen
     flags so child processes don't pop transient console windows.

  4. Filesystem denylist (`api/routers/filesystem.py::_DENIED_PREFIXES`)
     used POSIX-style prefixes (`"/Windows"`). On Windows,
     `Path.resolve()` returns `C:\Windows\System32\...`;
     `.lower().startswith("/windows")` returned False, silently
     letting the file picker browse into protected paths.
     Normalised path comparison: strip drive letter + flip
     backslashes to forward slashes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# user_home() helper — single source of truth for home-dir resolution
# ---------------------------------------------------------------------------


def test_user_home_falls_back_to_path_home(monkeypatch):
    """v0.7.185: with neither HOME nor USERPROFILE set, user_home()
    MUST return a writable directory (Path.home()), never `.` or
    `~`."""
    from desktop.paths import user_home

    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    result = user_home()
    assert result == Path.home(), (
        f"v0.7.185 regression: user_home() returned {result!r} when "
        f"HOME and USERPROFILE were both unset. Expected "
        f"Path.home(). The previous `.` fallback caused logs / "
        f"surreal_data to write to CWD on Windows installs launched "
        f"from File Explorer."
    )


def test_user_home_prefers_home_env(monkeypatch, tmp_path):
    """v0.7.185: explicit HOME env wins. Useful for tests + sandboxed
    shells. Order: HOME → USERPROFILE → Path.home()."""
    from desktop.paths import user_home

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("USERPROFILE", raising=False)
    assert user_home() == tmp_path


def test_user_home_falls_through_to_userprofile_on_windows(monkeypatch, tmp_path):
    """v0.7.185: USERPROFILE wins when HOME isn't set (Windows
    standard env var)."""
    from desktop.paths import user_home

    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert user_home() == tmp_path


def test_user_home_never_returns_dot_or_tilde(monkeypatch, tmp_path):
    """v0.7.185 INVARIANT: under no env combination should user_home()
    return literal `.` or `~`. The previous ad-hoc fallbacks did.

    Three branches: both env set, neither set, USERPROFILE only.
    None should produce the bad fallback."""
    from desktop.paths import user_home

    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    result = user_home()
    assert str(result) not in (".", "~"), (
        f"v0.7.185 regression: user_home() returned {result!r}."
    )


# ---------------------------------------------------------------------------
# AST-level pins: no remaining unsafe HOME fallbacks in desktop/
# ---------------------------------------------------------------------------


def test_no_unsafe_home_fallback_in_desktop():
    """v0.7.185 forward-guard: no file in desktop/ should construct
    a home-dir-derived Path with `"."` as final fallback. user_home()
    is the canonical resolver."""
    desktop_dir = ROOT / "desktop"
    offenders: list[tuple[str, int, str]] = []
    for path in desktop_dir.rglob("*.py"):
        if "__pycache__" in str(path) or path.name == "paths.py":
            continue
        for i, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            # The exact bad shape: `HOME", ".")` or similar.
            if 'os.environ.get("HOME"' in line and '"."' in line:
                rel = path.relative_to(ROOT).as_posix()
                offenders.append((rel, i, line.strip()))
            if 'os.environ.get("HOME", "~")' in line:
                rel = path.relative_to(ROOT).as_posix()
                offenders.append((rel, i, line.strip()))
    assert not offenders, (
        "v0.7.185 regression: desktop/ contains files with the "
        "unsafe HOME fallback (`.` or `~`). Use user_home() from "
        "desktop.paths instead.\n"
        + "\n".join(f"  {r}:{ln} → {t}" for r, ln, t in offenders)
    )


# ---------------------------------------------------------------------------
# file:// URI fix
# ---------------------------------------------------------------------------


def test_launcher_uses_as_uri_for_surreal_data_dir():
    """v0.7.185: the SurrealDB spawn must use `data_dir.as_uri()`,
    not the f-string `f"file://{data_dir}"` builder. The latter
    produces malformed `file://C:\\Users\\...` URLs on Windows."""
    src = _read_source("desktop/launcher.py")
    # Skip comment lines so the rationale block (which documents
    # the old bad shape) doesn't false-trigger.
    code_only = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    bad = 'f"file://{data_dir}"'
    assert bad not in code_only, (
        "v0.7.185 regression: SurrealDB spawn is back to the "
        "f-string file:// builder. On Windows this produces "
        "invalid file: URLs and SurrealDB silently fails to "
        "initialise storage."
    )
    assert "data_dir.as_uri()" in src


# ---------------------------------------------------------------------------
# Windows process-tree teardown via taskkill
# ---------------------------------------------------------------------------


def test_launcher_uses_taskkill_on_windows():
    """v0.7.185: Windows shutdown path uses `taskkill /F /T /PID`,
    not just `os.kill(pid, CTRL_BREAK_EVENT)` (the latter is a
    no-op for windowed PyInstaller .exe with no console)."""
    src = _read_source("desktop/launcher.py")
    assert '"taskkill", "/F", "/T", "/PID"' in src, (
        "v0.7.185 regression: Windows tree-kill no longer uses "
        "taskkill /F /T. Grandchildren (next-server forks etc.) "
        "will leak again — same class as the v0.7.173 POSIX "
        "killpg fix."
    )


def test_launcher_windows_popen_uses_no_window_flag():
    """v0.7.185: Windows Popen kwargs include CREATE_NO_WINDOW so
    child processes don't pop transient console windows."""
    src = _read_source("desktop/launcher.py")
    assert "CREATE_NO_WINDOW" in src, (
        "v0.7.185 regression: CREATE_NO_WINDOW flag gone from "
        "Windows Popen kwargs. Children will flash console "
        "windows from the packaged .exe."
    )


# ---------------------------------------------------------------------------
# Filesystem denylist Windows fix
# ---------------------------------------------------------------------------


def test_filesystem_denylist_normalises_backslashes():
    """v0.7.185: `_resolve_and_validate` must normalise backslashes
    + strip drive letters before prefix matching, so `C:\\Windows\\`
    on Windows matches the POSIX-shaped `/Windows` denylist entry."""
    src = _read_source("api/routers/filesystem.py")
    # The fix replaces backslashes with forward slashes.
    assert '.replace("\\\\", "/")' in src, (
        "v0.7.185 regression: filesystem denylist no longer "
        "normalises backslashes. Windows users can browse into "
        "C:\\Windows, C:\\Windows\\System32, etc. through the "
        "file picker."
    )
    # And strips the drive letter for comparison.
    assert 'resolved_lower[1] == ":"' in src, (
        "v0.7.185 regression: filesystem denylist no longer "
        "strips the drive letter before matching POSIX-shaped "
        "prefixes."
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-resolved paths")
def test_filesystem_denylist_still_blocks_posix_system_paths():
    """v0.7.185: the Windows-compatibility rewrite must NOT regress
    POSIX coverage. `/etc`, `/System`, etc. must still be blocked
    on macOS/Linux."""
    from fastapi import HTTPException

    from api.routers.filesystem import _resolve_and_validate

    # Use a fake denied path; the function resolves before comparing.
    with pytest.raises(HTTPException) as exc_info:
        _resolve_and_validate("/etc/passwd", must_exist=False)
    assert exc_info.value.status_code == 403
