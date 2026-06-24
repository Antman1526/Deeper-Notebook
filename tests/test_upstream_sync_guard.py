"""Smoke tests for the safe upstream sync guard."""
from __future__ import annotations

import os
import shutil
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


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _init_sync_fixture(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    upstream = tmp_path / "upstream.git"
    repo.mkdir()
    _git(repo, "init", "-b", "desktop-app")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _write(repo, "README.md", "base\n")
    _write(repo, "api/routers/studio.py", "base\n")
    _write(repo, "frontend/src/lib/api/sources.ts", "base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    _git(repo, "clone", "--bare", str(repo), str(upstream))
    _git(repo, "remote", "add", "upstream", str(upstream))
    _git(repo, "checkout", "-b", "upstream-main")
    _write(repo, "api/routers/studio.py", "upstream\n")
    _write(repo, "frontend/src/lib/api/sources.ts", "upstream\n")
    _git(repo, "commit", "-am", "upstream protected changes")
    _git(repo, "push", "upstream", "upstream-main:main")
    _git(repo, "checkout", "desktop-app")
    return repo, upstream


def _run_guard_in_repo(
    repo: Path,
    command: str,
    *,
    snapshot_dir: Path,
    worktree_dir: Path,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "UPSTREAM_REMOTE": "upstream",
        "UPSTREAM_BRANCH": "main",
        "BASE_BRANCH": "desktop-app",
        "SYNC_BRANCH": "integrate/test-upstream",
        "SNAPSHOT_DIR": str(snapshot_dir),
        "WORKTREE_DIR": str(worktree_dir),
    }
    return subprocess.run(
        ["bash", str(_SCRIPT), command],
        cwd=repo,
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


def test_prepare_writes_merge_report_and_protected_path_changes(tmp_path):
    repo, _upstream = _init_sync_fixture(tmp_path)
    snapshot_dir = tmp_path / "snapshot"
    worktree_dir = tmp_path / "integration"

    result = _run_guard_in_repo(
        repo,
        "prepare",
        snapshot_dir=snapshot_dir,
        worktree_dir=worktree_dir,
    )

    assert result.returncode == 0, result.stderr
    assert (snapshot_dir / "merge-status.txt").exists()
    assert (snapshot_dir / "changed-files.txt").read_text(encoding="utf-8")
    protected_changes = (
        snapshot_dir / "protected-plus-path-changes.txt"
    ).read_text(encoding="utf-8")
    assert "api/routers/studio.py" in protected_changes
    assert "frontend/src/lib/api/sources.ts" in protected_changes
    assert (snapshot_dir / "conflicted-files.txt").read_text(encoding="utf-8") == ""

    # The integration worktree is outside the temp repo; remove it explicitly
    # so Windows-style locked worktree metadata never bleeds into later tests.
    if worktree_dir.exists():
        shutil.rmtree(worktree_dir)
    _git(repo, "worktree", "prune")
