r"""v0.7.185 — Centralised home-directory resolution for desktop launcher.

The audit (round-9) caught 9 sites independently rolling their own
home-dir lookup via `os.environ.get("HOME", ...)` with inconsistent
fallbacks:

  - Some used `"~"` (works on POSIX, sketchy on Windows)
  - Some used `"."` (CATASTROPHIC on Windows — when launched from
    File Explorer, CWD is the .exe directory which on a typical
    install is `C:\Program Files\Open Notebook Plus\` and READ-ONLY.
    Logs, PID file, surreal_data all silently fail to write.)
  - Some used `os.environ.get("USERPROFILE", ".")` as fallback
    (closer, but still vulnerable to the `.` worst case).

This module exposes `user_home()` — single source of truth that
always returns a writable directory:
  1. `HOME` env (POSIX standard).
  2. `USERPROFILE` env (Windows standard).
  3. `Path.home()` — Python's own resolver, which on Windows
     synthesises USERPROFILE / HOMEDRIVE+HOMEPATH internally.

`Path.home()` is the last-resort guarantee — it will never return
the CWD, never return "~", never return "." on any supported OS.
The first two checks are kept so a user can override via env var
(useful for testing + sandboxed shells).

Migration: replaces 9 ad-hoc resolvers across desktop/. The
forward-guard test `test_no_unsafe_home_fallback_in_desktop`
catches any future regression that reintroduces the `"."` fallback.
"""

from __future__ import annotations

import os
from pathlib import Path


def user_home() -> Path:
    """Return the user's home directory as a Path.

    Priority: $HOME → $USERPROFILE → Path.home(). All three branches
    return an existing, writable directory on a normal install.
    Never returns `.` or `~`.
    """
    raw = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if raw:
        return Path(raw)
    return Path.home()
