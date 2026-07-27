"""Guarded resolution and one-time migration of desktop-owned state.

The canonical directory is ``.deeper-notebook``.  A legacy-only
``.open-notebook-plus`` directory is moved with one same-volume atomic rename,
after a durable receipt and exclusive owner lock have been written outside
both roots.  The migration never copies, merges, or deletes the legacy data.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import socket
import stat
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from deeper_notebook.identity import DATA_DIR_NAME, LEGACY_DATA_DIR_NAME
from desktop.paths import user_home

MigrationState = Literal[
    "not-needed",
    "ready",
    "migration-pending",
    "migration-deferred",
    "migration-conflict",
    "migration-failed",
    "rollback-available",
]


@dataclass(frozen=True)
class DataRootDecision:
    state: MigrationState
    active_root: Path
    canonical_root: Path
    legacy_root: Path
    receipt_path: Path | None = None
    reason_code: str | None = None


class DataRootUnavailableError(RuntimeError):
    """Raised when choosing a writable root would risk losing user data."""

    def __init__(self, decision: DataRootDecision):
        self.decision = decision
        super().__init__(
            "Desktop data root is unavailable: "
            f"{decision.state} ({decision.reason_code or 'unspecified'}). "
            f"See migration receipt: {decision.receipt_path or 'not available'}"
        )


class _CriticalPathError(RuntimeError):
    pass


class _ValidationError(RuntimeError):
    pass


class _AtomicRenameUnavailable(RuntimeError):
    pass


class _InjectedFailure(RuntimeError):
    def __init__(self, stage: str):
        self.stage = stage
        super().__init__(stage)


LOCK_FILE_NAME = "data-root-migration.lock"
_MIGRATION_DIRECTORY_NAME = ".deeper-notebook-migrations"
_CRITICAL_FILES = (
    Path("config.toml"),
    Path("launcher.env"),
    Path("update_state.json"),
    Path("venv/.lock-hash"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_manifest(root: Path) -> dict[str, tuple[str, str]]:
    """Return a content/type manifest without following any symlink."""
    manifest: dict[str, tuple[str, str]] = {}

    def visit(directory: Path) -> None:
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                if entry.is_symlink():
                    raise _CriticalPathError("root-tree-symlink")
                if entry.is_dir(follow_symlinks=False):
                    manifest[relative] = ("directory", "")
                    visit(path)
                elif entry.is_file(follow_symlinks=False):
                    manifest[relative] = ("file", _sha256(path))
                else:
                    mode = stat.S_IFMT(entry.stat(follow_symlinks=False).st_mode)
                    manifest[relative] = ("special", str(mode))

    visit(root)
    return manifest


def classify_roots(canonical: Path, legacy: Path) -> DataRootDecision:
    """Classify the two roots without modifying either path."""
    canonical = Path(canonical)
    legacy = Path(legacy)
    canonical_exists = _path_exists(canonical)
    legacy_exists = _path_exists(legacy)

    if not canonical_exists and not legacy_exists:
        return DataRootDecision(
            "not-needed", canonical, canonical, legacy
        )

    if canonical.is_symlink():
        return DataRootDecision(
            "migration-conflict",
            legacy if legacy_exists else canonical,
            canonical,
            legacy,
            reason_code="canonical-root-symlink",
        )

    if legacy.is_symlink():
        try:
            same_target = (
                canonical_exists
                and canonical.is_dir()
                and legacy.resolve(strict=True) == canonical.resolve(strict=True)
            )
        except (OSError, RuntimeError):
            same_target = False
        if same_target:
            return DataRootDecision("ready", canonical, canonical, legacy)
        return DataRootDecision(
            "migration-conflict",
            canonical if canonical_exists else legacy,
            canonical,
            legacy,
            reason_code="legacy-root-symlink",
        )

    if canonical_exists and not canonical.is_dir():
        return DataRootDecision(
            "migration-conflict",
            canonical,
            canonical,
            legacy,
            reason_code="canonical-root-not-directory",
        )
    if legacy_exists and not legacy.is_dir():
        return DataRootDecision(
            "migration-conflict",
            canonical if canonical_exists else legacy,
            canonical,
            legacy,
            reason_code="legacy-root-not-directory",
        )

    if canonical_exists and not legacy_exists:
        return DataRootDecision("ready", canonical, canonical, legacy)
    if legacy_exists and not canonical_exists:
        return DataRootDecision(
            "migration-pending", legacy, canonical, legacy
        )

    try:
        equivalent = _tree_manifest(canonical) == _tree_manifest(legacy)
    except (OSError, _CriticalPathError):
        equivalent = False
    if equivalent:
        return DataRootDecision("ready", canonical, canonical, legacy)
    return DataRootDecision(
        "migration-conflict",
        canonical,
        canonical,
        legacy,
        reason_code="non-equivalent-roots",
    )


def _reject_symlink_components(root: Path, relative: Path) -> None:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise _CriticalPathError("critical-path-symlink")
        if not _path_exists(current):
            return


def _snapshot_critical_hashes(root: Path) -> dict[str, str]:
    """Hash regular critical files and reject symlinks in critical paths."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise _CriticalPathError("critical-root-invalid")

    hashes: dict[str, str] = {}
    for relative in _CRITICAL_FILES:
        _reject_symlink_components(root, relative)
        target = root / relative
        if target.is_file():
            hashes[relative.as_posix()] = _sha256(target)

    data_path = root / "data"
    _reject_symlink_components(root, Path("data"))
    if data_path.exists() and not data_path.is_dir():
        raise _CriticalPathError("critical-data-path-not-directory")
    if data_path.is_dir():
        for directory, directory_names, file_names in os.walk(
            data_path, followlinks=False
        ):
            base = Path(directory)
            for name in list(directory_names):
                candidate = base / name
                if candidate.is_symlink():
                    raise _CriticalPathError("critical-path-symlink")
            for name in file_names:
                candidate = base / name
                if candidate.is_symlink():
                    raise _CriticalPathError("critical-path-symlink")
                mode = candidate.stat(follow_symlinks=False).st_mode
                if stat.S_ISREG(mode):
                    relative = candidate.relative_to(root).as_posix()
                    hashes[relative] = _sha256(candidate)
    return dict(sorted(hashes.items()))


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write while persisting migration metadata")
        view = view[written:]


def _json_bytes(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _fsync_directory(path: Path) -> None:
    """Durably flush a directory on POSIX and Windows."""
    path = Path(path)
    if sys.platform != "win32":
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        fd = os.open(path, flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return

    # Windows directory handles require FILE_FLAG_BACKUP_SEMANTICS.
    import ctypes
    from ctypes import wintypes

    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x80000000,  # GENERIC_READ
        0x00000007,  # FILE_SHARE_READ | WRITE | DELETE
        None,
        3,  # OPEN_EXISTING
        0x02000000,  # FILE_FLAG_BACKUP_SEMANTICS
        None,
    )
    invalid_handle = wintypes.HANDLE(-1).value
    if handle == invalid_handle:
        raise ctypes.WinError()
    try:
        if not ctypes.windll.kernel32.FlushFileBuffers(handle):
            raise ctypes.WinError()
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _write_new_json(path: Path, payload: dict[str, object]) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(path, flags, 0o600)
    try:
        _write_all(fd, _json_bytes(payload))
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_directory(path.parent)


def _replace_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        _write_new_json(temporary, payload)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if _path_exists(temporary):
            temporary.unlink()


def _device_id(path: Path) -> int:
    return Path(path).stat().st_dev


def _raise_posix_rename_error(
    error: int, source: Path, destination: Path
) -> None:
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            error, os.strerror(error), str(destination)
        )
    unsupported_errors = {
        errno.EXDEV,
        errno.EINVAL,
        getattr(errno, "ENOSYS", errno.EINVAL),
        getattr(errno, "ENOTSUP", errno.EINVAL),
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }
    if error in unsupported_errors:
        raise _AtomicRenameUnavailable(
            f"exclusive directory rename unavailable: errno {error}"
        )
    raise OSError(
        error,
        os.strerror(error),
        f"{source} -> {destination}",
    )


def _rename_macos_no_replace(source: Path, destination: Path) -> None:
    """Atomically rename a directory with macOS ``RENAME_EXCL``."""
    import ctypes

    try:
        renamex_np = ctypes.CDLL(None, use_errno=True).renamex_np
    except (AttributeError, OSError) as exc:
        raise _AtomicRenameUnavailable(
            "renamex_np is unavailable"
        ) from exc
    renamex_np.argtypes = (
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renamex_np.restype = ctypes.c_int
    if renamex_np(
        os.fsencode(source),
        os.fsencode(destination),
        0x00000004,  # RENAME_EXCL
    ) == 0:
        return
    _raise_posix_rename_error(
        ctypes.get_errno(), Path(source), Path(destination)
    )


def _rename_linux_no_replace(source: Path, destination: Path) -> None:
    """Atomically rename a directory with Linux ``RENAME_NOREPLACE``."""
    import ctypes

    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except (AttributeError, OSError) as exc:
        raise _AtomicRenameUnavailable(
            "renameat2 is unavailable"
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    at_fdcwd = -100
    if renameat2(
        at_fdcwd,
        os.fsencode(source),
        at_fdcwd,
        os.fsencode(destination),
        0x00000001,  # RENAME_NOREPLACE
    ) == 0:
        return
    _raise_posix_rename_error(
        ctypes.get_errno(), Path(source), Path(destination)
    )


def _rename_windows_no_replace(source: Path, destination: Path) -> None:
    """Atomically rename a directory without ``MOVEFILE_REPLACE_EXISTING``."""
    import ctypes
    from ctypes import wintypes

    try:
        move_file = ctypes.WinDLL(
            "kernel32", use_last_error=True
        ).MoveFileExW
    except (AttributeError, OSError) as exc:
        raise _AtomicRenameUnavailable(
            "MoveFileExW is unavailable"
        ) from exc
    move_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
    )
    move_file.restype = wintypes.BOOL
    if move_file(
        str(source),
        str(destination),
        0x00000008,  # MOVEFILE_WRITE_THROUGH; deliberately no REPLACE flag
    ):
        return
    error = ctypes.get_last_error()
    if error in {80, 183}:  # ERROR_FILE_EXISTS / ERROR_ALREADY_EXISTS
        raise FileExistsError(error, "destination exists", str(destination))
    if error in {
        1,  # ERROR_INVALID_FUNCTION
        17,  # ERROR_NOT_SAME_DEVICE
        50,  # ERROR_NOT_SUPPORTED
        120,  # ERROR_CALL_NOT_IMPLEMENTED
    }:
        raise _AtomicRenameUnavailable(
            f"exclusive directory rename unavailable: Windows error {error}"
        )
    raise OSError(
        error,
        f"MoveFileExW failed with Windows error {error}",
        f"{source} -> {destination}",
    )


def _rename_directory_no_replace(
    source: Path, destination: Path
) -> None:
    """Use only native atomic directory renames that reject destinations."""
    if sys.platform == "darwin":
        _rename_macos_no_replace(source, destination)
        return
    if sys.platform == "linux":
        _rename_linux_no_replace(source, destination)
        return
    if sys.platform == "win32":
        _rename_windows_no_replace(source, destination)
        return
    raise _AtomicRenameUnavailable(
        f"unsupported platform for exclusive rename: {sys.platform}"
    )


def _process_start_time(pid: int) -> str | None:
    """Return an OS-derived process creation marker suitable for PID reuse."""
    if pid <= 0:
        return None
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return None
            try:
                creation = wintypes.FILETIME()
                exit_time = wintypes.FILETIME()
                kernel = wintypes.FILETIME()
                user = wintypes.FILETIME()
                ok = ctypes.windll.kernel32.GetProcessTimes(
                    handle,
                    ctypes.byref(creation),
                    ctypes.byref(exit_time),
                    ctypes.byref(kernel),
                    ctypes.byref(user),
                )
                if not ok:
                    return None
                ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
                return str(ticks)
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except (AttributeError, OSError):
            return None
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    value = " ".join(result.stdout.split())
    return value or None


def _pid_exists(pid: int) -> bool | None:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        status = _windows_process_status(pid)
        if status == "live":
            return True
        if status == "absent":
            return False
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def _windows_process_status(
    pid: int,
) -> Literal["live", "absent", "unknown"]:
    """Query Windows process state without sending any signal.

    Access denied is positive evidence that the PID exists under another
    security context. Only explicit not-found errors establish absence;
    every other failure remains unknown and therefore non-reclaimable.
    """
    import ctypes

    process_query_limited_information = 0x1000
    error_access_denied = 5
    error_invalid_parameter = 87
    error_not_found = 1168
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(
        process_query_limited_information, False, pid
    )
    if handle:
        kernel32.CloseHandle(handle)
        return "live"
    error = ctypes.get_last_error()
    if error == error_access_denied:
        return "live"
    if error in {error_invalid_parameter, error_not_found}:
        return "absent"
    return "unknown"


def _read_lock(lock_path: Path) -> tuple[dict[str, object], os.stat_result] | None:
    try:
        before = lock_path.lstat()
        if not stat.S_ISREG(before.st_mode):
            return None
        raw = lock_path.read_bytes()
        after = lock_path.lstat()
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            return None
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return None
        required = {
            "pid",
            "hostname",
            "process_start_time",
            "migration_id",
            "created_at",
        }
        if set(payload) != required:
            return None
        if (
            not isinstance(payload["pid"], int)
            or not isinstance(payload["hostname"], str)
            or not isinstance(payload["process_start_time"], str)
            or not isinstance(payload["migration_id"], str)
            or not isinstance(payload["created_at"], str)
        ):
            return None
        return payload, after
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _lock_is_verified_stale(payload: dict[str, object]) -> bool:
    if payload["hostname"] != socket.gethostname():
        return False
    pid = int(payload["pid"])
    exists = _pid_exists(pid)
    if exists is False:
        return True
    if exists is not True:
        return False
    stored_start = str(payload["process_start_time"])
    if stored_start.startswith("unavailable-"):
        return False
    current_start = _process_start_time(pid)
    if current_start is None:
        return False
    return current_start != stored_start


def _acquire_lock(lock_path: Path, migration_id: str) -> bool:
    start_time = _process_start_time(os.getpid())
    payload: dict[str, object] = {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "process_start_time": start_time or f"unavailable-{time.time_ns()}",
        "migration_id": migration_id,
        "created_at": _now(),
    }
    for attempt in range(2):
        try:
            _write_new_json(lock_path, payload)
            return True
        except FileExistsError:
            existing = _read_lock(lock_path)
            if existing is None or not _lock_is_verified_stale(existing[0]):
                return False
            if attempt:
                return False
            try:
                current = lock_path.lstat()
                observed = existing[1]
                if (current.st_dev, current.st_ino) != (
                    observed.st_dev,
                    observed.st_ino,
                ):
                    return False
                lock_path.unlink()
                _fsync_directory(lock_path.parent)
            except OSError:
                return False
    return False


def _release_owned_lock(lock_path: Path, migration_id: str) -> None:
    existing = _read_lock(lock_path)
    if existing is None or existing[0].get("migration_id") != migration_id:
        return
    try:
        current = lock_path.lstat()
        observed = existing[1]
        if (current.st_dev, current.st_ino) != (observed.st_dev, observed.st_ino):
            return
        lock_path.unlink()
        _fsync_directory(lock_path.parent)
    except OSError:
        # Never remove an unverified replacement lock.
        return


def _create_compatibility_link(canonical: Path, legacy: Path) -> None:
    if _path_exists(legacy):
        raise FileExistsError(str(legacy))
    os.symlink(canonical, legacy, target_is_directory=True)


def _operator_instructions(
    canonical: Path, legacy: Path, receipt_path: Path
) -> list[str]:
    return [
        "Keep all Deeper Notebook write-capable services stopped.",
        f"Review the critical hashes and validation state in {receipt_path}.",
        (
            f"Do not move or delete {canonical} or {legacy} until their current "
            "contents and any compatibility link have been inspected."
        ),
        (
            f"If the canonical hashes still match the receipt, remove only a "
            f"verified compatibility link at {legacy}, then atomically rename "
            f"{canonical} back to {legacy} on the same volume."
        ),
    ]


def _invoke_failure(
    failure_injector: Callable[[str], None] | None, stage: str
) -> None:
    if failure_injector is None:
        return
    try:
        failure_injector(stage)
    except Exception as exc:
        raise _InjectedFailure(stage) from exc


def _reason_for_exception(exc: BaseException) -> str:
    if isinstance(exc, _InjectedFailure):
        return f"injected-{exc.stage.replace('_', '-')}"
    if isinstance(exc, _CriticalPathError):
        return str(exc)
    if isinstance(exc, _ValidationError):
        return str(exc)
    if isinstance(exc, _AtomicRenameUnavailable):
        return "atomic-rename-unavailable"
    if isinstance(exc, OSError):
        return "filesystem-operation-failed"
    return "migration-step-failed"


def _safe_replace_receipt(
    receipt_path: Path, payload: dict[str, object]
) -> None:
    try:
        _replace_json(receipt_path, payload)
    except OSError:
        # Preserve the last durable receipt if the status update cannot land.
        pass


def _unresolved_rollback(
    receipt_dir: Path, canonical: Path, legacy: Path
) -> DataRootDecision | None:
    """Find a durable unresolved rollback marker for these exact roots."""
    if (
        not receipt_dir.is_dir()
        or receipt_dir.is_symlink()
        or not canonical.exists()
    ):
        return None
    try:
        receipt_paths = sorted(
            receipt_dir.glob("migration-*.json"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
    except OSError:
        return None
    for receipt_path in receipt_paths:
        try:
            if receipt_path.is_symlink():
                continue
            mode = receipt_path.stat(follow_symlinks=False).st_mode
            if not stat.S_ISREG(mode):
                continue
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            if (
                payload.get("canonical_path") != str(canonical)
                or payload.get("source_path") != str(legacy)
            ):
                continue
            status = payload.get("status")
            if status in {
                "completed",
                "conflict",
                "deferred",
                "failed",
                "rolled-back",
            }:
                return None
            if status in {"started", "rollback-available"}:
                return DataRootDecision(
                    "rollback-available",
                    canonical,
                    canonical,
                    legacy,
                    receipt_path,
                    str(
                        payload.get("rollback_reason_code")
                        or "unresolved-rollback"
                    ),
                )
        except (OSError, ValueError, json.JSONDecodeError, AttributeError):
            continue
    return None


def migrate_data_root(
    canonical: Path,
    legacy: Path,
    *,
    receipt_dir: Path | None = None,
    failure_injector: Callable[[str], None] | None = None,
) -> DataRootDecision:
    """Migrate one legacy-only root under the guarded atomic contract."""
    canonical = Path(canonical)
    legacy = Path(legacy)
    initial = classify_roots(canonical, legacy)
    if initial.state != "migration-pending":
        return initial

    receipt_dir = Path(
        receipt_dir or canonical.parent / _MIGRATION_DIRECTORY_NAME
    )
    migration_id = uuid.uuid4().hex
    receipt_path = receipt_dir / f"migration-{migration_id}.json"
    lock_path = receipt_dir / LOCK_FILE_NAME
    receipt_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if receipt_dir.is_symlink():
        return DataRootDecision(
            "migration-deferred",
            legacy,
            canonical,
            legacy,
            reason_code="migration-metadata-directory-symlink",
        )
    try:
        os.chmod(receipt_dir, 0o700)
    except OSError:
        pass

    try:
        acquired = _acquire_lock(lock_path, migration_id)
    except OSError:
        acquired = False
    if not acquired:
        return DataRootDecision(
            "migration-deferred",
            legacy,
            canonical,
            legacy,
            reason_code="migration-lock-contended",
        )

    started: dict[str, object] = {
        "status": "started",
        "migration_id": migration_id,
        "source_path": str(legacy),
        "canonical_path": str(canonical),
        "started_at": _now(),
        "rollback_instructions": _operator_instructions(
            canonical, legacy, receipt_path
        ),
    }
    renamed = False
    compatibility_link_created = False
    before_hashes: dict[str, str] = {}
    try:
        _write_new_json(receipt_path, started)
        _invoke_failure(failure_injector, "after_receipt")

        if _device_id(legacy) != _device_id(canonical.parent):
            deferred = {
                **started,
                "status": "deferred",
                "reason_code": "cross-device-atomic-rename-unavailable",
                "completed_at": _now(),
            }
            _replace_json(receipt_path, deferred)
            return DataRootDecision(
                "migration-deferred",
                legacy,
                canonical,
                legacy,
                receipt_path,
                "cross-device-atomic-rename-unavailable",
            )

        source_before = legacy.lstat()
        before_hashes = _snapshot_critical_hashes(legacy)
        started = {
            **started,
            "critical_hashes_before": before_hashes,
        }
        _replace_json(receipt_path, started)

        if _path_exists(canonical):
            reason_code = "canonical-root-appeared"
            conflict = {
                **started,
                "status": "conflict",
                "reason_code": reason_code,
                "completed_at": _now(),
            }
            _replace_json(receipt_path, conflict)
            return DataRootDecision(
                "migration-conflict",
                legacy,
                canonical,
                legacy,
                receipt_path,
                reason_code,
            )
        source_after = legacy.lstat()
        if (
            source_before.st_dev,
            source_before.st_ino,
            stat.S_IFMT(source_before.st_mode),
        ) != (
            source_after.st_dev,
            source_after.st_ino,
            stat.S_IFMT(source_after.st_mode),
        ):
            reason_code = "legacy-root-changed"
            conflict = {
                **started,
                "status": "conflict",
                "reason_code": reason_code,
                "completed_at": _now(),
            }
            _replace_json(receipt_path, conflict)
            return DataRootDecision(
                "migration-conflict",
                legacy,
                canonical,
                legacy,
                receipt_path,
                reason_code,
            )
        try:
            _rename_directory_no_replace(legacy, canonical)
        except FileExistsError:
            reason_code = "canonical-root-appeared"
            conflict = {
                **started,
                "status": "conflict",
                "reason_code": reason_code,
                "critical_hashes_before": before_hashes,
                "completed_at": _now(),
            }
            _replace_json(receipt_path, conflict)
            return DataRootDecision(
                "migration-conflict",
                legacy,
                canonical,
                legacy,
                receipt_path,
                reason_code,
            )
        except _AtomicRenameUnavailable:
            reason_code = "atomic-rename-unavailable"
            deferred = {
                **started,
                "status": "deferred",
                "reason_code": reason_code,
                "critical_hashes_before": before_hashes,
                "completed_at": _now(),
            }
            _replace_json(receipt_path, deferred)
            return DataRootDecision(
                "migration-deferred",
                legacy,
                canonical,
                legacy,
                receipt_path,
                reason_code,
            )
        renamed = True
        _fsync_directory(canonical.parent)
        _invoke_failure(failure_injector, "after_rename")

        after_hashes = _snapshot_critical_hashes(canonical)
        if after_hashes != before_hashes:
            raise _ValidationError("critical-hash-validation-failed")
        _invoke_failure(failure_injector, "after_validation")

        compatibility_reason: str | None = None
        try:
            _create_compatibility_link(canonical, legacy)
            compatibility_link_created = True
            _fsync_directory(canonical.parent)
        except OSError:
            compatibility_reason = "link-unavailable"
        _invoke_failure(failure_injector, "after_link")

        completed: dict[str, object] = {
            **started,
            "status": "completed",
            "completed_at": _now(),
            "critical_hashes_before": before_hashes,
            "critical_hashes_after": after_hashes,
            "validation": {"critical_hashes_match": True},
            "compatibility_link_created": compatibility_link_created,
            "compatibility_link_reason_code": compatibility_reason,
            "operator_instructions": _operator_instructions(
                canonical, legacy, receipt_path
            ),
        }
        _replace_json(receipt_path, completed)
        _invoke_failure(failure_injector, "after_receipt_finalization")
        return DataRootDecision(
            "ready",
            canonical,
            canonical,
            legacy,
            receipt_path,
        )
    except BaseException as exc:
        reason_code = _reason_for_exception(exc)
        if not renamed:
            failed = {
                **started,
                "status": "failed",
                "failed_at": _now(),
                "reason_code": reason_code,
                "operator_instructions": _operator_instructions(
                    canonical, legacy, receipt_path
                ),
            }
            if receipt_path.exists():
                _safe_replace_receipt(receipt_path, failed)
            return DataRootDecision(
                "migration-failed",
                legacy,
                canonical,
                legacy,
                receipt_path if receipt_path.exists() else None,
                reason_code,
            )

        rollback_problem: str | None = None
        try:
            if compatibility_link_created:
                if (
                    not legacy.is_symlink()
                    or legacy.resolve(strict=True)
                    != canonical.resolve(strict=True)
                ):
                    raise _ValidationError(
                        "compatibility-link-ownership-uncertain"
                    )
                legacy.unlink()
                _fsync_directory(canonical.parent)
            if _path_exists(legacy):
                raise _ValidationError("legacy-path-reappeared")
            if _snapshot_critical_hashes(canonical) != before_hashes:
                raise _ValidationError("rollback-hash-mismatch")
            _rename_directory_no_replace(canonical, legacy)
            _fsync_directory(legacy.parent)
        except BaseException as rollback_exc:
            rollback_problem = _reason_for_exception(rollback_exc)

        if rollback_problem is not None:
            rollback_available = {
                **started,
                "status": "rollback-available",
                "failed_at": _now(),
                "reason_code": reason_code,
                "rollback_reason_code": rollback_problem,
                "critical_hashes_before": before_hashes,
                "operator_instructions": _operator_instructions(
                    canonical, legacy, receipt_path
                ),
            }
            _safe_replace_receipt(receipt_path, rollback_available)
            active = canonical if canonical.exists() else legacy
            return DataRootDecision(
                "rollback-available",
                active,
                canonical,
                legacy,
                receipt_path,
                rollback_problem,
            )

        rolled_back = {
            **started,
            "status": "rolled-back",
            "failed_at": _now(),
            "reason_code": reason_code,
            "critical_hashes_before": before_hashes,
            "operator_instructions": _operator_instructions(
                canonical, legacy, receipt_path
            ),
        }
        _safe_replace_receipt(receipt_path, rolled_back)
        return DataRootDecision(
            "migration-failed",
            legacy,
            canonical,
            legacy,
            receipt_path,
            reason_code,
        )
    finally:
        _release_owned_lock(lock_path, migration_id)


def resolve_data_root(
    *,
    home: Path | None = None,
    failure_injector: Callable[[str], None] | None = None,
) -> DataRootDecision:
    """Resolve, and when safe migrate, the desktop data root."""
    base = Path(home) if home is not None else user_home()
    canonical = base / DATA_DIR_NAME
    legacy = base / LEGACY_DATA_DIR_NAME
    rollback = _unresolved_rollback(
        base / _MIGRATION_DIRECTORY_NAME, canonical, legacy
    )
    if rollback is not None:
        return rollback
    decision = classify_roots(canonical, legacy)
    if decision.state != "migration-pending":
        return decision
    return migrate_data_root(
        canonical,
        legacy,
        receipt_dir=base / _MIGRATION_DIRECTORY_NAME,
        failure_injector=failure_injector,
    )


def active_data_root(*, home: Path | None = None) -> Path:
    """Return the writable root, blocking only unsafe/uncertain states."""
    decision = resolve_data_root(home=home)
    safe_deferred_reasons = {
        "cross-device-atomic-rename-unavailable",
        "atomic-rename-unavailable",
    }
    if (
        decision.state in {"migration-conflict", "rollback-available"}
        or (
            decision.state == "migration-deferred"
            and decision.reason_code not in safe_deferred_reasons
        )
    ):
        raise DataRootUnavailableError(decision)
    return decision.active_root
