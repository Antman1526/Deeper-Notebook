"""Safety tests for the canonical feature-build worktree boundary wrapper."""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WRAPPER = ROOT / "frontend" / "scripts" / "run-feature-build-contract.mjs"


def test_wrapper_never_renames_callers_node_modules_symlink():
    source = WRAPPER.read_text(encoding="utf-8")
    assert "renameSync(nodeModules" not in source
    assert "processIsAlive" in source
    assert "isSafeStagePath" in source


def _wait_for(path: Path, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {path}")


def test_wrapper_recovers_crashed_stage_without_mutating_shared_symlink(tmp_path: Path):
    frontend = tmp_path / "frontend"
    scripts = frontend / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "run-feature-build-contract.mjs").write_bytes(WRAPPER.read_bytes())
    (scripts / "verify-feature-env-build.mjs").write_text(
        "process.exit(0)\n", encoding="utf-8"
    )

    shared = tmp_path / "shared-node-modules"
    next_bin = shared / ".bin" / "next"
    next_bin.parent.mkdir(parents=True)
    next_bin.write_text(
        "#!/bin/sh\n"
        "if [ \"${NEXT_SLEEP:-0}\" != 0 ]; then sleep \"$NEXT_SLEEP\"; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    next_bin.chmod(0o755)
    node_modules = frontend / "node_modules"
    node_modules.symlink_to(shared, target_is_directory=True)

    temp_dir = tmp_path / "tmp"
    temp_dir.mkdir()
    lock = temp_dir / (
        "deeper-notebook-feature-build-"
        + hashlib.sha256(frontend.as_posix().encode()).hexdigest()[:24]
        + ".lock"
    )
    env = {
        **os.environ,
        "TMPDIR": str(temp_dir),
        "RSYNC_BIN": "/usr/bin/rsync",
        "NEXT_SLEEP": "30",
    }
    crashed = subprocess.Popen(
        ["node", str(scripts / "run-feature-build-contract.mjs")],
        cwd=frontend,
        env=env,
        start_new_session=True,
    )
    try:
        _wait_for(lock)
        stage = next(temp_dir.glob("deeper-notebook-feature-contract-*"))
        os.killpg(crashed.pid, signal.SIGKILL)
        assert crashed.wait(timeout=5) == -signal.SIGKILL
        assert node_modules.is_symlink()
        assert node_modules.resolve() == shared.resolve()
        assert stage.exists()

        env["NEXT_SLEEP"] = "0"
        completed = subprocess.run(
            ["node", str(scripts / "run-feature-build-contract.mjs")],
            cwd=frontend,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert node_modules.is_symlink()
        assert node_modules.resolve() == shared.resolve()
        assert not lock.exists()
        assert list(temp_dir.glob("deeper-notebook-feature-contract-*")) == []
    finally:
        if crashed.poll() is None:
            os.killpg(crashed.pid, signal.SIGKILL)
            crashed.wait(timeout=5)
