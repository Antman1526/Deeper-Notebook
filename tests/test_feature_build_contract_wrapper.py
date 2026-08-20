"""Safety tests for the canonical feature-build worktree boundary wrapper."""

from __future__ import annotations

import hashlib
import json
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


def _wait_for_group_gone(pgid: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe = subprocess.run(
            ["ps", "-axo", "pid=,pgid=,stat="],
            check=False,
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            raise AssertionError(f"process-group probe failed: {probe.stderr}")
        members = []
        for line in probe.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 3 and fields[1].isdigit() and int(fields[1]) == pgid:
                members.append(fields)
        if not members:
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for process group {pgid}")


def _wait_for_owner(lock: Path) -> None:
    _wait_for(lock)
    _wait_for(lock / "owner.json")


def _stage_from_lock(lock: Path) -> Path:
    stage = Path(json.loads((lock / "owner.json").read_text(encoding="utf-8"))["stage"])
    _wait_for(stage)
    return stage


def _owner_from_lock(lock: Path) -> dict:
    return json.loads((lock / "owner.json").read_text(encoding="utf-8"))


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
        'if [ "${NEXT_SLEEP:-0}" != 0 ]; then sleep "$NEXT_SLEEP"; fi\n'
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
    helper_group = None
    try:
        _wait_for_owner(lock)
        stage = _stage_from_lock(lock)
        helper_group = _owner_from_lock(lock)["pgid"]
        os.killpg(crashed.pid, signal.SIGKILL)
        assert crashed.wait(timeout=5) == -signal.SIGKILL
        assert node_modules.is_symlink()
        assert node_modules.resolve() == shared.resolve()
        assert stage.exists()

        blocked = subprocess.run(
            ["node", str(scripts / "run-feature-build-contract.mjs")],
            cwd=frontend,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert blocked.returncode != 0
        assert stage.exists()
        os.killpg(helper_group, signal.SIGKILL)
        _wait_for_group_gone(helper_group)
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
        if helper_group is not None:
            try:
                os.killpg(helper_group, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_wrapper_recovers_stale_group_lock_with_no_live_child(tmp_path: Path):
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
    next_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
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
    stale_stage = temp_dir / f"deeper-notebook-feature-contract-{'0' * 32}"
    stale_stage.mkdir()
    lock.mkdir()
    (lock / "owner.json").write_text(
        json.dumps(
            {
                "version": 4,
                "pid": 4_000_000,
                "pgid": 4_000_000,
                "nonce": "0" * 32,
                "startToken": "Thu Jan 01 00:00:00 1970",
                "argvHash": "0" * 64,
                "stage": str(stale_stage),
                "state": "running",
            }
        ),
        encoding="utf-8",
    )
    env = {**os.environ, "TMPDIR": str(temp_dir), "RSYNC_BIN": "/usr/bin/rsync"}
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
    assert not stale_stage.exists()
    assert list(temp_dir.glob("deeper-notebook-feature-contract-*")) == []


def test_wrapper_malformed_lock_fails_closed_without_deleting_stage(tmp_path: Path):
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
    next_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
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
    stage = temp_dir / "deeper-notebook-feature-contract-malformed"
    stage.mkdir()
    lock.mkdir()
    (lock / "owner.json").write_text("{malformed", encoding="utf-8")
    completed = subprocess.run(
        ["node", str(scripts / "run-feature-build-contract.mjs")],
        cwd=frontend,
        env={**os.environ, "TMPDIR": str(temp_dir), "RSYNC_BIN": "/usr/bin/rsync"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert (lock / "owner.json").read_text(encoding="utf-8") == "{malformed"
    assert stage.exists()
    assert node_modules.is_symlink()


def test_wrapper_parent_sigkill_does_not_delete_stage_with_surviving_build_child(
    tmp_path: Path,
):
    """A dead wrapper is not enough evidence that its build descendants are gone."""
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
    child_pid_file = tmp_path / "child.pid"
    next_bin.write_text(
        "#!/bin/sh\n"
        f"echo $$ > {child_pid_file}\n"
        'if [ "${NEXT_SLEEP:-30}" != 0 ]; then sleep "${NEXT_SLEEP:-30}"; fi\n'
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
    }
    crashed = subprocess.Popen(
        ["node", str(scripts / "run-feature-build-contract.mjs")],
        cwd=frontend,
        env=env,
        start_new_session=True,
    )
    child_pid = None
    try:
        _wait_for_owner(lock)
        stage = _stage_from_lock(lock)
        _wait_for(child_pid_file)
        child_pid = int(child_pid_file.read_text(encoding="utf-8").strip())
        os.kill(crashed.pid, signal.SIGKILL)
        assert crashed.wait(timeout=5) == -signal.SIGKILL
        assert node_modules.is_symlink()
        assert stage.exists()
        os.kill(child_pid, 0)

        blocked = subprocess.run(
            ["node", str(scripts / "run-feature-build-contract.mjs")],
            cwd=frontend,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert blocked.returncode != 0
        assert stage.exists()
        # The owned child is a process group; terminate the exact recorded
        # group before allowing stale-stage recovery, never a broad pattern.
        recorded_group = _owner_from_lock(lock)["pgid"]
        assert recorded_group > 1
        os.killpg(recorded_group, signal.SIGKILL)
        _wait_for_group_gone(recorded_group)

        env["NEXT_SLEEP"] = "0"
        recovered = subprocess.run(
            ["node", str(scripts / "run-feature-build-contract.mjs")],
            cwd=frontend,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert recovered.returncode == 0, recovered.stderr
        assert node_modules.is_symlink()
        assert node_modules.resolve() == shared.resolve()
        assert not lock.exists()
        assert list(temp_dir.glob("deeper-notebook-feature-contract-*")) == []
    finally:
        if crashed.poll() is None:
            os.kill(crashed.pid, signal.SIGKILL)
            crashed.wait(timeout=5)
        if child_pid is not None:
            try:
                if lock.exists():
                    recorded_group = _owner_from_lock(lock)["pgid"]
                    os.killpg(recorded_group, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_wrapper_drains_lingering_descendant_before_releasing_stage(tmp_path: Path):
    """A successful direct child must not leave a descendant in the helper group."""
    next_script = (
        "#!/bin/sh\n"
        'sleep "${DESCENDANT_SLEEP:-30}" &\n'
        'echo "$!" > "$DESCENDANT_PID_FILE"\n'
        "exit 0\n"
    )
    frontend, shared, node_modules, temp_dir, lock, env = _fixture(
        tmp_path, next_script
    )
    descendant_pid_file = tmp_path / "descendant.pid"
    env["DESCENDANT_PID_FILE"] = str(descendant_pid_file)
    env["DESCENDANT_SLEEP"] = "30"
    completed = subprocess.run(
        ["node", str(frontend / "scripts/run-feature-build-contract.mjs")],
        cwd=frontend,
        env=env,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    descendant_pid = None
    try:
        assert completed.returncode == 0
        _wait_for(descendant_pid_file)
        descendant_pid = int(descendant_pid_file.read_text(encoding="utf-8"))
        assert descendant_pid > 1
        assert node_modules.is_symlink()
        assert node_modules.resolve() == shared.resolve()
        assert not lock.exists()
        assert list(temp_dir.glob("deeper-notebook-feature-contract-*")) == []
        with subprocess.Popen(
            ["kill", "-0", str(descendant_pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ) as probe:
            assert probe.wait(timeout=2) != 0
    finally:
        if descendant_pid is not None:
            try:
                os.kill(descendant_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _fixture(tmp_path: Path, next_script: str = "#!/bin/sh\nexit 0\n"):
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
    next_bin.write_text(next_script, encoding="utf-8")
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
    }
    return frontend, shared, node_modules, temp_dir, lock, env


def _write_owner_lock(lock: Path, owner: dict) -> None:
    lock.mkdir()
    (lock / "owner.json").write_text(json.dumps(owner), encoding="utf-8")


def _stale_owner(stage: Path, *, pid: int = 4_000_000, pgid: int = 4_000_000) -> dict:
    return {
        "version": 4,
        "pid": pid,
        "pgid": pgid,
        "nonce": "0" * 32,
        "startToken": "Thu Jan 01 00:00:00 1970",
        "argvHash": "0" * 64,
        "stage": str(stage),
        "state": "running",
    }


def test_simultaneous_stale_recoverers_have_one_owner_and_preserve_successor(
    tmp_path: Path,
):
    _, shared, node_modules, temp_dir, lock, env = _fixture(
        tmp_path,
        '#!/bin/sh\nsleep "${NEXT_SLEEP:-0}"\nexit 0\n',
    )
    env["NEXT_SLEEP"] = "1"
    stale_stage = temp_dir / f"deeper-notebook-feature-contract-{'0' * 32}"
    stale_stage.mkdir()
    (stale_stage / "stale-marker").write_text("stale", encoding="utf-8")
    _write_owner_lock(lock, _stale_owner(stale_stage))

    contenders = [
        subprocess.Popen(
            ["node", str(tmp_path / "frontend/scripts/run-feature-build-contract.mjs")],
            cwd=tmp_path / "frontend",
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    try:
        deadline = time.monotonic() + 5
        owner = None
        while time.monotonic() < deadline:
            try:
                candidate = _owner_from_lock(lock)
            except (FileNotFoundError, json.JSONDecodeError):
                time.sleep(0.005)
                continue
            if candidate["nonce"] != "0" * 32:
                owner = candidate
                break
            time.sleep(0.005)
        if owner is None:
            raise AssertionError("stale lock was not replaced by an atomic owner")
        assert owner["nonce"] != "0" * 32
        # One contender must refuse while the exact successor owner is live.
        deadline = time.monotonic() + 5
        while not any(process.poll() is not None for process in contenders):
            if time.monotonic() >= deadline:
                raise AssertionError("no stale-recovery contender refused")
            time.sleep(0.01)
        assert lock.exists()
        results = [process.wait(timeout=5) for process in contenders]
        assert sum(result == 0 for result in results) == 1
        assert sum(result != 0 for result in results) == 1
        assert not lock.exists()
        assert not stale_stage.exists()
        assert list(temp_dir.glob("deeper-notebook-feature-contract-*")) == []
        assert node_modules.is_symlink()
        assert node_modules.resolve() == shared.resolve()
    finally:
        for process in contenders:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def test_reader_never_observes_empty_or_partial_owner_metadata(tmp_path: Path):
    _, _, node_modules, _, lock, env = _fixture(
        tmp_path,
        "#!/bin/sh\nsleep 0.75\nexit 0\n",
    )
    process = subprocess.Popen(
        ["node", str(tmp_path / "frontend/scripts/run-feature-build-contract.mjs")],
        cwd=tmp_path / "frontend",
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    samples = 0
    try:
        deadline = time.monotonic() + 5
        while process.poll() is None or lock.exists():
            owner_path = lock / "owner.json"
            try:
                raw = owner_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                time.sleep(0.001)
                continue
            assert raw
            value = json.loads(raw)
            assert value["version"] == 4
            assert value["nonce"]
            samples += 1
            if time.monotonic() >= deadline:
                raise AssertionError("owner metadata reader probe timed out")
            time.sleep(0.001)
        assert process.wait(timeout=5) == 0
        assert samples > 20
        assert node_modules.is_symlink()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_cleanup_does_not_unlink_a_replaced_successor_lock(tmp_path: Path):
    frontend, shared, node_modules, temp_dir, lock, env = _fixture(tmp_path)
    successor_stage = temp_dir / f"deeper-notebook-feature-contract-{'f' * 32}"
    next_script = f"""#!/usr/bin/env node
import {{ mkdirSync, renameSync, writeFileSync }} from 'node:fs'
const lock = process.env.FEATURE_LOCK_PATH
const stage = process.env.FEATURE_SUCCESSOR_STAGE
const old = `${{lock}}.old`
renameSync(lock, old)
mkdirSync(lock)
mkdirSync(stage)
const owner = {{
  version: 4,
  pid: 4000000,
  pgid: 4000000,
  nonce: 'f'.repeat(32),
  startToken: 'Thu Jan 01 00:00:00 1970',
  argvHash: '0'.repeat(64),
  stage,
  state: 'running'
}}
writeFileSync(`${{lock}}/.owner.tmp`, JSON.stringify(owner))
renameSync(`${{lock}}/.owner.tmp`, `${{lock}}/owner.json`)
"""
    next_bin = shared / ".bin" / "next"
    next_bin.write_text(next_script, encoding="utf-8")
    next_bin.chmod(0o755)
    env["FEATURE_LOCK_PATH"] = str(lock)
    env["FEATURE_SUCCESSOR_STAGE"] = str(successor_stage)
    completed = subprocess.run(
        ["node", str(tmp_path / "frontend/scripts/run-feature-build-contract.mjs")],
        cwd=tmp_path / "frontend",
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert lock.exists()
    assert _owner_from_lock(lock)["nonce"] == "f" * 32
    assert successor_stage.exists()
    assert node_modules.is_symlink()
    assert node_modules.resolve() == shared.resolve()


def test_pid_start_mismatch_is_safe_only_when_group_is_gone(tmp_path: Path):
    _, shared, node_modules, temp_dir, lock, env = _fixture(tmp_path)
    stale_stage = temp_dir / f"deeper-notebook-feature-contract-{'0' * 32}"
    stale_stage.mkdir()
    _write_owner_lock(
        lock,
        _stale_owner(stale_stage, pid=os.getpid(), pgid=4_000_000),
    )
    completed = subprocess.run(
        ["node", str(tmp_path / "frontend/scripts/run-feature-build-contract.mjs")],
        cwd=tmp_path / "frontend",
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert not lock.exists()
    assert not stale_stage.exists()
    assert node_modules.is_symlink()
    assert node_modules.resolve() == shared.resolve()


def test_lock_symlink_fails_closed_without_touching_target(tmp_path: Path):
    _, _, node_modules, temp_dir, lock, env = _fixture(tmp_path)
    lock_target = temp_dir / "lock-target"
    lock_target.mkdir()
    (lock_target / "marker").write_text("untouched", encoding="utf-8")
    lock.symlink_to(lock_target, target_is_directory=True)
    completed = subprocess.run(
        ["node", str(tmp_path / "frontend/scripts/run-feature-build-contract.mjs")],
        cwd=tmp_path / "frontend",
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert lock.is_symlink()
    assert (lock_target / "marker").read_text(encoding="utf-8") == "untouched"
    assert node_modules.is_symlink()


def test_owner_metadata_symlink_fails_closed_without_touching_target(tmp_path: Path):
    _, _, node_modules, temp_dir, lock, env = _fixture(tmp_path)
    lock.mkdir()
    target = temp_dir / "owner-target.json"
    target.write_text("untouched", encoding="utf-8")
    (lock / "owner.json").symlink_to(target)
    completed = subprocess.run(
        ["node", str(tmp_path / "frontend/scripts/run-feature-build-contract.mjs")],
        cwd=tmp_path / "frontend",
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert (lock / "owner.json").is_symlink()
    assert target.read_text(encoding="utf-8") == "untouched"
    assert node_modules.is_symlink()


def test_stage_symlink_fails_closed_without_deleting_target(tmp_path: Path):
    _, _, node_modules, temp_dir, lock, env = _fixture(tmp_path)
    nonce = "0" * 32
    stage_target = temp_dir / "stage-target"
    stage_target.mkdir()
    (stage_target / "marker").write_text("untouched", encoding="utf-8")
    stage = temp_dir / f"deeper-notebook-feature-contract-{nonce}"
    stage.symlink_to(stage_target, target_is_directory=True)
    _write_owner_lock(lock, _stale_owner(stage))
    completed = subprocess.run(
        ["node", str(tmp_path / "frontend/scripts/run-feature-build-contract.mjs")],
        cwd=tmp_path / "frontend",
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert stage.is_symlink()
    assert (stage_target / "marker").read_text(encoding="utf-8") == "untouched"
    assert node_modules.is_symlink()


def test_pid_start_mismatch_with_live_group_fails_closed(tmp_path: Path):
    _, _, node_modules, temp_dir, lock, env = _fixture(tmp_path)
    nonce = "0" * 32
    stage = temp_dir / f"deeper-notebook-feature-contract-{nonce}"
    stage.mkdir()
    live_group = os.getpgid(os.getpid())
    _write_owner_lock(
        lock,
        _stale_owner(stage, pid=os.getpid(), pgid=live_group),
    )
    completed = subprocess.run(
        ["node", str(tmp_path / "frontend/scripts/run-feature-build-contract.mjs")],
        cwd=tmp_path / "frontend",
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert lock.exists()
    assert stage.exists()
    assert node_modules.is_symlink()
