"""v0.7.205 — Critical: `PORT` env var must NOT be in the shared
session_env that every spawned child inherits.

Background: when the user launched the .app fresh, the window
showed `{"detail":"Not Found"}` instead of the Next.js UI. Root
cause: the launcher allocated dynamic ports (e.g., api_port=60432,
frontend_port=60433, embed_port=60434), then set `PORT=60433` in
`session_env` for the Next.js child. But every other child also
inherited that env. uvicorn — used by `llama_cpp.server` — reads
`PORT` from env via pydantic_settings and treats it as
AUTHORITATIVE, overriding the `--port 60434` CLI arg.

End result: the embed server (PID 69622) was spawned with
`--port 60434` but actually bound `127.0.0.1:60433`, the same
port Next.js (`*:60433`) also bound. macOS routes 127.0.0.1
connections to the more-specific listener — so the webview
opened `http://127.0.0.1:60433/` (correct URL) and got served
by the embed server's FastAPI root handler, returning
`{"detail":"Not Found"}` instead of the Next.js UI.

Fix:
  1. Remove `PORT` from `session_env`.
  2. Add an `extra_env` parameter to `_spawn()` so callers can
     pass per-child env overrides.
  3. `_spawn_next` passes `extra_env={"PORT": str(port)}` so
     only the Next.js child sees `PORT`.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_session_env_does_not_contain_port_key():
    """v0.7.205 — `PORT` must NOT be set as a key in
    `self.session_env` (which every spawn inherits). Verified by
    pinning the v0.7.205 marker that documents the removal."""
    src = _src("desktop/launcher.py")
    assert '"PORT": str(frontend_port),  # Next.js convention' not in src, (
        "v0.7.205 regression: `PORT` is back in the shared "
        "session_env. uvicorn-based children (llama_cpp.server etc.) "
        "will override their --port CLI arg with this value and "
        "collide with the Next.js port."
    )
    # The v0.7.205 rationale comment must remain so a future "this
    # comment block is huge, let's prune it" PR doesn't remove the
    # explanation along with the markers.
    assert "v0.7.205 — DO NOT put `PORT` in the shared session_env" in src


def test_spawn_supports_per_child_env_override():
    """v0.7.205 — `_spawn` must accept an `extra_env` kwarg and
    merge it on top of `session_env` so callers can pass
    per-child env overrides without leaking them to siblings."""
    src = _src("desktop/launcher.py")
    assert "extra_env: dict[str, str] | None = None" in src
    # And the merge logic.
    assert "if extra_env:" in src
    assert "child_env = dict(self.session_env)" in src
    assert "child_env.update(extra_env)" in src
    # The popen_kwargs must use the merged env, not the raw
    # session_env.
    assert '"env": child_env,' in src
    assert '"env": self.session_env,' not in src


def test_spawn_next_passes_port_via_extra_env():
    """v0.7.205 — `_spawn_next` must pass `PORT` via `extra_env`
    so the Next.js child sees it but no other child does."""
    src = _src("desktop/launcher.py")
    assert 'extra_env={"PORT": str(port)},' in src, (
        "v0.7.205 regression: _spawn_next no longer passes PORT "
        "via per-child extra_env. Next.js will not honour the "
        "dynamic port."
    )
