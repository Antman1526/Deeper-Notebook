"""v0.7.141 — bundle-bootstrap fix tests.

The real bug a user hit: bundled `Open Notebook Plus.app` silently
quit 3 minutes after launch because the bundled requirements.lock
was stale (didn't contain prometheus_client, added in v0.7.124).
The bootstrap correctly hashed the stale lock + reused the stale
venv, so the lockfile-freshness check was pointing at the wrong
thing.

Three-part fix this file tests:
  1. Makefile gained a `build-mac-lock` target that regenerates
     desktop/requirements.lock from pyproject.toml before bundling.
  2. `build-mac-lock` is a precondition of `build-mac`.
  3. bootstrap.py runs post-install import verification of every
     critical package and fails loudly with the recovery command
     if any is missing.

These tests pin all three so the same class of bug can't ship again.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_MAKEFILE = Path("Makefile")
_PYPROJECT = Path("pyproject.toml")
_LOCKFILE = Path("desktop/requirements.lock")


# ---------------------------------------------------------------------- #
# Part 1 — Makefile gained `build-mac-lock`
# ---------------------------------------------------------------------- #


def test_build_mac_lock_target_exists():
    src = _MAKEFILE.read_text()
    assert "build-mac-lock:" in src, (
        "Makefile should define `build-mac-lock` target — "
        "the regeneration step that was missing pre-v0.7.141"
    )


def test_build_mac_lock_invokes_uv_pip_compile():
    """The target must regenerate the lock, not just touch it."""
    src = _MAKEFILE.read_text()
    # Extract the build-mac-lock recipe body
    match = re.search(
        r"^build-mac-lock:\s*\n((?:[\t ].*\n)+)",
        src,
        re.MULTILINE,
    )
    assert match, "Couldn't locate build-mac-lock recipe body"
    recipe = match.group(1)
    assert "uv pip compile" in recipe, (
        "build-mac-lock should regenerate the lockfile via "
        "`uv pip compile`"
    )
    assert "pyproject.toml" in recipe, (
        "build-mac-lock should read deps from pyproject.toml"
    )
    assert "desktop/requirements.lock" in recipe, (
        "build-mac-lock should write to desktop/requirements.lock"
    )


def test_runtime_lock_recipe_is_universal_across_packaged_platforms() -> None:
    src = _MAKEFILE.read_text()
    match = re.search(
        r"^build-mac-lock:\s*\n((?:[\t ].*\n)+)",
        src,
        re.MULTILINE,
    )
    assert match
    assert "--universal" in match.group(1)

    lock = _LOCKFILE.read_text()
    marker = "platform_machine == 'arm64' and sys_platform == 'darwin'"
    # v0.8.84 — assert the platform marker, not an exact version: the pin
    # moved 0.26.4 → 0.31.x (qwen3_5 support) and this test's subject is the
    # lock staying universal with mlx deps gated to Apple Silicon, exactly as
    # the mlx / mlx-metal assertions below already express it.
    assert re.search(rf"^mlx-lm==[^\n]+ ; {re.escape(marker)}$", lock, re.MULTILINE)
    assert re.search(rf"^mlx==[^\n]+ ; {re.escape(marker)}$", lock, re.MULTILINE)
    assert re.search(
        rf"^mlx-metal==[^\n]+ ; {re.escape(marker)}$",
        lock,
        re.MULTILINE,
    )


# ---------------------------------------------------------------------- #
# Part 2 — `build-mac-lock` is a precondition of `build-mac`
# ---------------------------------------------------------------------- #


def test_build_mac_lock_runs_before_venv():
    """Without this dependency, the bundled venv installs against the
    stale on-disk lockfile, defeating the whole point of the
    regeneration target."""
    src = _MAKEFILE.read_text()
    # Find the build-mac:  line — should be the rule's prerequisite list
    match = re.search(r"^build-mac:\s*(.+)$", src, re.MULTILINE)
    assert match, "build-mac target should declare its dependencies"
    deps = match.group(1).split()
    assert "build-mac-lock" in deps, (
        f"build-mac should depend on build-mac-lock; deps were: {deps}"
    )
    # And it should come BEFORE build-mac-venv (otherwise the venv
    # installs against the stale lock).
    lock_idx = deps.index("build-mac-lock")
    venv_idx = deps.index("build-mac-venv")
    assert lock_idx < venv_idx, (
        f"build-mac-lock (idx {lock_idx}) must run BEFORE build-mac-venv "
        f"(idx {venv_idx}); current order: {deps}"
    )


# ---------------------------------------------------------------------- #
# Part 3 — bootstrap.py defensive depcheck
# ---------------------------------------------------------------------- #


class TestBootstrapDepcheck:
    """v0.7.141 — bootstrap.ensure_venv now runs each critical import
    in the freshly-installed venv and raises with a clear recovery
    command if any failed."""

    def test_verify_critical_imports_passes_when_all_present(self):
        from desktop.bootstrap import _verify_critical_imports

        # Use the system Python for these test imports — it definitely
        # has sys, os, json available.
        result = _verify_critical_imports(
            Path(sys.executable),
            ["sys", "os", "json"],
        )
        assert result == [], (
            f"All builtin modules should import cleanly; got failures: {result}"
        )

    def test_verify_critical_imports_returns_missing_modules(self):
        from desktop.bootstrap import _verify_critical_imports

        result = _verify_critical_imports(
            Path(sys.executable),
            ["sys", "this_module_does_not_exist_xyz_v0_7_141"],
        )
        assert "this_module_does_not_exist_xyz_v0_7_141" in result
        assert "sys" not in result

    def test_verify_critical_imports_handles_subprocess_timeout(self):
        from desktop.bootstrap import _verify_critical_imports

        # We can't easily force a timeout inside a unit test, but we
        # CAN confirm the function returns even with a totally bogus
        # python_exe path — it catches all exceptions per-module.
        result = _verify_critical_imports(
            Path("/nonexistent/python/binary"),
            ["sys"],
        )
        # Should report sys as failed (since we can't even execute the
        # nonexistent binary), not crash the whole function.
        assert len(result) == 1

    def test_critical_imports_list_includes_prometheus_client(self):
        """Regression test: the v0.7.124 prometheus_client dep was
        the exact module missing from the user's stale venv. It MUST
        be in the critical imports list so a future stale-lockfile
        scenario fails loudly at bootstrap instead of silently 3
        minutes later when the API tries to import."""
        src = Path("desktop/bootstrap.py").read_text()
        # The list lives inside ensure_venv as `_CRITICAL_IMPORTS`.
        assert '"prometheus_client"' in src, (
            "prometheus_client (added v0.7.124) must be in the "
            "ensure_venv critical-imports list — that was the exact "
            "dep missing from the user's stale venv when this fix "
            "was written"
        )

    def test_critical_imports_list_includes_load_bearing_packages(self):
        """Every package that api.main imports at module-load time
        needs to be in the critical list. Otherwise a future bundle
        could ship missing one of them and we'd be back to the
        '3-minute silent quit' bug."""
        src = Path("desktop/bootstrap.py").read_text()
        for required in (
            "prometheus_client",
            "surrealdb",
            "fastapi",
            "langgraph",
            "loguru",
            "pydantic",
        ):
            assert f'"{required}"' in src, (
                f"bootstrap critical-imports list missing {required!r}; "
                "this module is imported at api.main load time and its "
                "absence would crash startup with a silent ModuleNotFoundError"
            )


# ---------------------------------------------------------------------- #
# Cross-cutting: lockfile actually matches pyproject.toml (post-fix)
# ---------------------------------------------------------------------- #


def test_lockfile_includes_all_pyproject_direct_deps():
    """v0.7.141 — once `build-mac-lock` runs, the bundle's lockfile
    contains every package listed as a direct dep in pyproject.toml.
    This test is the after-the-fact check: if the lock is missing a
    direct dep, the regen step didn't run.

    Why this test exists: pre-v0.7.141 the lockfile was hand-maintained
    and drifted from pyproject.toml between commits. With the
    Makefile-side fix in place, a stale lock means someone built
    the bundle bypassing `make build-mac` — which the test catches
    at CI before that bundle ships.
    """
    if not _LOCKFILE.exists():
        pytest.skip("lockfile not present (clean checkout)")

    pyproject_text = _PYPROJECT.read_text()
    lock_text = _LOCKFILE.read_text()

    # Extract direct deps from pyproject.toml dependencies = [...] array.
    # Format: "pkg-name>=X.Y.Z" or "pkg-name[extra]>=X.Y"
    match = re.search(
        r"^dependencies\s*=\s*\[\s*\n(.*?)\n\]",
        pyproject_text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        pytest.skip("Couldn't extract dependencies block from pyproject.toml")
    deps_block = match.group(1)

    # Each dep line is `    "pkg-name>=version",` possibly with [extras].
    direct_deps = []
    for line in deps_block.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        dep_match = re.match(r'"([a-zA-Z0-9_-]+)', line)
        if dep_match:
            direct_deps.append(dep_match.group(1).lower())

    assert direct_deps, "Found zero direct deps — parser broken"

    # Normalize lockfile package names too (uv writes with both _ and -)
    lock_packages = set()
    for line in lock_text.split("\n"):
        # uv pip compile output: `package==X.Y.Z` lines
        m = re.match(r"^([a-zA-Z0-9_-]+)==", line.strip())
        if m:
            lock_packages.add(m.group(1).lower().replace("_", "-"))

    missing = []
    for dep in direct_deps:
        normalized = dep.lower().replace("_", "-")
        if normalized not in lock_packages:
            missing.append(dep)

    assert not missing, (
        f"desktop/requirements.lock is missing direct deps from "
        f"pyproject.toml: {missing}.\n\n"
        f"This means the lockfile is STALE — regenerate with:\n"
        f"    make build-mac-lock\n"
        f"or rebuild the whole bundle:\n"
        f"    make build-mac"
    )
