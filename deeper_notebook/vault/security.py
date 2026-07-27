"""Race-safe, read-only filesystem boundary for approved Markdown vaults."""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Callable, Literal

from deeper_notebook.vault.parsers.common import configured_max_markdown_bytes

try:
    import pwd
except ImportError:  # pragma: no cover - Windows fails closed before root access
    pwd = None  # type: ignore[assignment]

PROTECTED_GLOBS = (
    "sources/**",
    "inbox/raw/**",
    "brain-engine/**",
    ".git/**",
    ".obsidian/**",
    "logseq/**",
)
INDEXABLE_MARKDOWN = frozenset({".md", ".markdown"})
INDEXABLE_METADATA = frozenset({".canvas", ".base"})
TEMPORARY_SUFFIXES = ("~", ".tmp", ".part", ".crdownload", ".download")

_SAFE_MESSAGES = {
    "invalid_root": "The approved root must be an existing absolute directory.",
    "unsafe_root": "The approved root is too broad or is a system directory.",
    "unsupported_platform": "Secure descriptor-relative vault access is unavailable.",
    "unsafe_symlink": "Symbolic links are not accepted by the vault reader.",
    "unsafe_hardlink": "Multiply linked files are not accepted by the vault reader.",
    "path_escape": "The candidate path escapes the approved root.",
    "not_regular_file": "The candidate is not a regular file.",
    "unreadable": "The candidate could not be read safely.",
    "file_too_large": "The candidate exceeds the configured parser limit.",
    "changed_during_read": "The candidate changed while it was being read.",
    "root_changed": "The approved root identity changed.",
}

PathKind = Literal[
    "markdown", "metadata", "connector", "control", "temporary", "ignored"
]


class VaultSecurityError(ValueError):
    """Typed error that never renders source content or local paths."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_SAFE_MESSAGES.get(code, "Vault filesystem access failed."))


@dataclass(frozen=True, slots=True)
class VaultPathClassification:
    kind: PathKind
    protected: bool

    @property
    def indexable(self) -> bool:
        return self.kind in {"markdown", "metadata"}


@dataclass(frozen=True, slots=True)
class SecureFileCandidate:
    relative_path: str
    device: int
    inode: int
    mode: int
    byte_size: int
    modified_ns: int


@dataclass(frozen=True, slots=True)
class SecureReadResult:
    relative_path: str
    content: bytes
    sha256: str
    byte_size: int
    modified_ns: int
    device: int
    inode: int
    mode: int


@dataclass(slots=True)
class ApprovedVaultRoot:
    """An immutable root identity pinned by an open directory descriptor."""

    path: Path
    device: int
    inode: int
    _fd: int
    _closed: bool = False

    def __enter__(self) -> "ApprovedVaultRoot":
        self._assert_current()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        os.close(self._fd)
        self._closed = True

    def _assert_current(self) -> os.stat_result:
        if self._closed:
            raise VaultSecurityError("root_changed")
        try:
            current = os.fstat(self._fd)
        except OSError as exc:
            raise VaultSecurityError("root_changed") from exc
        if (
            current.st_dev != self.device
            or current.st_ino != self.inode
            or not stat.S_ISDIR(current.st_mode)
        ):
            raise VaultSecurityError("root_changed")
        verification_fd = -1
        try:
            verification_fd = _open_absolute_directory(self.path)
            path_current = os.fstat(verification_fd)
        except (OSError, VaultSecurityError) as exc:
            raise VaultSecurityError("root_changed") from exc
        finally:
            if verification_fd >= 0:
                os.close(verification_fd)
        if (
            path_current.st_dev != self.device
            or path_current.st_ino != self.inode
            or not stat.S_ISDIR(path_current.st_mode)
        ):
            raise VaultSecurityError("root_changed")
        return current


def _descriptor_security_available() -> bool:
    return bool(
        os.name == "posix"
        and hasattr(os, "O_NOFOLLOW")
        and hasattr(os, "O_DIRECTORY")
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.stat in os.supports_follow_symlinks
    )


def _directory_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _file_flags() -> int:
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    return flags


def _open_child_directory(parent_fd: int, name: str) -> int:
    try:
        child_fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
    except OSError as exc:
        try:
            entry_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError:
            entry_stat = None
        if entry_stat is not None and stat.S_ISLNK(entry_stat.st_mode):
            raise VaultSecurityError("unsafe_symlink") from exc
        raise VaultSecurityError("invalid_root") from exc
    try:
        child_stat = os.fstat(child_fd)
        if not stat.S_ISDIR(child_stat.st_mode):
            raise VaultSecurityError("invalid_root")
    except BaseException:
        os.close(child_fd)
        raise
    return child_fd


def _open_absolute_directory(path: Path) -> int:
    current_fd = -1
    try:
        current_fd = os.open(os.path.sep, _directory_flags())
        for part in path.parts[1:]:
            child_fd = _open_child_directory(current_fd, part)
            os.close(current_fd)
            current_fd = child_fd
        return current_fd
    except BaseException:
        if current_fd >= 0:
            os.close(current_fd)
        raise


def _is_unsafe_root(path: Path) -> bool:
    normalized = os.path.normcase(str(path))
    if os.path.ismount(path):
        return True
    homes = {os.path.normcase(str(Path.home()))}
    if pwd is not None:
        try:
            homes.add(os.path.normcase(pwd.getpwuid(os.getuid()).pw_dir))
        except (KeyError, OSError):
            pass
    forbidden = {
        os.path.normcase(value)
        for value in (
            os.path.sep,
            "/System",
            "/Library",
            "/Applications",
            "/Users",
            "/Volumes",
            "/private",
            "/private/var",
            "/usr",
            "/bin",
            "/sbin",
            "/etc",
            "/var",
            "/tmp",
        )
    }
    forbidden.update(homes)
    if normalized in forbidden:
        return True

    drive, tail = os.path.splitdrive(str(path))
    if drive and tail in {"", os.path.sep}:
        return True
    return str(path).startswith(("\\\\", "//")) and len(path.parts) <= 2


def approve_vault_root(root: Path | str) -> ApprovedVaultRoot:
    """Validate and pin an explicitly selected root without following symlinks."""

    if not _descriptor_security_available():
        raise VaultSecurityError("unsupported_platform")

    expanded_text = os.path.expanduser(os.fspath(root))
    expanded = Path(expanded_text)
    if not expanded.is_absolute() or ".." in expanded.parts:
        raise VaultSecurityError("invalid_root")
    normalized = Path(os.path.normpath(expanded_text))
    if _is_unsafe_root(normalized):
        raise VaultSecurityError("unsafe_root")

    current_fd = -1
    try:
        current_fd = _open_absolute_directory(normalized)
        root_stat = os.fstat(current_fd)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise VaultSecurityError("invalid_root")
        return ApprovedVaultRoot(
            path=normalized,
            device=root_stat.st_dev,
            inode=root_stat.st_ino,
            _fd=current_fd,
        )
    except VaultSecurityError:
        if current_fd >= 0:
            os.close(current_fd)
        raise
    except OSError as exc:
        if current_fd >= 0:
            os.close(current_fd)
        raise VaultSecurityError("invalid_root") from exc


def _relative_parts(relative_path: str) -> tuple[str, ...]:
    if not isinstance(relative_path, str) or not relative_path or "\x00" in relative_path:
        raise VaultSecurityError("path_escape")
    if "\\" in relative_path:
        raise VaultSecurityError("path_escape")
    candidate = PurePosixPath(relative_path)
    if (
        not candidate.parts
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise VaultSecurityError("path_escape")
    return candidate.parts


def _is_temporary_name(name: str) -> bool:
    lower = name.casefold()
    return (
        lower.startswith((".#", "~$", "#"))
        or lower.endswith(TEMPORARY_SUFFIXES)
        or lower.endswith((".swp", ".swo", ".swx", ".lock", ".lck"))
        or (lower.startswith(".") and lower.endswith((".tmp", ".part")))
    )


def classify_vault_path(relative_path: str) -> VaultPathClassification:
    parts = _relative_parts(relative_path)
    folded = tuple(part.casefold() for part in parts)
    name = folded[-1]

    if _is_temporary_name(name):
        return VaultPathClassification("temporary", False)
    if folded[0] in {".git", ".obsidian", "logseq"} or any(
        part.startswith(".") for part in folded
    ):
        return VaultPathClassification("control", True)
    if folded[0] == "brain-engine":
        return VaultPathClassification("connector", True)

    protected = (
        folded[0] == "sources"
        or (len(folded) >= 2 and folded[:2] == ("inbox", "raw"))
    )
    suffix = PurePosixPath(name).suffix.casefold()
    if suffix in INDEXABLE_MARKDOWN:
        return VaultPathClassification("markdown", protected)
    if suffix in INDEXABLE_METADATA:
        return VaultPathClassification("metadata", protected)
    return VaultPathClassification("ignored", protected)


def _open_relative_file(
    root: ApprovedVaultRoot, parts: tuple[str, ...]
) -> tuple[int, list[int]]:
    root._assert_current()
    parent_fd = root._fd
    opened_directories: list[int] = []
    try:
        for part in parts[:-1]:
            child_fd = _open_child_directory(parent_fd, part)
            opened_directories.append(child_fd)
            parent_fd = child_fd
        try:
            file_fd = os.open(parts[-1], _file_flags(), dir_fd=parent_fd)
        except OSError as exc:
            try:
                entry_stat = os.stat(
                    parts[-1], dir_fd=parent_fd, follow_symlinks=False
                )
            except OSError:
                entry_stat = None
            if entry_stat is not None and stat.S_ISLNK(entry_stat.st_mode):
                raise VaultSecurityError("unsafe_symlink") from exc
            if entry_stat is not None and not stat.S_ISREG(entry_stat.st_mode):
                raise VaultSecurityError("not_regular_file") from exc
            raise VaultSecurityError("unreadable") from exc
        return file_fd, opened_directories
    except BaseException:
        for descriptor in reversed(opened_directories):
            os.close(descriptor)
        raise


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _validate_open_path_identity(
    root: ApprovedVaultRoot,
    parts: tuple[str, ...],
    opened_directories: list[int],
    file_stat: os.stat_result,
) -> None:
    parent_fd = root._fd
    for name, directory_fd in zip(parts[:-1], opened_directories, strict=True):
        try:
            path_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            descriptor_stat = os.fstat(directory_fd)
        except OSError as exc:
            raise VaultSecurityError("changed_during_read") from exc
        if (
            stat.S_ISLNK(path_stat.st_mode)
            or not stat.S_ISDIR(path_stat.st_mode)
            or path_stat.st_dev != descriptor_stat.st_dev
            or path_stat.st_ino != descriptor_stat.st_ino
        ):
            raise VaultSecurityError("changed_during_read")
        parent_fd = directory_fd

    try:
        final_path_stat = os.stat(
            parts[-1], dir_fd=parent_fd, follow_symlinks=False
        )
    except OSError as exc:
        raise VaultSecurityError("changed_during_read") from exc
    if (
        stat.S_ISLNK(final_path_stat.st_mode)
        or not stat.S_ISREG(final_path_stat.st_mode)
        or _identity(final_path_stat) != _identity(file_stat)
    ):
        raise VaultSecurityError("changed_during_read")


def _bounded_read(fd: int, limit: int) -> bytes:
    chunks: list[bytes] = []
    remaining = limit + 1
    while remaining:
        try:
            chunk = os.read(fd, min(remaining, 64 * 1024))
        except OSError as exc:
            raise VaultSecurityError("unreadable") from exc
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    content = b"".join(chunks)
    if len(content) > limit:
        raise VaultSecurityError("file_too_large")
    return content


def secure_read(
    root: ApprovedVaultRoot,
    relative_path: str,
    *,
    max_bytes: int | None = None,
    _between_read_passes: Callable[[], None] | None = None,
) -> SecureReadResult:
    """Read and hash one regular file twice through the same pinned descriptor."""

    parts = _relative_parts(relative_path)
    limit = configured_max_markdown_bytes(max_bytes)
    file_fd = -1
    opened_directories: list[int] = []
    try:
        file_fd, opened_directories = _open_relative_file(root, parts)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise VaultSecurityError("not_regular_file")
        if before.st_nlink != 1:
            raise VaultSecurityError("unsafe_hardlink")
        if before.st_size > limit:
            raise VaultSecurityError("file_too_large")

        first = _bounded_read(file_fd, limit)
        middle = os.fstat(file_fd)
        if _between_read_passes is not None:
            _between_read_passes()
        os.lseek(file_fd, 0, os.SEEK_SET)
        second = _bounded_read(file_fd, limit)
        after = os.fstat(file_fd)
        first_hash = hashlib.sha256(first).hexdigest()
        second_hash = hashlib.sha256(second).hexdigest()
        if (
            _identity(before) != _identity(middle)
            or _identity(middle) != _identity(after)
            or first_hash != second_hash
        ):
            raise VaultSecurityError("changed_during_read")
        _validate_open_path_identity(root, parts, opened_directories, after)
        root._assert_current()
        return SecureReadResult(
            relative_path=relative_path,
            content=second,
            sha256=second_hash,
            byte_size=len(second),
            modified_ns=after.st_mtime_ns,
            device=after.st_dev,
            inode=after.st_ino,
            mode=after.st_mode,
        )
    except VaultSecurityError:
        raise
    except OSError as exc:
        code = (
            "unsafe_symlink"
            if exc.errno in {errno.ELOOP, errno.EMLINK}
            else "unreadable"
        )
        raise VaultSecurityError(code) from exc
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        for descriptor in reversed(opened_directories):
            os.close(descriptor)


def list_secure_candidates(root: ApprovedVaultRoot) -> list[SecureFileCandidate]:
    """List regular descendants without following any directory or file symlink."""

    root._assert_current()
    candidates: list[SecureFileCandidate] = []

    def walk(directory_fd: int, prefix: tuple[str, ...]) -> None:
        try:
            with os.scandir(directory_fd) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as exc:
            raise VaultSecurityError("unreadable") from exc
        for entry in entries:
            name = entry.name
            relative_parts = (*prefix, name)
            relative = PurePosixPath(*relative_parts).as_posix()
            classification = classify_vault_path(relative)
            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISLNK(entry_stat.st_mode):
                continue
            if stat.S_ISDIR(entry_stat.st_mode):
                if classification.kind in {"control", "connector", "temporary"}:
                    continue
                try:
                    child_fd = os.open(name, _directory_flags(), dir_fd=directory_fd)
                except OSError:
                    continue
                try:
                    child_stat = os.fstat(child_fd)
                    if (
                        not stat.S_ISDIR(child_stat.st_mode)
                        or child_stat.st_dev != entry_stat.st_dev
                        or child_stat.st_ino != entry_stat.st_ino
                    ):
                        continue
                    walk(child_fd, relative_parts)
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(entry_stat.st_mode) or entry_stat.st_nlink != 1:
                continue
            candidates.append(
                SecureFileCandidate(
                    relative_path=relative,
                    device=entry_stat.st_dev,
                    inode=entry_stat.st_ino,
                    mode=entry_stat.st_mode,
                    byte_size=entry_stat.st_size,
                    modified_ns=entry_stat.st_mtime_ns,
                )
            )

    walk(root._fd, ())
    root._assert_current()
    return candidates


__all__ = [
    "INDEXABLE_MARKDOWN",
    "INDEXABLE_METADATA",
    "PROTECTED_GLOBS",
    "TEMPORARY_SUFFIXES",
    "ApprovedVaultRoot",
    "SecureFileCandidate",
    "SecureReadResult",
    "VaultPathClassification",
    "VaultSecurityError",
    "approve_vault_root",
    "classify_vault_path",
    "list_secure_candidates",
    "secure_read",
]
