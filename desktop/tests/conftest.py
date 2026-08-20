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

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_data_root_home(tmp_path, monkeypatch):
    """Keep every desktop test's resolver inside its own temporary home."""
    test_home = tmp_path
    monkeypatch.setenv("HOME", str(test_home))
    monkeypatch.setenv("USERPROFILE", str(test_home))

    from desktop import data_root

    original_resolve = data_root.resolve_data_root
    allowed_root = tmp_path.resolve()

    def guarded_resolve(*, home=None, failure_injector=None):
        candidate = (
            Path(home) if home is not None else Path(os.environ["HOME"])
        ).resolve()
        assert candidate.is_relative_to(allowed_root), (
            f"test attempted data-root resolution outside {allowed_root}: {candidate}"
        )
        return original_resolve(home=home, failure_injector=failure_injector)

    monkeypatch.setattr(data_root, "resolve_data_root", guarded_resolve)


@pytest.fixture(autouse=True)
def _disable_db_autorepair(monkeypatch):
    """v0.8.67l — Tests drive Supervisor.start_all() with mocked subprocesses
    and the REAL user_home(). The boot-time DB auto-repair + worker watcher
    would otherwise touch the real ~/.open-notebook-plus (read worker.log, set
    the repair flag, spawn a temp surreal). Disable both during tests; their
    own logic is covered by test_db_repair.py."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_DISABLE_DB_AUTOREPAIR", "1")
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


def pytest_collection_modifyitems(config, items):
    """Keep POSIX/macOS-only descriptor and bundle tests off Windows."""
    import sys

    if sys.platform != "win32":
        return
    mac_app_suite = "desktop/tests/test_app_migration.py::"
    posix_descriptor_tests = {
        (
            "desktop/tests/test_data_root_conflict_recovery.py::"
            "test_conflict_evidence_dirfd_refuses_visible_root_swap_without_redirect"
        ),
        (
            "desktop/tests/test_emergency_log.py::"
            "test_emergency_log_dirfd_cannot_be_redirected_after_open"
        ),
        (
            "desktop/tests/test_data_root_conflict_recovery.py::"
            "test_divergent_roots_enter_read_only_recovery_before_normal_startup"
        ),
    }
    marker = pytest.mark.skip(reason="POSIX descriptor or macOS bundle contract")
    for item in items:
        normalized = item.nodeid.replace("\\", "/")
        if normalized.startswith(mac_app_suite) or normalized in posix_descriptor_tests:
            item.add_marker(marker)
