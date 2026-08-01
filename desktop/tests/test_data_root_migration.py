from __future__ import annotations

import ast
import ctypes
import json
import os
import socket
from pathlib import Path

import pytest

from desktop import data_root
from desktop.data_root import (
    DataRootUnavailableError,
    classify_roots,
    migrate_data_root,
)


def _seed_legacy(root: Path) -> dict[str, str]:
    files = {
        "config.toml": "theme='research-core'\npassword='do-not-copy-to-receipt'\n",
        "launcher.env": "DEEPER_NOTEBOOK_LOG_LEVEL=INFO\n",
        "update_state.json": '{"enabled": true}\n',
        "data/notebooks/source.txt": "private source contents\n",
        "venv/.lock-hash": "lock-hash-value\n",
        "non-critical/keep.txt": "keep this too\n",
    }
    for relative, contents in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
    return files


def _roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    canonical = tmp_path / ".deeper-notebook"
    legacy = tmp_path / ".open-notebook-plus"
    receipts = tmp_path / ".deeper-notebook-migrations"
    return canonical, legacy, receipts


@pytest.mark.parametrize(
    ("canonical_exists", "legacy_exists", "expected"),
    [
        (False, False, "not-needed"),
        (True, False, "ready"),
        (False, True, "migration-pending"),
        (True, True, "ready"),
    ],
)
def test_classifies_roots(
    tmp_path, canonical_exists, legacy_exists, expected
):
    canonical, legacy, _ = _roots(tmp_path)
    if canonical_exists:
        canonical.mkdir()
    if legacy_exists:
        legacy.mkdir()
    assert classify_roots(canonical, legacy).state == expected


def test_active_data_root_uses_explicit_controlled_data_root(tmp_path, monkeypatch):
    """A caller can isolate a native runtime without changing a user profile."""
    controlled_root = tmp_path / "controlled-runtime"
    monkeypatch.setenv("DEEPER_NOTEBOOK_DATA_DIR", str(controlled_root))

    assert data_root.active_data_root() == controlled_root
    assert controlled_root.is_dir()


def test_active_data_root_rejects_controlled_root_through_symlink(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    redirected_parent = tmp_path / "redirected"
    redirected_parent.symlink_to(target, target_is_directory=True)
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_DATA_DIR", str(redirected_parent / "runtime")
    )

    with pytest.raises(ValueError, match="symlink"):
        data_root.active_data_root()


def test_active_data_root_rejects_filesystem_root_override(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_DATA_DIR", Path("/").anchor)

    with pytest.raises(ValueError, match="filesystem root"):
        data_root.active_data_root()


def test_non_equivalent_roots_are_conflict(tmp_path):
    canonical, legacy, _ = _roots(tmp_path)
    (canonical / "config.toml").parent.mkdir(parents=True)
    (legacy / "config.toml").parent.mkdir(parents=True)
    (canonical / "config.toml").write_text("theme='dark'")
    (legacy / "config.toml").write_text("theme='light-blue'")
    assert classify_roots(canonical, legacy).state == "migration-conflict"


def test_legacy_symlink_to_canonical_is_ready(tmp_path):
    canonical, legacy, _ = _roots(tmp_path)
    canonical.mkdir()
    legacy.symlink_to(canonical, target_is_directory=True)

    decision = classify_roots(canonical, legacy)

    assert decision.state == "ready"
    assert decision.active_root == canonical


def test_two_root_symlinks_to_external_target_are_conflict(tmp_path):
    canonical, legacy, _ = _roots(tmp_path)
    external = tmp_path / "external-state"
    external.mkdir()
    canonical.symlink_to(external, target_is_directory=True)
    legacy.symlink_to(external, target_is_directory=True)

    decision = classify_roots(canonical, legacy)

    assert decision.state == "migration-conflict"
    assert decision.reason_code == "canonical-root-symlink"


def test_same_volume_migration_uses_atomic_no_replace(tmp_path, monkeypatch):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    calls: list[tuple[Path, Path]] = []
    real_rename = data_root._rename_directory_no_replace

    def tracked_rename(source, destination):
        calls.append((Path(source), Path(destination)))
        return real_rename(source, destination)

    monkeypatch.setattr(
        data_root, "_rename_directory_no_replace", tracked_rename
    )
    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "ready"
    assert (legacy, canonical) in calls
    assert canonical.is_dir()


def test_started_receipt_is_durable_before_root_move(tmp_path, monkeypatch):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    real_rename = data_root._rename_directory_no_replace
    observed_started: dict[str, object] = {}

    def tracked_rename(source, destination):
        if Path(source) == legacy and Path(destination) == canonical:
            receipt_paths = list(receipts.glob("*.json"))
            assert len(receipt_paths) == 1
            observed_started.update(json.loads(receipt_paths[0].read_text()))
            assert observed_started["status"] == "started"
        return real_rename(source, destination)

    monkeypatch.setattr(
        data_root, "_rename_directory_no_replace", tracked_rename
    )
    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "ready"
    assert observed_started["source_path"] == str(legacy)
    assert observed_started["canonical_path"] == str(canonical)
    assert observed_started["critical_hashes_before"]


def test_critical_hashes_match_after_migration(tmp_path):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)

    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    receipt = json.loads(decision.receipt_path.read_text())
    assert receipt["validation"]["critical_hashes_match"] is True
    assert receipt["critical_hashes_before"] == receipt["critical_hashes_after"]
    assert set(receipt["critical_hashes_before"]) == {
        "config.toml",
        "launcher.env",
        "update_state.json",
        "data/notebooks/source.txt",
        "venv/.lock-hash",
    }


def test_nonempty_conflicting_canonical_is_never_replaced(tmp_path, monkeypatch):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    canonical.mkdir()
    (canonical / "config.toml").write_text("different")
    root_moves: list[tuple[Path, Path]] = []
    real_rename = data_root._rename_directory_no_replace

    def tracked_rename(source, destination):
        if {Path(source), Path(destination)} == {legacy, canonical}:
            root_moves.append((Path(source), Path(destination)))
        return real_rename(source, destination)

    monkeypatch.setattr(
        data_root, "_rename_directory_no_replace", tracked_rename
    )
    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "migration-conflict"
    assert root_moves == []
    assert canonical.is_dir()
    assert legacy.is_dir()


def test_canonical_created_during_preflight_is_never_replaced(
    tmp_path, monkeypatch
):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    real_snapshot = data_root._snapshot_critical_hashes
    root_moves: list[tuple[Path, Path]] = []
    real_rename = data_root._rename_directory_no_replace

    def race_destination(root):
        result = real_snapshot(root)
        canonical.mkdir()
        (canonical / "racing-writer.txt").write_text("do not replace")
        return result

    def tracked_rename(source, destination):
        if Path(source) == legacy and Path(destination) == canonical:
            root_moves.append((Path(source), Path(destination)))
        return real_rename(source, destination)

    monkeypatch.setattr(
        data_root, "_snapshot_critical_hashes", race_destination
    )
    monkeypatch.setattr(
        data_root, "_rename_directory_no_replace", tracked_rename
    )
    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "migration-conflict"
    assert decision.reason_code == "canonical-root-appeared"
    assert root_moves == []
    assert (canonical / "racing-writer.txt").read_text() == "do not replace"
    assert legacy.is_dir()


def test_failed_validation_rolls_back_and_leaves_legacy_root(
    tmp_path, monkeypatch
):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    real_snapshot = data_root._snapshot_critical_hashes
    calls = 0

    def changed_snapshot(root):
        nonlocal calls
        calls += 1
        result = real_snapshot(root)
        if calls == 2:
            result["config.toml"] = "validation-mismatch"
        return result

    monkeypatch.setattr(
        data_root, "_snapshot_critical_hashes", changed_snapshot
    )
    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "migration-failed"
    assert decision.active_root == legacy
    assert legacy.is_dir()
    assert not canonical.exists()
    assert json.loads(decision.receipt_path.read_text())["status"] == "rolled-back"


def test_rollback_destination_race_preserves_both_roots(
    tmp_path, monkeypatch
):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    real_rename = data_root._rename_directory_no_replace
    rename_calls = 0

    def race_rollback_destination(source, destination):
        nonlocal rename_calls
        rename_calls += 1
        if rename_calls == 2:
            assert Path(source) == canonical
            assert Path(destination) == legacy
            legacy.mkdir()
            (legacy / "racing-writer.txt").write_text("preserve me")
        return real_rename(source, destination)

    def fail_after_validation(stage):
        if stage == "after_validation":
            raise RuntimeError("trigger rollback")

    monkeypatch.setattr(
        data_root,
        "_rename_directory_no_replace",
        race_rollback_destination,
    )
    decision = migrate_data_root(
        canonical,
        legacy,
        receipt_dir=receipts,
        failure_injector=fail_after_validation,
    )

    assert decision.state == "rollback-available"
    assert decision.reason_code == "filesystem-operation-failed"
    assert canonical.is_dir()
    assert (legacy / "racing-writer.txt").read_text() == "preserve me"


def test_rerun_after_success_is_idempotent(tmp_path, monkeypatch):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    first = migrate_data_root(canonical, legacy, receipt_dir=receipts)
    assert first.state == "ready"
    real_rename = data_root._rename_directory_no_replace
    second_root_moves: list[tuple[Path, Path]] = []

    def tracked_rename(source, destination):
        if {Path(source), Path(destination)} == {legacy, canonical}:
            second_root_moves.append((Path(source), Path(destination)))
        return real_rename(source, destination)

    monkeypatch.setattr(
        data_root, "_rename_directory_no_replace", tracked_rename
    )
    second = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert second.state == "ready"
    assert second.active_root == canonical
    assert second_root_moves == []


def test_compatibility_link_failure_is_recorded_but_migration_stays_ready(
    tmp_path, monkeypatch
):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)

    def denied_link(*_args, **_kwargs):
        raise OSError("directory links unavailable")

    monkeypatch.setattr(data_root, "_create_compatibility_link", denied_link)
    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    receipt = json.loads(decision.receipt_path.read_text())
    assert decision.state == "ready"
    assert receipt["compatibility_link_created"] is False
    assert receipt["compatibility_link_reason_code"] == "link-unavailable"
    assert canonical.is_dir()
    assert not legacy.exists()


def test_receipt_contains_hashes_but_no_contents_or_secrets(tmp_path):
    canonical, legacy, receipts = _roots(tmp_path)
    source_contents = _seed_legacy(legacy)

    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    receipt_text = decision.receipt_path.read_text()
    receipt = json.loads(receipt_text)
    assert receipt["source_path"] == str(legacy)
    assert receipt["canonical_path"] == str(canonical)
    assert receipt["critical_hashes_before"]
    for contents in source_contents.values():
        assert contents.strip() not in receipt_text
    assert "do-not-copy-to-receipt" not in receipt_text
    assert "private source contents" not in receipt_text


def test_live_lock_contention_returns_deferred_and_is_not_reclaimed(tmp_path):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    receipts.mkdir(mode=0o700)
    lock_path = receipts / data_root.LOCK_FILE_NAME
    lock_payload = {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "process_start_time": data_root._process_start_time(os.getpid()),
        "migration_id": "live-owner",
        "created_at": "2026-07-26T00:00:00+00:00",
    }
    lock_path.write_text(json.dumps(lock_payload))

    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "migration-deferred"
    assert decision.reason_code == "migration-lock-contended"
    assert decision.active_root == legacy
    assert json.loads(lock_path.read_text())["migration_id"] == "live-owner"


def test_lock_records_required_owner_fields(tmp_path):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    captured: dict[str, object] = {}

    def capture_lock(stage):
        if stage == "after_receipt":
            captured.update(
                json.loads((receipts / data_root.LOCK_FILE_NAME).read_text())
            )
            raise RuntimeError("test stop after durable receipt")

    decision = migrate_data_root(
        canonical,
        legacy,
        receipt_dir=receipts,
        failure_injector=capture_lock,
    )

    assert decision.state == "migration-failed"
    assert captured["pid"] == os.getpid()
    assert captured["hostname"] == socket.gethostname()
    assert captured["process_start_time"]
    assert captured["migration_id"]
    assert captured["created_at"]


def test_verified_dead_stale_lock_is_recovered(tmp_path, monkeypatch):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    receipts.mkdir(mode=0o700)
    lock_path = receipts / data_root.LOCK_FILE_NAME
    lock_path.write_text(
        json.dumps(
            {
                "pid": 999_999_999,
                "hostname": socket.gethostname(),
                "process_start_time": "old-start",
                "migration_id": "dead-owner",
                "created_at": "2026-07-25T00:00:00+00:00",
            }
        )
    )
    monkeypatch.setattr(data_root, "_pid_exists", lambda pid: False)

    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "ready"
    assert not lock_path.exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"not": "valid-lock-data"},
        {
            "pid": 999_999_999,
            "hostname": "another-host",
            "process_start_time": "unknown",
            "migration_id": "remote-owner",
            "created_at": "2026-07-25T00:00:00+00:00",
        },
    ],
)
def test_unknown_lock_owner_is_never_reclaimed(tmp_path, payload):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    receipts.mkdir(mode=0o700)
    lock_path = receipts / data_root.LOCK_FILE_NAME
    lock_path.write_text(json.dumps(payload))

    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "migration-deferred"
    assert lock_path.exists()
    assert json.loads(lock_path.read_text()) == payload


def test_reused_pid_with_different_start_time_is_recovered(
    tmp_path, monkeypatch
):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    receipts.mkdir(mode=0o700)
    lock_path = receipts / data_root.LOCK_FILE_NAME
    lock_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "process_start_time": "old-process-start",
                "migration_id": "reused-pid-owner",
                "created_at": "2026-07-25T00:00:00+00:00",
            }
        )
    )
    monkeypatch.setattr(data_root, "_pid_exists", lambda pid: True)
    monkeypatch.setattr(
        data_root, "_process_start_time", lambda pid: "new-process-start"
    )

    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "ready"
    assert not lock_path.exists()


def test_unverifiable_lock_start_time_is_never_reclaimed(
    tmp_path, monkeypatch
):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    receipts.mkdir(mode=0o700)
    lock_path = receipts / data_root.LOCK_FILE_NAME
    lock_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "process_start_time": "unavailable-123",
                "migration_id": "unknown-live-owner",
                "created_at": "2026-07-25T00:00:00+00:00",
            }
        )
    )
    monkeypatch.setattr(data_root, "_pid_exists", lambda pid: True)
    monkeypatch.setattr(
        data_root, "_process_start_time", lambda pid: "now-observable"
    )

    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "migration-deferred"
    assert json.loads(lock_path.read_text())["migration_id"] == (
        "unknown-live-owner"
    )


@pytest.mark.parametrize(
    ("open_result", "last_error", "expected"),
    [
        (1234, 0, "live"),
        (0, 5, "live"),
        (0, 87, "absent"),
        (0, 1168, "absent"),
        (0, 31, "unknown"),
    ],
)
def test_windows_process_status_is_query_only_and_tri_state(
    monkeypatch, open_result, last_error, expected
):
    calls: list[tuple[int, bool, int]] = []

    class FakeKernel32:
        def OpenProcess(self, access, inherit, pid):
            calls.append((access, inherit, pid))
            return open_result

        def CloseHandle(self, handle):
            assert handle == open_result

    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: FakeKernel32(),
        raising=False,
    )
    monkeypatch.setattr(
        ctypes, "get_last_error", lambda: last_error, raising=False
    )

    assert data_root._windows_process_status(4321) == expected
    assert calls == [(0x1000, False, 4321)]


def test_windows_pid_probe_never_calls_os_kill(monkeypatch):
    monkeypatch.setattr(data_root.sys, "platform", "win32")
    monkeypatch.setattr(
        data_root, "_windows_process_status", lambda pid: "unknown"
    )

    def unsafe_kill(*_args):
        raise AssertionError("os.kill must never probe a Windows PID")

    monkeypatch.setattr(data_root.os, "kill", unsafe_kill)

    assert data_root._pid_exists(4321) is None


def test_session_guard_rejects_resolution_outside_test_home():
    with pytest.raises(AssertionError, match="outside"):
        data_root.active_data_root(home=Path("/task3-outside-test-home"))


@pytest.mark.parametrize(
    "stage",
    [
        "after_receipt",
        "after_rename",
        "after_validation",
        "after_link",
        "after_receipt_finalization",
    ],
)
def test_injected_failures_restore_legacy_path(tmp_path, stage):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)

    def fail_at(checkpoint):
        if checkpoint == stage:
            raise RuntimeError(f"injected at {stage}")

    decision = migrate_data_root(
        canonical,
        legacy,
        receipt_dir=receipts,
        failure_injector=fail_at,
    )

    assert decision.state == "migration-failed"
    assert decision.active_root == legacy
    assert legacy.is_dir()
    assert not canonical.exists()
    assert not legacy.is_symlink()
    receipt = json.loads(decision.receipt_path.read_text())
    assert receipt["status"] in {"failed", "rolled-back"}
    assert receipt["reason_code"] == f"injected-{stage.replace('_', '-')}"


def test_uncertain_rollback_returns_rollback_available_with_instructions(
    tmp_path,
):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)

    def mutate_then_fail(stage):
        if stage == "after_validation":
            (canonical / "config.toml").write_text("changed-after-validation")
            raise RuntimeError("trigger rollback")

    decision = migrate_data_root(
        canonical,
        legacy,
        receipt_dir=receipts,
        failure_injector=mutate_then_fail,
    )

    assert decision.state == "rollback-available"
    assert decision.active_root == canonical
    assert canonical.is_dir()
    assert not legacy.exists()
    receipt = json.loads(decision.receipt_path.read_text())
    assert receipt["status"] == "rollback-available"
    assert receipt["operator_instructions"]
    instructions = "\n".join(receipt["operator_instructions"])
    assert str(canonical) in instructions
    assert str(legacy) in instructions


def test_unresolved_rollback_receipt_blocks_later_active_root_resolution(
    tmp_path,
):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)

    def mutate_then_fail(stage):
        if stage == "after_validation":
            (canonical / "config.toml").write_text("changed-after-validation")
            raise RuntimeError("trigger rollback")

    first = migrate_data_root(
        canonical,
        legacy,
        receipt_dir=receipts,
        failure_injector=mutate_then_fail,
    )
    assert first.state == "rollback-available"

    later = data_root.resolve_data_root(home=tmp_path)

    assert later.state == "rollback-available"
    assert later.receipt_path == first.receipt_path
    with pytest.raises(DataRootUnavailableError):
        data_root.active_data_root(home=tmp_path)


def test_interrupted_started_receipt_with_moved_root_blocks_later_writers(
    tmp_path,
):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(canonical)
    receipts.mkdir(mode=0o700)
    receipt_path = receipts / "migration-interrupted.json"
    receipt_path.write_text(
        json.dumps(
            {
                "status": "started",
                "migration_id": "interrupted",
                "source_path": str(legacy),
                "canonical_path": str(canonical),
                "critical_hashes_before": data_root._snapshot_critical_hashes(
                    canonical
                ),
                "rollback_instructions": ["keep services stopped"],
            }
        )
    )

    decision = data_root.resolve_data_root(home=tmp_path)

    assert decision.state == "rollback-available"
    assert decision.receipt_path == receipt_path
    with pytest.raises(DataRootUnavailableError):
        data_root.active_data_root(home=tmp_path)


def test_new_completed_receipt_supersedes_older_started_receipt(tmp_path):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    receipts.mkdir(mode=0o700)
    old_receipt = receipts / "migration-old-crash.json"
    old_receipt.write_text(
        json.dumps(
            {
                "status": "started",
                "migration_id": "old-crash",
                "source_path": str(legacy),
                "canonical_path": str(canonical),
                "rollback_instructions": ["keep services stopped"],
            }
        )
    )
    os.utime(old_receipt, ns=(1, 1))

    migrated = migrate_data_root(canonical, legacy, receipt_dir=receipts)
    assert migrated.state == "ready"

    first_repeat = data_root.resolve_data_root(home=tmp_path)
    second_repeat = data_root.resolve_data_root(home=tmp_path)

    assert first_repeat.state == "ready"
    assert second_repeat.state == "ready"
    assert first_repeat.active_root == canonical


def test_live_migration_lock_blocks_write_capable_active_root(tmp_path):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    receipts.mkdir(mode=0o700)
    lock_path = receipts / data_root.LOCK_FILE_NAME
    lock_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "process_start_time": data_root._process_start_time(os.getpid()),
                "migration_id": "live-owner",
                "created_at": "2026-07-26T00:00:00+00:00",
            }
        )
    )

    with pytest.raises(DataRootUnavailableError):
        data_root.active_data_root(home=tmp_path)

    assert lock_path.exists()
    assert legacy.is_dir()


def test_critical_path_symlink_is_rejected_without_rename(tmp_path):
    canonical, legacy, receipts = _roots(tmp_path)
    legacy.mkdir()
    outside = tmp_path / "outside-config.toml"
    outside.write_text("theme='outside'")
    (legacy / "config.toml").symlink_to(outside)

    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "migration-failed"
    assert decision.reason_code == "critical-path-symlink"
    assert legacy.is_dir()
    assert not canonical.exists()


def test_cross_device_root_is_deferred_without_copy(tmp_path, monkeypatch):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    real_stat = data_root._device_id

    def different_devices(path):
        if Path(path) == legacy:
            return 100
        if Path(path) == canonical.parent:
            return 200
        return real_stat(path)

    monkeypatch.setattr(data_root, "_device_id", different_devices)
    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "migration-deferred"
    assert decision.reason_code == "cross-device-atomic-rename-unavailable"
    assert decision.active_root == legacy
    assert legacy.is_dir()
    assert not canonical.exists()


def test_exdev_from_root_rename_is_deferred_without_copy(
    tmp_path, monkeypatch
):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    def unavailable_atomic_rename(_source, _destination):
        raise data_root._AtomicRenameUnavailable("EXDEV")

    monkeypatch.setattr(
        data_root,
        "_rename_directory_no_replace",
        unavailable_atomic_rename,
    )
    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "migration-deferred"
    assert decision.reason_code == "atomic-rename-unavailable"
    assert legacy.is_dir()
    assert not canonical.exists()


def test_receipt_file_and_parent_are_fsynced_around_transitions(
    tmp_path, monkeypatch
):
    canonical, legacy, receipts = _roots(tmp_path)
    _seed_legacy(legacy)
    events: list[tuple[str, Path | None]] = []
    real_fsync = os.fsync
    real_fsync_directory = data_root._fsync_directory
    real_replace = os.replace
    real_rename = data_root._rename_directory_no_replace

    def tracked_fsync(fd):
        events.append(("file-fsync", None))
        return real_fsync(fd)

    def tracked_fsync_directory(path):
        events.append(("directory-fsync", Path(path)))
        return real_fsync_directory(path)

    def tracked_replace(source, destination):
        source = Path(source)
        destination = Path(destination)
        if source.parent == receipts and destination.parent == receipts:
            events.append(("receipt-finalize", None))
        return real_replace(source, destination)

    def tracked_rename(source, destination):
        events.append(("root-move", None))
        return real_rename(source, destination)

    monkeypatch.setattr(data_root.os, "fsync", tracked_fsync)
    monkeypatch.setattr(data_root, "_fsync_directory", tracked_fsync_directory)
    monkeypatch.setattr(data_root.os, "replace", tracked_replace)
    monkeypatch.setattr(
        data_root, "_rename_directory_no_replace", tracked_rename
    )
    decision = migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "ready"
    root_move_index = events.index(("root-move", None))
    assert ("file-fsync", None) in events[:root_move_index]
    assert ("directory-fsync", receipts) in events[:root_move_index]
    final_index = events.index(("receipt-finalize", None))
    assert ("file-fsync", None) in events[:final_index]
    assert ("directory-fsync", receipts) in events[final_index + 1 :]


def test_production_code_has_no_direct_data_directory_construction():
    repository_root = Path(__file__).resolve().parents[2]
    production_roots = (
        "api",
        "commands",
        "deeper_notebook",
        "desktop",
        "open_" "notebook",
        "scripts",
    )
    allowed = {
        Path("deeper_notebook/identity.py"),
        Path("desktop/data_root.py"),
    }
    violations: list[str] = []
    for root_name in production_roots:
        for path in (repository_root / root_name).rglob("*.py"):
            relative = path.relative_to(repository_root)
            if relative in allowed or "tests" in relative.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Constant)
                    and node.value in {".deeper-notebook", ".open-notebook-plus"}
                ):
                    violations.append(f"{relative}:{node.lineno}")
    assert violations == []
