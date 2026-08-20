"""v0.7.195 — Local-server shim deps must be in the bundled venv.

End-to-end test of the freshly-built v0.7.194 .app revealed that
3 of the 5 local servers never started:

  - whisper (STT) — `desktop_shims.whisper_shim` import-failed on
    `from faster_whisper import WhisperModel` (ModuleNotFoundError).
  - piper (TTS) — `desktop_shims.piper_shim` import-failed on
    `from piper.voice import PiperVoice` (ModuleNotFoundError).
  - memory — `desktop_shims.memory_shim` import-failed on
    `from mem0 import Memory` (ModuleNotFoundError).

All three shims have been in the codebase since the v0.4 local-
server feature shipped, but none of their runtime dependencies
(`faster-whisper`, `piper-tts`, `mem0ai`) were ever pinned in
`desktop/requirements.txt`. Every .app install since v0.4 has
silently shipped non-functional STT/TTS/memory servers — the spawn
looked successful (no log entries surfaced the failure because
launcher.py:689/700 returns early before logging when the shim
module crashes at import) and `auto_register` happily registered
credentials pointing at ports nothing was listening on.

End-user symptom: in the Settings → Models page, the Whisper,
Piper, and Memory credentials' "Test connection" buttons returned
"Cannot connect to server."

Fix: pin all three shim deps in `desktop/requirements.txt` and
regenerate `desktop/requirements.lock`. Same class of fix as v0.7.192's
`llama-cpp-python[server]` extras.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Requirements pins
# ---------------------------------------------------------------------------


def test_desktop_requirements_includes_shim_deps():
    """v0.7.195: `faster-whisper`, `piper-tts`, `mem0ai` must be
    explicitly pinned in `desktop/requirements.txt`. Without them,
    the bundled venv ships shims that crash at import — Whisper,
    Piper, and Memory servers never start."""
    src = _read_source("desktop/requirements.txt")
    for dep in ("faster-whisper>=", "piper-tts>=", "mem0ai>="):
        assert dep in src, (
            f"v0.7.195 regression: {dep} pin missing from "
            f"desktop/requirements.txt. The corresponding shim will "
            f"crash at import on every launch and the local server "
            f"will silently never start."
        )


def test_desktop_lockfile_includes_shim_deps():
    """v0.7.195 forward-guard: `make build-mac-lock` must have been
    re-run after editing requirements.txt. Otherwise the venv
    install at first launch installs the LOCKED set (which doesn't
    include our additions), and we're back to the original bug."""
    lock = _read_source("desktop/requirements.lock")
    for dep in ("faster-whisper==", "piper-tts==", "mem0ai=="):
        assert dep in lock, (
            f"v0.7.195 regression: {dep} missing from "
            f"desktop/requirements.lock. Did you forget `make "
            f"build-mac-lock` after editing requirements.txt?"
        )


# ---------------------------------------------------------------------------
# Shim sources still import what we pinned
# ---------------------------------------------------------------------------


def test_whisper_shim_still_imports_faster_whisper():
    """v0.7.195 forward-guard: if a future refactor swaps the
    underlying STT library, this test fails so the requirements.txt
    pin gets updated in lockstep."""
    src = _read_source("desktop/desktop_shims/whisper_shim.py")
    assert "from faster_whisper import" in src, (
        "v0.7.195: whisper shim no longer imports faster_whisper — "
        "did the underlying STT library change? Update the "
        "requirements.txt pin to match."
    )


def test_piper_shim_still_imports_piper():
    """v0.7.195 forward-guard for piper-tts."""
    src = _read_source("desktop/desktop_shims/piper_shim.py")
    assert "from piper" in src, (
        "v0.7.195: piper shim no longer imports the piper package — "
        "update requirements.txt if the underlying TTS library "
        "changed."
    )


def test_memory_shim_still_imports_mem0():
    """v0.7.195 forward-guard for mem0ai."""
    src = _read_source("desktop/desktop_shims/memory_shim.py")
    assert "mem0" in src, (
        "v0.7.195: memory shim no longer references mem0 — update "
        "requirements.txt if the underlying memory library changed."
    )
