from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "repair_desktop_db.sh"
pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX repair script")


def _run(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the repair script against a throwaway HOME.

    v0.8.114 — `pgrep` is stubbed to report nothing running. The script aborts
    early if Deeper Notebook or SurrealDB is live, so before this stub these
    tests passed or failed depending on whether the developer happened to have
    the app OPEN — `test_explicit_exact_target_resolves_both_roots_conflict`
    failed on a machine running the app and passed everywhere else. These tests
    are about how the script resolves its data root, and none of them asserts
    the running-process guard, so removing that dependency costs no coverage.

    The stub lives OUTSIDE `home` deliberately: one of these tests snapshots the
    whole HOME tree to prove the script mutates nothing, and a stub directory
    planted inside it would register as a mutation.
    """
    with tempfile.TemporaryDirectory(prefix="repair-script-stub-") as stub_root:
        stub_bin = Path(stub_root)
        pgrep = stub_bin / "pgrep"
        pgrep.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        pgrep.chmod(0o755)
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            env={"HOME": str(home), "PATH": f"{stub_bin}:/usr/bin:/bin"},
            capture_output=True,
            text=True,
            check=False,
        )


def test_both_data_roots_refuse_without_explicit_target_and_do_not_mutate(
    tmp_path,
):
    canonical = tmp_path / ".deeper-notebook"
    legacy = tmp_path / ".open-notebook-plus"
    canonical.mkdir()
    legacy.mkdir()
    (canonical / "canonical.marker").write_text("canonical", encoding="utf-8")
    (legacy / "legacy.marker").write_text("legacy", encoding="utf-8")
    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))

    result = _run(tmp_path)

    after = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    assert result.returncode != 0
    assert "both" in result.stderr.lower()
    assert "--data-home" in result.stderr
    assert after == before


def test_explicit_target_must_be_exact_canonical_or_legacy_root(tmp_path):
    canonical = tmp_path / ".deeper-notebook"
    legacy = tmp_path / ".open-notebook-plus"
    other = tmp_path / "other"
    canonical.mkdir()
    legacy.mkdir()
    other.mkdir()

    result = _run(tmp_path, "--data-home", str(other))

    assert result.returncode != 0
    assert "exactly" in result.stderr.lower()
    assert str(canonical) in result.stderr
    assert str(legacy) in result.stderr


def test_explicit_exact_target_resolves_both_roots_conflict(tmp_path):
    canonical = tmp_path / ".deeper-notebook"
    legacy = tmp_path / ".open-notebook-plus"
    canonical.mkdir()
    legacy.mkdir()

    result = _run(tmp_path, "--data-home", str(legacy))

    assert result.returncode != 0
    assert "both" not in result.stderr.lower()
    assert f"No surreal_data at {legacy}/surreal_data" in result.stderr
