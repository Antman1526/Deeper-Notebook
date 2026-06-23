"""Smoke tests for the safe upstream sync guard."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "upstream_sync_guard.sh"


def _run_guard(command: str, snapshot_dir: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "UPSTREAM_REMOTE": "definitely-missing-upstream",
        "SNAPSHOT_DIR": str(snapshot_dir),
    }
    return subprocess.run(
        ["bash", str(_SCRIPT), command],
        cwd=_REPO,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_snapshot_does_not_require_upstream_remote(tmp_path):
    snapshot_dir = tmp_path / "snapshot"

    result = _run_guard("snapshot", snapshot_dir)

    assert result.returncode == 0
    assert (snapshot_dir / "README.md").exists()
    assert (snapshot_dir / "status-short.txt").exists()
    assert (snapshot_dir / "tracked-changes.patch").exists()
    assert "Missing remote" not in result.stderr


def test_prepare_writes_snapshot_before_remote_failure(tmp_path):
    snapshot_dir = tmp_path / "snapshot"

    result = _run_guard("prepare", snapshot_dir)

    assert result.returncode != 0
    assert (snapshot_dir / "README.md").exists()
    assert (snapshot_dir / "status-short.txt").exists()
    assert "Missing remote: definitely-missing-upstream" in result.stderr
