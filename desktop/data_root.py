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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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
RECOVERY_DIRECTORY_NAME = ".deeper-notebook-recovery"
CONFLICT_RECOVERY_RECEIPT_NAME = "data-root-conflict-recovery.json"
_CRITICAL_FILES = (
    Path("config.toml"),
    Path("launcher.env"),
    Path("update_state.json"),
    Path("venv/.lock-hash"),
)
_CONTROLLED_DATA_ROOT_ENV = "DEEPER_NOTEBOOK_DATA_DIR"


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


def recovery_metadata_root(*, home: Path | None = None) -> Path:
    """Return metadata storage that is never either product data root."""
    base = Path(home) if home is not None else user_home()
    return base / RECOVERY_DIRECTORY_NAME


@dataclass(frozen=True)
class SecureDirectory:
    """An owned directory bound to a validated no-follow descriptor."""

    path: Path
    fd: int
    parent_fd: int | None
    name: str | None
    device: int
    inode: int
    windows_handle: int | None = None

    def verify_visible_identity(self) -> None:
        if self.windows_handle is not None:
            if _windows_path_is_reparse_point(self.path):
                raise _CriticalPathError("recovery-directory-identity-changed")
            try:
                current = self.path.stat(follow_symlinks=False)
            except OSError as exc:
                raise _CriticalPathError("recovery-directory-identity-changed") from exc
            if (
                not stat.S_ISDIR(current.st_mode)
                or current.st_dev != self.device
                or current.st_ino != self.inode
            ):
                raise _CriticalPathError("recovery-directory-identity-changed")
            return
        if self.parent_fd is None or self.name is None:
            return
        try:
            current = os.stat(
                self.name,
                dir_fd=self.parent_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise _CriticalPathError("recovery-directory-identity-changed") from exc
        if (
            not stat.S_ISDIR(current.st_mode)
            or current.st_dev != self.device
            or current.st_ino != self.inode
        ):
            raise _CriticalPathError("recovery-directory-identity-changed")


def _windows_path_is_reparse_point(path: Path) -> bool:
    if sys.platform != "win32":
        return path.is_symlink()

    import ctypes
    from ctypes import wintypes

    get_attributes = ctypes.WinDLL("kernel32", use_last_error=True).GetFileAttributesW
    get_attributes.argtypes = (wintypes.LPCWSTR,)
    get_attributes.restype = wintypes.DWORD
    attributes = get_attributes(str(path))
    if attributes == 0xFFFFFFFF:
        raise ctypes.WinError(ctypes.get_last_error())
    return bool(attributes & 0x00000400)  # FILE_ATTRIBUTE_REPARSE_POINT


def _open_windows_directory_handle(path: Path) -> int:
    """Hold a directory against rename/reparse swaps for pathname operations."""
    import ctypes
    from ctypes import wintypes

    create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
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
        0xC0000000,  # GENERIC_READ | GENERIC_WRITE
        0x00000003,  # FILE_SHARE_READ | FILE_SHARE_WRITE; no delete sharing
        None,
        3,  # OPEN_EXISTING
        0x02200000,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
        None,
    )
    invalid_handle = wintypes.HANDLE(-1).value
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    raw_handle = int(handle)
    try:
        if _windows_path_is_reparse_point(path):
            raise _CriticalPathError("owned-directory-symlink")
    except BaseException:
        _close_windows_handle(raw_handle)
        raise
    return raw_handle


def _close_windows_handle(handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    close_handle = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    if not close_handle(handle):
        raise ctypes.WinError(ctypes.get_last_error())


def _windows_current_user_sid() -> str:
    import csv

    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise _CriticalPathError("windows-owner-sid-unavailable")
    try:
        sid = next(csv.reader([result.stdout.strip()]))[1].strip()
    except (IndexError, StopIteration):
        sid = ""
    if not sid.startswith("S-1-"):
        raise _CriticalPathError("windows-owner-sid-unavailable")
    return sid


def _windows_path_owner_sid(path: Path) -> str:
    import ctypes
    from ctypes import wintypes

    owner = wintypes.LPVOID()
    descriptor = wintypes.LPVOID()
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    get_security = advapi32.GetNamedSecurityInfoW
    get_security.argtypes = (
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.LPVOID),
    )
    get_security.restype = wintypes.DWORD
    error = get_security(
        str(path),
        1,  # SE_FILE_OBJECT
        0x00000001,  # OWNER_SECURITY_INFORMATION
        ctypes.byref(owner),
        None,
        None,
        None,
        ctypes.byref(descriptor),
    )
    if error:
        raise ctypes.WinError(error)

    string_sid = wintypes.LPWSTR()
    convert = advapi32.ConvertSidToStringSidW
    convert.argtypes = (wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR))
    convert.restype = wintypes.BOOL
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    local_free = kernel32.LocalFree
    local_free.argtypes = (wintypes.HLOCAL,)
    local_free.restype = wintypes.HLOCAL
    try:
        if not convert(owner, ctypes.byref(string_sid)):
            raise ctypes.WinError(ctypes.get_last_error())
        return string_sid.value
    finally:
        if string_sid:
            local_free(string_sid)
        if descriptor:
            local_free(descriptor)


def _create_windows_owned_directory(path: Path, reason: str) -> bool:
    """Create a directory with the current user as owner and a protected ACL."""
    import ctypes
    from ctypes import wintypes

    sid = _windows_current_user_sid()
    descriptor = wintypes.LPVOID()
    descriptor_size = wintypes.DWORD()
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    convert = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.DWORD),
    )
    convert.restype = wintypes.BOOL
    sddl = f"O:{sid}D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
    if not convert(sddl, 1, ctypes.byref(descriptor), ctypes.byref(descriptor_size)):
        raise _CriticalPathError(reason)

    class _SecurityAttributes(ctypes.Structure):
        _fields_ = (
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", wintypes.LPVOID),
            ("bInheritHandle", wintypes.BOOL),
        )

    attributes = _SecurityAttributes(
        ctypes.sizeof(_SecurityAttributes),
        descriptor,
        False,
    )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_directory = kernel32.CreateDirectoryW
    create_directory.argtypes = (
        wintypes.LPCWSTR,
        ctypes.POINTER(_SecurityAttributes),
    )
    create_directory.restype = wintypes.BOOL
    local_free = kernel32.LocalFree
    local_free.argtypes = (wintypes.HLOCAL,)
    local_free.restype = wintypes.HLOCAL
    try:
        if create_directory(str(path), ctypes.byref(attributes)):
            return True
        error = ctypes.get_last_error()
        if error == 183:  # ERROR_ALREADY_EXISTS
            return False
        raise _CriticalPathError(reason) from ctypes.WinError(error)
    finally:
        local_free(descriptor)


def _harden_windows_owned_directory(path: Path, reason: str) -> None:
    import ctypes
    from ctypes import wintypes

    sid = _windows_current_user_sid()
    if _windows_path_owner_sid(path) != sid:
        raise _CriticalPathError(reason)
    descriptor = wintypes.LPVOID()
    descriptor_size = wintypes.DWORD()
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    convert = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.DWORD),
    )
    convert.restype = wintypes.BOOL
    sddl = f"D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
    if not convert(sddl, 1, ctypes.byref(descriptor), ctypes.byref(descriptor_size)):
        raise _CriticalPathError(reason)

    set_security = advapi32.SetFileSecurityW
    set_security.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
    )
    set_security.restype = wintypes.BOOL
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    local_free = kernel32.LocalFree
    local_free.argtypes = (wintypes.HLOCAL,)
    local_free.restype = wintypes.HLOCAL
    try:
        security_information = (
            0x00000004  # DACL_SECURITY_INFORMATION
            | 0x80000000  # PROTECTED_DACL_SECURITY_INFORMATION
        )
        if not set_security(str(path), security_information, descriptor):
            raise _CriticalPathError(reason)
    finally:
        local_free(descriptor)

    if _windows_path_owner_sid(path) != sid:
        raise _CriticalPathError(reason)


def _open_windows_append_file(path: Path) -> int:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
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
        # FILE_APPEND_DATA keeps the handle append-only: omitting
        # FILE_WRITE_DATA prevents any write from replacing existing bytes.
        # FILE_GENERIC_READ is required by the CRT's O_APPEND path so it can
        # position an existing file at EOF before each write.
        0x0012008D,  # FILE_APPEND_DATA | FILE_GENERIC_READ
        0x00000003,  # FILE_SHARE_READ | FILE_SHARE_WRITE; no delete sharing
        None,
        4,  # OPEN_ALWAYS
        0x80200000,  # WRITE_THROUGH | OPEN_REPARSE_POINT
        None,
    )
    invalid_handle = wintypes.HANDLE(-1).value
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    raw_handle = int(handle)
    try:
        if _windows_path_is_reparse_point(path):
            raise _CriticalPathError("recovery-log-file-unsafe")
        return msvcrt.open_osfhandle(
            raw_handle,
            os.O_APPEND | os.O_WRONLY | os.O_BINARY,
        )
    except BaseException:
        _close_windows_handle(raw_handle)
        raise


def _secure_directory_flags() -> int:
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise _CriticalPathError("secure-directory-handles-unavailable")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _validate_directory_fd(
    fd: int,
    *,
    ownership_reason: str | None,
    harden_permissions: bool,
) -> os.stat_result:
    result = os.fstat(fd)
    if not stat.S_ISDIR(result.st_mode):
        raise _CriticalPathError(ownership_reason or "recovery-parent-is-not-directory")
    getuid = getattr(os, "getuid", None)
    if (
        ownership_reason is not None
        and getuid is not None
        and result.st_uid != getuid()
    ):
        raise _CriticalPathError(ownership_reason)
    if harden_permissions:
        os.fchmod(fd, 0o700)
        result = os.fstat(fd)
        if stat.S_IMODE(result.st_mode) & 0o077:
            raise _CriticalPathError("recovery-directory-permissions-unsafe")
    return result


@contextmanager
def _open_directory_path(path: Path) -> Iterator[SecureDirectory]:
    if sys.platform == "win32":
        handle = _open_windows_directory_handle(path)
        try:
            result = path.stat(follow_symlinks=False)
            if not stat.S_ISDIR(result.st_mode):
                raise _CriticalPathError("recovery-parent-is-not-directory")
            directory = SecureDirectory(
                path,
                -1,
                None,
                None,
                result.st_dev,
                result.st_ino,
                handle,
            )
            directory.verify_visible_identity()
            yield directory
            directory.verify_visible_identity()
        finally:
            _close_windows_handle(handle)
        return

    fd = os.open(path, _secure_directory_flags())
    try:
        result = _validate_directory_fd(
            fd,
            ownership_reason=None,
            harden_permissions=False,
        )
        yield SecureDirectory(path, fd, None, None, result.st_dev, result.st_ino)
    finally:
        os.close(fd)


@contextmanager
def _open_child_directory(
    parent: SecureDirectory,
    name: str,
    *,
    path: Path,
    symlink_reason: str,
    ownership_reason: str,
) -> Iterator[SecureDirectory]:
    if sys.platform == "win32":
        _create_windows_owned_directory(path, ownership_reason)
        if _windows_path_is_reparse_point(path):
            raise _CriticalPathError(symlink_reason)
        handle = _open_windows_directory_handle(path)
        try:
            result = path.stat(follow_symlinks=False)
            if not stat.S_ISDIR(result.st_mode):
                raise _CriticalPathError(ownership_reason)
            _harden_windows_owned_directory(path, ownership_reason)
            directory = SecureDirectory(
                path,
                -1,
                None,
                name,
                result.st_dev,
                result.st_ino,
                handle,
            )
            directory.verify_visible_identity()
            yield directory
            directory.verify_visible_identity()
        finally:
            _close_windows_handle(handle)
        return

    try:
        os.mkdir(name, mode=0o700, dir_fd=parent.fd)
    except FileExistsError:
        pass
    try:
        fd = os.open(name, _secure_directory_flags(), dir_fd=parent.fd)
    except OSError as exc:
        raise _CriticalPathError(symlink_reason) from exc
    try:
        result = _validate_directory_fd(
            fd,
            ownership_reason=ownership_reason,
            harden_permissions=True,
        )
        directory = SecureDirectory(
            path,
            fd,
            parent.fd,
            name,
            result.st_dev,
            result.st_ino,
        )
        directory.verify_visible_identity()
        yield directory
        directory.verify_visible_identity()
    finally:
        os.close(fd)


@contextmanager
def open_owned_directory(path: Path) -> Iterator[SecureDirectory]:
    """Create and bind one owned private directory below an existing parent."""
    path = Path(path).absolute()
    with _open_directory_path(path.parent) as parent:
        with _open_child_directory(
            parent,
            path.name,
            path=path,
            symlink_reason="owned-directory-symlink",
            ownership_reason="owned-directory-not-owned",
        ) as directory:
            yield directory


@contextmanager
def open_recovery_metadata_directory(
    *, home: Path | None = None
) -> Iterator[SecureDirectory]:
    """Bind the sibling recovery root through owned no-follow descriptors."""
    base = Path(home) if home is not None else user_home()
    with _open_directory_path(base) as home_directory:
        with _open_child_directory(
            home_directory,
            RECOVERY_DIRECTORY_NAME,
            path=base / RECOVERY_DIRECTORY_NAME,
            symlink_reason="recovery-metadata-directory-symlink",
            ownership_reason="recovery-metadata-directory-not-owned",
        ) as recovery_directory:
            yield recovery_directory


@contextmanager
def open_recovery_log_directory(
    *, home: Path | None = None
) -> Iterator[SecureDirectory]:
    """Bind the sibling recovery log directory without pathname writes."""
    with open_recovery_metadata_directory(home=home) as recovery_directory:
        with _open_child_directory(
            recovery_directory,
            "logs",
            path=recovery_directory.path / "logs",
            symlink_reason="recovery-log-directory-symlink",
            ownership_reason="recovery-log-directory-not-owned",
        ) as log_directory:
            yield log_directory


def _safe_tree_summary(root: Path) -> dict[str, object]:
    """Hash a root without exposing file contents or selecting it for use."""
    if root.is_symlink() or not root.is_dir():
        raise _CriticalPathError("recovery-root-is-not-safe-directory")
    digest = hashlib.sha256()
    file_count = 0
    directory_count = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise _CriticalPathError("recovery-root-tree-symlink")
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path.is_file():
            file_count += 1
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
        elif path.is_dir():
            directory_count += 1
        else:
            raise _CriticalPathError("recovery-root-tree-special-file")
        digest.update(b"\0")
    return {
        "path": str(root),
        "tree_sha256": digest.hexdigest(),
        "file_count": file_count,
        "directory_count": directory_count,
    }


def write_conflict_recovery_evidence(
    decision: DataRootDecision,
    *,
    home: Path | None = None,
    _race_hook: Callable[[str, Path], None] | None = None,
) -> tuple[Path, dict[str, object]]:
    """Persist read-only conflict evidence outside both ambiguous roots."""
    if (
        decision.state != "migration-conflict"
        or decision.reason_code != "non-equivalent-roots"
    ):
        raise ValueError("only divergent data roots use conflict recovery")

    recovery_root = recovery_metadata_root(home=home)
    if recovery_root in {decision.canonical_root, decision.legacy_root}:
        raise _CriticalPathError("recovery-metadata-overlaps-data-root")
    with open_recovery_metadata_directory(home=home) as recovery_directory:
        recovery_root = recovery_directory.path
        if _race_hook is not None:
            _race_hook("recovery-opened", recovery_root)
        payload: dict[str, object] = {
            "schema_version": 1,
            "recorded_at": _now(),
            "state": decision.state,
            "reason_code": decision.reason_code,
            "selected_root": None,
            "mutated_roots": [],
            "canonical": _safe_tree_summary(decision.canonical_root),
            "legacy": _safe_tree_summary(decision.legacy_root),
        }
        atomic_replace_json(
            recovery_directory,
            CONFLICT_RECOVERY_RECEIPT_NAME,
            payload,
        )
        with _open_child_directory(
            recovery_directory,
            "logs",
            path=recovery_root / "logs",
            symlink_reason="recovery-log-directory-symlink",
            ownership_reason="recovery-log-directory-not-owned",
        ) as log_directory:
            if _race_hook is not None:
                _race_hook("logs-opened", log_directory.path)
            atomic_replace_json(log_directory, "recovery.log", payload)
    return recovery_root, payload


def classify_roots(canonical: Path, legacy: Path) -> DataRootDecision:
    """Classify the two roots without modifying either path."""
    canonical = Path(canonical)
    legacy = Path(legacy)
    canonical_exists = _path_exists(canonical)
    legacy_exists = _path_exists(legacy)

    if not canonical_exists and not legacy_exists:
        return DataRootDecision("not-needed", canonical, canonical, legacy)

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
        return DataRootDecision("migration-pending", legacy, canonical, legacy)

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

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
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
        0x40000000,  # GENERIC_WRITE, required by FlushFileBuffers
        0x00000007,  # FILE_SHARE_READ | WRITE | DELETE
        None,
        3,  # OPEN_EXISTING
        0x02000000,  # FILE_FLAG_BACKUP_SEMANTICS
        None,
    )
    invalid_handle = wintypes.HANDLE(-1).value
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        flush = kernel32.FlushFileBuffers
        flush.argtypes = (wintypes.HANDLE,)
        flush.restype = wintypes.BOOL
        if not flush(handle):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        _close_windows_handle(int(handle))


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


def atomic_replace_json(
    directory: SecureDirectory,
    name: str,
    payload: dict[str, object],
) -> None:
    """Atomically replace JSON relative to a bound no-follow directory."""
    if directory.windows_handle is not None:
        directory.verify_visible_identity()
        _replace_json(directory.path / name, payload)
        directory.verify_visible_identity()
        return

    temporary = f".{name}.{uuid.uuid4().hex}.tmp"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(temporary, flags, 0o600, dir_fd=directory.fd)
        try:
            _write_all(fd, _json_bytes(payload))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(
            temporary,
            name,
            src_dir_fd=directory.fd,
            dst_dir_fd=directory.fd,
        )
        os.fsync(directory.fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory.fd)
        except FileNotFoundError:
            pass


def append_recovery_log(
    directory: SecureDirectory,
    name: str,
    payload: bytes,
) -> None:
    """Append to an owned regular file relative to a bound log directory."""
    flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    if directory.windows_handle is not None:
        directory.verify_visible_identity()
        fd = _open_windows_append_file(directory.path / name)
    else:
        fd = os.open(name, flags, 0o600, dir_fd=directory.fd)
    try:
        result = os.fstat(fd)
        getuid = getattr(os, "getuid", None)
        if (
            not stat.S_ISREG(result.st_mode)
            or (getuid is not None and result.st_uid != getuid())
            or result.st_nlink != 1
            or result.st_dev != directory.device
        ):
            raise _CriticalPathError("recovery-log-file-unsafe")
        if sys.platform != "win32":
            os.fchmod(fd, 0o600)
            if stat.S_IMODE(os.fstat(fd).st_mode) & 0o177:
                raise _CriticalPathError("recovery-log-file-permissions-unsafe")
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    if directory.windows_handle is not None:
        _fsync_directory(directory.path)
        directory.verify_visible_identity()
    else:
        os.fsync(directory.fd)


def unlink_owned_file(
    directory: SecureDirectory,
    name: str,
    *,
    missing_ok: bool = False,
) -> None:
    """Unlink one entry relative to a bound owned directory and fsync it."""
    try:
        if directory.windows_handle is not None:
            directory.verify_visible_identity()
            (directory.path / name).unlink()
        else:
            os.unlink(name, dir_fd=directory.fd)
    except FileNotFoundError:
        if not missing_ok:
            raise
    if directory.windows_handle is not None:
        _fsync_directory(directory.path)
        directory.verify_visible_identity()
    else:
        os.fsync(directory.fd)


def _device_id(path: Path) -> int:
    return Path(path).stat().st_dev


def _raise_posix_rename_error(error: int, source: Path, destination: Path) -> None:
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error, os.strerror(error), str(destination))
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
        raise _AtomicRenameUnavailable("renamex_np is unavailable") from exc
    renamex_np.argtypes = (
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renamex_np.restype = ctypes.c_int
    if (
        renamex_np(
            os.fsencode(source),
            os.fsencode(destination),
            0x00000004,  # RENAME_EXCL
        )
        == 0
    ):
        return
    _raise_posix_rename_error(ctypes.get_errno(), Path(source), Path(destination))


def _rename_linux_no_replace(source: Path, destination: Path) -> None:
    """Atomically rename a directory with Linux ``RENAME_NOREPLACE``."""
    import ctypes

    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except (AttributeError, OSError) as exc:
        raise _AtomicRenameUnavailable("renameat2 is unavailable") from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    at_fdcwd = -100
    if (
        renameat2(
            at_fdcwd,
            os.fsencode(source),
            at_fdcwd,
            os.fsencode(destination),
            0x00000001,  # RENAME_NOREPLACE
        )
        == 0
    ):
        return
    _raise_posix_rename_error(ctypes.get_errno(), Path(source), Path(destination))


def _rename_windows_no_replace(source: Path, destination: Path) -> None:
    """Atomically rename a directory without ``MOVEFILE_REPLACE_EXISTING``."""
    import ctypes
    from ctypes import wintypes

    try:
        move_file = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
    except (AttributeError, OSError) as exc:
        raise _AtomicRenameUnavailable("MoveFileExW is unavailable") from exc
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


def _rename_directory_no_replace(source: Path, destination: Path) -> None:
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
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
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


def _invoke_failure(failure_injector: Callable[[str], None] | None, stage: str) -> None:
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


def _safe_replace_receipt(receipt_path: Path, payload: dict[str, object]) -> None:
    try:
        _replace_json(receipt_path, payload)
    except OSError:
        # Preserve the last durable receipt if the status update cannot land.
        pass


def _unresolved_rollback(
    receipt_dir: Path, canonical: Path, legacy: Path
) -> DataRootDecision | None:
    """Find a durable unresolved rollback marker for these exact roots."""
    if not receipt_dir.is_dir() or receipt_dir.is_symlink() or not canonical.exists():
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
            if payload.get("canonical_path") != str(canonical) or payload.get(
                "source_path"
            ) != str(legacy):
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
                    str(payload.get("rollback_reason_code") or "unresolved-rollback"),
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

    receipt_dir = Path(receipt_dir or canonical.parent / _MIGRATION_DIRECTORY_NAME)
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
                if not legacy.is_symlink() or legacy.resolve(
                    strict=True
                ) != canonical.resolve(strict=True):
                    raise _ValidationError("compatibility-link-ownership-uncertain")
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
    rollback = _unresolved_rollback(base / _MIGRATION_DIRECTORY_NAME, canonical, legacy)
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
    if home is None:
        raw_controlled_root = os.environ.get(_CONTROLLED_DATA_ROOT_ENV, "").strip()
        if raw_controlled_root:
            controlled_root = Path(raw_controlled_root).expanduser()
            if not controlled_root.is_absolute():
                raise ValueError(
                    f"{_CONTROLLED_DATA_ROOT_ENV} must be an absolute path"
                )
            controlled_root = Path(os.path.abspath(controlled_root))
            if controlled_root == Path(controlled_root.anchor):
                raise ValueError(
                    f"{_CONTROLLED_DATA_ROOT_ENV} must not be a filesystem root"
                )
            current = Path(controlled_root.anchor)
            for part in controlled_root.parts[1:]:
                current = current / part
                if current.is_symlink():
                    raise ValueError(
                        f"{_CONTROLLED_DATA_ROOT_ENV} must not traverse a symlink"
                    )
            controlled_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                os.chmod(controlled_root, 0o700)
            except OSError:
                pass
            return controlled_root
    decision = resolve_data_root(home=home)
    safe_deferred_reasons = {
        "cross-device-atomic-rename-unavailable",
        "atomic-rename-unavailable",
    }
    if decision.state in {"migration-conflict", "rollback-available"} or (
        decision.state == "migration-deferred"
        and decision.reason_code not in safe_deferred_reasons
    ):
        raise DataRootUnavailableError(decision)
    return decision.active_root
