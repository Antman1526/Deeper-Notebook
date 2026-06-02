"""v0.7.183 — desktop/tests conftest.

Four shim tests (test_memory_shim, test_piper_shim,
test_openchronicle_shim, test_whisper_shim) need `desktop/` on
sys.path so they can import `desktop_shims.X`. They do their own
`sys.path.insert(...)` at module load; this conftest is the central
place that documents the requirement.

Cross-suite pollution background — RESOLVED in v0.7.183:

  Previously, `desktop/` insertion would shadow the root `scripts/`
  package whenever pytest ran the combined `tests/ desktop/tests/`
  suite. `<repo>/desktop/scripts/` got resolved as the `scripts`
  package, so `from scripts.benchmark_models import ...` in
  `tests/test_v0_7_139.py` failed with ModuleNotFoundError. 17
  tests blew up.

  v0.7.183 fixed it by renaming `desktop/scripts/` →
  `desktop/dl_scripts/`. There's no namespace collision to fix
  with sys.path tricks — the fix is at the source.
"""
import pytest


@pytest.fixture(autouse=True)
def _disable_db_autorepair(monkeypatch):
    """v0.8.67l — Tests drive Supervisor.start_all() with mocked subprocesses
    and the REAL user_home(). The boot-time DB auto-repair + worker watcher
    would otherwise touch the real ~/.open-notebook-plus (read worker.log, set
    the repair flag, spawn a temp surreal). Disable both during tests; their
    own logic is covered by test_db_repair.py."""
    monkeypatch.setenv("ONP_DISABLE_DB_AUTOREPAIR", "1")
    # v0.8.67l — _available_ram_bytes() shells out to `vm_stat`, and
    # subprocess.run uses subprocess.Popen internally. Tests that mock
    # subprocess.Popen with a finite iterator (e.g. stop_all child accounting)
    # would have that probe consume a mock proc. Stub it to None (the pressure
    # backoff then no-ops); the backoff math is covered directly in
    # test_launcher_adaptive_nctx.py. Individual tests may still override it.
    monkeypatch.setattr(
        "desktop.launcher.Supervisor._available_ram_bytes",
        staticmethod(lambda: None),
        raising=False,
    )
