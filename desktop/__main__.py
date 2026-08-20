"""Entry point — `python -m desktop` — see desktop/app.py for orchestration.

On first launch (after the wizard), bootstrap.ensure_venv() uses the bundled
uv binary and python-build-standalone interpreter to create
~/.deeper-notebook/venv and install upstream deps (~30-60s). Subsequent
launches skip bootstrapping when requirements.lock hasn't changed.

The supervisor spawns FastAPI/worker/llama-cpp using the venv's Python
interpreter rather than the frozen launcher binary, so no internal dispatcher
tricks are needed.
"""

from __future__ import annotations

import sys

from desktop.data_root import append_recovery_log, open_recovery_log_directory


def _emergency_log(exc: BaseException) -> None:
    """v0.6.33 — capture early-init exceptions before _setup_launcher_log_handler
    has run. Without this, a failure in _new_context() / _phase_load_config /
    _phase_wizard_if_first_run produced a frozen-launcher crash with NOTHING
    visible to the user — no stderr (no terminal), no launcher.log (the
    handler wasn't attached yet), just a dock-bouncing PyWebView app that
    failed to open.

    We write outside both product data roots so a failed or ambiguous root
    resolution cannot recursively trigger itself. Best-effort — if even this
    fails, the process still exits non-zero so the caller knows it failed.
    """
    import datetime as _dt
    import traceback as _traceback

    try:
        payload = (
            f"\n===== EARLY-INIT FAILURE at "
            f"{_dt.datetime.now().isoformat()} =====\n"
            f"{type(exc).__name__}: {exc}\n"
            f"{_traceback.format_exc()}\n"
        ).encode("utf-8", errors="replace")
        with open_recovery_log_directory() as log_directory:
            append_recovery_log(log_directory, "launcher.log", payload)
    except Exception:
        # If we can't even write to the log dir, fall back to stderr.
        try:
            sys.stderr.write(f"Launcher early-init failure: {exc!r}\n")
        except Exception:
            pass  # nothing more we can do


if __name__ == "__main__":
    try:
        from desktop.app import run

        rc = run()
    except BaseException as exc:  # noqa: BLE001 — catch SystemExit too
        # SystemExit and KeyboardInterrupt are intentional exits; pass them
        # through without logging as a crash.
        if isinstance(exc, (SystemExit, KeyboardInterrupt)):
            raise
        _emergency_log(exc)
        sys.exit(1)
    sys.exit(rc)
