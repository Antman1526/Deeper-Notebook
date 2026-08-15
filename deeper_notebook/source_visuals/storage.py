"""Exact-root storage for rebuildable source-derived visual assets."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import secrets
import stat
import threading
import time
import weakref
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised through platform capability checks.
    fcntl = None

from deeper_notebook.config import DATA_FOLDER
from deeper_notebook.source_visuals.contracts import (
    PreparedVisualAsset,
    SourceVisualRecord,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_ID = re.compile(r"^source:[A-Za-z0-9_-]+$")
_RELPATH = re.compile(r"^([0-9a-f]{2})/([0-9a-f]{64})/([0-9a-f]{64})\.webp$")
_TEMP_NAME = re.compile(r"^stage-([0-9a-f]{64})-([0-9a-f]{64})\.tmp$")
_UNVERIFIED_STAGE_NAME = re.compile(
    r"^\.unverified-stage-[0-9a-f]{64}-[0-9a-f]{64}\.tmp$"
)
TOMBSTONE = re.compile(r"^\.expired-([0-9a-f]{16})-([0-9a-f]{64})\.webp$")
_TEMP_DIR = ".tmp"
_TEMP_MARKER = ".deeper-notebook-source-visual-cache-v1"
_MUTATION_LOCK = ".mutation.lock"
_UNLINK_FENCE_PREFIX = ".unlink-fence-"
_UNLINK_FENCE_NAME = re.compile(r"^\.unlink-fence-[0-9a-f]{32}$")
_UNLINK_RECOVERY_PREFIX = ".unlink-recovery-"
_UNLINK_RECOVERY_NAME = re.compile(r"^\.unlink-recovery-[0-9a-f]{32}$")
_UNLINK_JOURNAL = ".journal"
_MAX_ASSET_BYTES = 1_572_864
_MAX_CACHE_FILES = 4096
_MAX_RECOVERY_ENTRIES = 8
_STALE_STAGE_SECONDS = 300
_OPEN_DIRECTORY = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
)
_OPEN_FILE = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
_PUBLIC_CODES = frozenset(
    {
        "INVALID_INPUT",
        "CACHE_ROOT_INVALID",
        "CACHE_ROOT_SYMLINK",
        "CACHE_LOCK_INVALID",
        "CACHE_LOCK_UNSUPPORTED",
        "CACHE_RECOVERY_REQUIRED",
        "CACHE_PATH_SYMLINK",
        "CACHE_SCAN_LIMIT",
        "TEMP_CREATE_FAILED",
        "TEMP_INVALID",
        "ASSET_RELPATH_INVALID",
        "ASSET_MISSING",
        "ASSET_SYMLINK",
        "ASSET_NOT_REGULAR",
        "ASSET_TOO_LARGE",
        "ASSET_HASH_MISMATCH",
        "ASSET_BUSY",
        "ASSET_IO_FAILED",
        "TOMBSTONE_INVALID",
    }
)

_PROCESS_MUTATION_LOCK = threading.Lock()
_PROCESS_MUTATION_GUARDS: weakref.WeakValueDictionary[
    tuple[int, int, int, int], Any
] = weakref.WeakValueDictionary()
_MUTATION_STATE = threading.local()
_HAS_DESCRIPTOR_RELATIVE_PRIMITIVES = (
    bool(getattr(os, "O_NOFOLLOW", None))
    and bool(getattr(os, "O_DIRECTORY", None))
    and all(
        operation in os.supports_dir_fd
        for operation in (
            os.open,
            os.mkdir,
            os.link,
            os.rename,
            os.rmdir,
            os.stat,
            os.unlink,
        )
    )
    and os.link in os.supports_follow_symlinks
)


@dataclass(slots=True)
class _HeldMutation:
    root_fd: int
    lock_fd: int
    process_guard: Any
    depth: int = 1


class SourceVisualStorageError(ValueError):
    """Fail-closed storage error whose code never includes a filesystem path."""

    def __init__(self, code: str):
        self.code = code if code in _PUBLIC_CODES else "ASSET_IO_FAILED"
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class StagedVisualAsset:
    source_id: str
    content_sha256: str
    asset_sha256: str
    temp_name: str
    byte_size: int
    width: int
    height: int
    mime_type: str


@dataclass(frozen=True, slots=True)
class StoredVisualAsset:
    asset_relpath: str
    asset_sha256: str
    byte_size: int
    width: int
    height: int
    mime_type: str


@dataclass(frozen=True, slots=True)
class TombstonedVisualAsset:
    asset_relpath: str
    tombstone_name: str
    asset_sha256: str
    byte_size: int


def _validate_hash(value: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise SourceVisualStorageError("INVALID_INPUT")
    return value


def _validate_source_id(value: str) -> str:
    if not isinstance(value, str) or _SOURCE_ID.fullmatch(value) is None:
        raise SourceVisualStorageError("INVALID_INPUT")
    return value


def asset_relpath(source_id: str, content_sha256: str, asset_sha256: str) -> str:
    """Return the sole canonical relative path for one derived asset."""

    source_id = _validate_source_id(source_id)
    content_sha256 = _validate_hash(content_sha256)
    asset_sha256 = _validate_hash(asset_sha256)
    prefix = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:2]
    return f"{prefix}/{content_sha256}/{asset_sha256}.webp"


def _stage_identity(source_id: str, content_sha256: str, asset_sha256: str) -> str:
    return hashlib.sha256(
        f"{source_id}\0{content_sha256}\0{asset_sha256}".encode("utf-8")
    ).hexdigest()


def _hash_fd(fd: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, 64 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > _MAX_ASSET_BYTES:
            raise SourceVisualStorageError("ASSET_TOO_LARGE")
        digest.update(chunk)
    return digest.hexdigest(), size


def _safe_close(fd: int | None) -> None:
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _process_mutation_guard(
    root_stat: os.stat_result, lock_stat: os.stat_result
) -> Any:
    key = (root_stat.st_dev, root_stat.st_ino, lock_stat.st_dev, lock_stat.st_ino)
    with _PROCESS_MUTATION_LOCK:
        return _PROCESS_MUTATION_GUARDS.setdefault(key, threading.RLock())


def _require_supported_platform() -> None:
    if (
        fcntl is None
        or not hasattr(fcntl, "flock")
        or not _HAS_DESCRIPTOR_RELATIVE_PRIMITIVES
    ):
        raise SourceVisualStorageError("CACHE_LOCK_UNSUPPORTED")


class SourceVisualStore:
    """Own derived bytes beneath ``DATA_FOLDER/source-visual-cache/v1`` only."""

    def __init__(self, *, data_folder: str | os.PathLike[str] | None = None):
        configured = Path(data_folder if data_folder is not None else DATA_FOLDER)
        self._data_folder = configured
        self._root = configured / "source-visual-cache" / "v1"
        self._active_lock = threading.RLock()
        self._active_reads: dict[str, int] = {}

    @property
    def root(self) -> Path:
        return self._root

    def _open_mutation_lock(self, root_fd: int) -> int:
        lock_fd = None
        try:
            lock_fd = os.open(
                _MUTATION_LOCK,
                os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=root_fd,
            )
            metadata = os.fstat(lock_fd)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
                or metadata.st_size != 0
            ):
                raise SourceVisualStorageError("CACHE_LOCK_INVALID")
            return lock_fd
        except SourceVisualStorageError:
            _safe_close(lock_fd)
            raise
        except OSError as exc:
            _safe_close(lock_fd)
            raise SourceVisualStorageError("CACHE_LOCK_INVALID") from exc

    @contextmanager
    def mutation_guard(self) -> Iterator[int]:
        """Serialize trusted cache mutations across threads and processes."""

        root_fd = lock_fd = None
        process_guard = None
        locked = False
        key = None
        held: _HeldMutation | None = None
        try:
            root_fd = self._ensure_root()
            lock_fd = self._open_mutation_lock(root_fd)
            root_stat = os.fstat(root_fd)
            lock_stat = os.fstat(lock_fd)
            key = (root_stat.st_dev, root_stat.st_ino, lock_stat.st_dev, lock_stat.st_ino)
            held_mutations = getattr(_MUTATION_STATE, "held", None)
            if held_mutations is None:
                held_mutations = {}
                _MUTATION_STATE.held = held_mutations
            held = held_mutations.get(key)
            if held is not None:
                _safe_close(lock_fd)
                _safe_close(root_fd)
                lock_fd = root_fd = None
                held.depth += 1
                try:
                    yield held.root_fd
                finally:
                    held.depth -= 1
                return
            process_guard = _process_mutation_guard(root_stat, lock_stat)
            process_guard.acquire()
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                locked = True
            except (AttributeError, OSError) as exc:
                raise SourceVisualStorageError("CACHE_LOCK_INVALID") from exc
            held = _HeldMutation(root_fd, lock_fd, process_guard)
            held_mutations[key] = held
            try:
                self._reconcile_recovery_at(root_fd)
                yield root_fd
            finally:
                held_mutations.pop(key, None)
        finally:
            if locked and lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            if process_guard is not None:
                process_guard.release()
            _safe_close(lock_fd)
            _safe_close(root_fd)

    def _ensure_root(self) -> int:
        data_fd = cache_fd = None
        try:
            _require_supported_platform()
            data_fd = self._open_absolute_directory(self._data_folder)
            cache_fd = self._open_child_dir(
                data_fd, "source-visual-cache", create=True
            )
            return self._open_child_dir(cache_fd, "v1", create=True)
        except SourceVisualStorageError as exc:
            if exc.code == "CACHE_PATH_SYMLINK":
                raise SourceVisualStorageError("CACHE_ROOT_SYMLINK") from None
            raise
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise SourceVisualStorageError("CACHE_ROOT_SYMLINK") from None
            raise SourceVisualStorageError("CACHE_ROOT_INVALID") from exc
        finally:
            _safe_close(cache_fd)
            _safe_close(data_fd)

    @classmethod
    def _open_absolute_directory(cls, path: Path) -> int:
        if not path.is_absolute():
            raise SourceVisualStorageError("CACHE_ROOT_INVALID")
        current_fd = os.open("/", _OPEN_DIRECTORY)
        try:
            for component in path.parts[1:]:
                child_fd = cls._open_child_dir(current_fd, component, create=True)
                _safe_close(current_fd)
                current_fd = child_fd
            return current_fd
        except Exception:
            _safe_close(current_fd)
            raise

    @staticmethod
    def _open_child_dir(parent_fd: int, name: str, *, create: bool) -> int:
        if "/" in name or name in {"", ".", ".."}:
            raise SourceVisualStorageError("ASSET_RELPATH_INVALID")
        created = False
        if create:
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent_fd)
                created = True
            except FileExistsError:
                pass
            except OSError as exc:
                raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        if created:
            try:
                os.fsync(parent_fd)
            except OSError as exc:
                raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        try:
            return os.open(name, _OPEN_DIRECTORY, dir_fd=parent_fd)
        except FileNotFoundError:
            raise SourceVisualStorageError("ASSET_MISSING") from None
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise SourceVisualStorageError("CACHE_PATH_SYMLINK") from None
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc

    def _open_asset_parent_at(
        self, root_fd: int, relpath: str, *, create: bool
    ) -> tuple[int, str]:
        match = _RELPATH.fullmatch(relpath)
        if match is None:
            raise SourceVisualStorageError("ASSET_RELPATH_INVALID")
        prefix_fd = None
        try:
            prefix_fd = self._open_child_dir(root_fd, match.group(1), create=create)
            content_fd = self._open_child_dir(prefix_fd, match.group(2), create=create)
            return content_fd, f"{match.group(3)}.webp"
        finally:
            _safe_close(prefix_fd)

    def _open_asset_parent(self, relpath: str, *, create: bool) -> tuple[int, str]:
        root_fd = self._ensure_root()
        try:
            return self._open_asset_parent_at(root_fd, relpath, create=create)
        finally:
            _safe_close(root_fd)

    def _open_temp_at(self, root_fd: int) -> int:
        temp_fd = None
        try:
            temp_fd = self._open_child_dir(root_fd, _TEMP_DIR, create=True)
            try:
                marker_fd = os.open(
                    _TEMP_MARKER,
                    os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=temp_fd,
                )
            except OSError as exc:
                raise SourceVisualStorageError("TEMP_INVALID") from exc
            try:
                metadata = os.fstat(marker_fd)
                if not stat.S_ISREG(metadata.st_mode):
                    raise SourceVisualStorageError("TEMP_INVALID")
            finally:
                os.close(marker_fd)
            return temp_fd
        except Exception:
            _safe_close(temp_fd)
            raise

    def _open_temp(self) -> tuple[int, int]:
        root_fd = self._ensure_root()
        try:
            return root_fd, self._open_temp_at(root_fd)
        except Exception:
            _safe_close(root_fd)
            raise

    @staticmethod
    def _open_regular_file(parent_fd: int, name: str) -> int:
        try:
            fd = os.open(name, _OPEN_FILE, dir_fd=parent_fd)
        except FileNotFoundError:
            raise SourceVisualStorageError("ASSET_MISSING") from None
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise SourceVisualStorageError("ASSET_SYMLINK") from None
            if exc.errno in {errno.EISDIR, errno.ENXIO, errno.ENODEV}:
                raise SourceVisualStorageError("ASSET_NOT_REGULAR") from None
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(fd)
            raise SourceVisualStorageError("ASSET_NOT_REGULAR")
        return fd

    @staticmethod
    def _validate_record(record: SourceVisualRecord) -> str:
        if not isinstance(record, SourceVisualRecord):
            raise SourceVisualStorageError("INVALID_INPUT")
        expected = asset_relpath(
            record.source_id, record.content_sha256, record.asset_sha256
        )
        if record.asset_relpath != expected:
            raise SourceVisualStorageError("ASSET_RELPATH_INVALID")
        return expected

    @staticmethod
    def _require_path_identity(
        parent_fd: int, name: str, expected_stat: os.stat_result
    ) -> None:
        try:
            current_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise SourceVisualStorageError("ASSET_HASH_MISMATCH") from exc
        if not _same_identity(current_stat, expected_stat):
            raise SourceVisualStorageError("ASSET_HASH_MISMATCH")

    @staticmethod
    def _is_owned_mutation_name(name: str) -> bool:
        return (
            _TEMP_NAME.fullmatch(name) is not None
            or _UNVERIFIED_STAGE_NAME.fullmatch(name) is not None
            or TOMBSTONE.fullmatch(name) is not None
            or _UNLINK_RECOVERY_NAME.fullmatch(name) is not None
            or re.fullmatch(r"[0-9a-f]{64}\.webp", name) is not None
        )

    def _write_fence_journal(
        self, fence_fd: int, name: str, expected_stat: os.stat_result
    ) -> None:
        if not self._is_owned_mutation_name(name):
            raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")
        payload = json.dumps(
            {
                "dev": expected_stat.st_dev,
                "ino": expected_stat.st_ino,
                "name": name,
                "operation": "unlink",
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        journal_fd = None
        try:
            journal_fd = os.open(
                _UNLINK_JOURNAL,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=fence_fd,
            )
            with os.fdopen(os.dup(journal_fd), "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
            os.fsync(journal_fd)
            os.fsync(fence_fd)
        except OSError as exc:
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        finally:
            _safe_close(journal_fd)

    def _read_fence_journal(self, fence_fd: int) -> tuple[str, int, int]:
        journal_fd = None
        try:
            journal_fd = self._open_regular_file(fence_fd, _UNLINK_JOURNAL)
            journal_stat = os.fstat(journal_fd)
            if journal_stat.st_size > 512:
                raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")
            payload = os.read(journal_fd, 513)
        except SourceVisualStorageError as exc:
            raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED") from exc
        except OSError as exc:
            raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED") from exc
        finally:
            _safe_close(journal_fd)
        try:
            value = json.loads(payload.decode("ascii"))
            name = value["name"]
            dev = value["dev"]
            ino = value["ino"]
            if (
                set(value) != {"dev", "ino", "name", "operation"}
                or value["operation"] != "unlink"
                or not isinstance(name, str)
                or not self._is_owned_mutation_name(name)
                or isinstance(dev, bool)
                or not isinstance(dev, int)
                or dev < 0
                or isinstance(ino, bool)
                or not isinstance(ino, int)
                or ino < 0
            ):
                raise ValueError
        except (UnicodeDecodeError, ValueError, KeyError, TypeError):
            raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED") from None
        return name, dev, ino

    @staticmethod
    def _retire_fence_at(
        parent_fd: int, fence_name: str, fence_fd: int, name: str, *, moved_present: bool
    ) -> None:
        if moved_present:
            os.unlink(name, dir_fd=fence_fd)
            os.fsync(fence_fd)
        os.unlink(_UNLINK_JOURNAL, dir_fd=fence_fd)
        os.fsync(fence_fd)
        os.close(fence_fd)
        os.rmdir(fence_name, dir_fd=parent_fd)
        os.fsync(parent_fd)

    def _retire_empty_fence_at(
        self, parent_fd: int, fence_name: str, fence_fd: int, visited: list[int]
    ) -> None:
        """Retire only an exact private fence proven empty immediately before rmdir."""

        if self._fence_entry_names(fence_fd, visited):
            raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")
        os.close(fence_fd)
        try:
            os.rmdir(fence_name, dir_fd=parent_fd)
        except OSError as exc:
            raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED") from exc
        os.fsync(parent_fd)

    def _reconcile_fence_at(
        self,
        parent_fd: int,
        fence_name: str,
        recovery_count: list[int],
        visited: list[int] | None = None,
    ) -> bool:
        if _UNLINK_FENCE_NAME.fullmatch(fence_name) is None:
            raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")
        fence_fd = moved_fd = None
        try:
            fence_fd = self._open_child_dir(parent_fd, fence_name, create=False)
            fence_entries = self._fence_entry_names(
                fence_fd, [0] if visited is None else visited
            )
            if not fence_entries:
                self._retire_empty_fence_at(
                    parent_fd, fence_name, fence_fd, [0] if visited is None else visited
                )
                fence_fd = None
                return True
            name, expected_dev, expected_ino = self._read_fence_journal(fence_fd)
            if fence_entries not in ({_UNLINK_JOURNAL}, {_UNLINK_JOURNAL, name}):
                raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")
            try:
                moved_fd = self._open_regular_file(fence_fd, name)
            except SourceVisualStorageError as exc:
                if exc.code != "ASSET_MISSING":
                    raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED") from exc
                self._retire_fence_at(
                    parent_fd, fence_name, fence_fd, name, moved_present=False
                )
                fence_fd = None
                return True
            moved_stat = os.fstat(moved_fd)
            if (moved_stat.st_dev, moved_stat.st_ino) == (expected_dev, expected_ino):
                _safe_close(moved_fd)
                moved_fd = None
                self._retire_fence_at(
                    parent_fd, fence_name, fence_fd, name, moved_present=True
                )
                fence_fd = None
                return True

            destination_name = name
            try:
                os.link(
                    name,
                    destination_name,
                    src_dir_fd=fence_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                existing_fd = None
                try:
                    existing_fd = self._open_regular_file(parent_fd, destination_name)
                    already_recovered = _same_identity(
                        os.fstat(existing_fd), moved_stat
                    )
                except SourceVisualStorageError as exc:
                    raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED") from exc
                finally:
                    _safe_close(existing_fd)
                if not already_recovered:
                    if recovery_count[0] >= _MAX_RECOVERY_ENTRIES:
                        raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")
                    destination_name = (
                        f"{_UNLINK_RECOVERY_PREFIX}{secrets.token_hex(16)[:32]}"
                    )
                    try:
                        os.link(
                            name,
                            destination_name,
                            src_dir_fd=fence_fd,
                            dst_dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                    except OSError as exc:
                        raise SourceVisualStorageError(
                            "CACHE_RECOVERY_REQUIRED"
                        ) from exc
                    recovery_count[0] += 1
            except OSError as exc:
                raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED") from exc

            destination_fd = None
            try:
                destination_fd = self._open_regular_file(parent_fd, destination_name)
                if not _same_identity(os.fstat(destination_fd), moved_stat):
                    raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")
            finally:
                _safe_close(destination_fd)
            os.fsync(parent_fd)
            _safe_close(moved_fd)
            moved_fd = None
            self._retire_fence_at(
                parent_fd, fence_name, fence_fd, name, moved_present=True
            )
            fence_fd = None
            return False
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED") from exc
        finally:
            _safe_close(moved_fd)
            _safe_close(fence_fd)

    def _unlink_verified(
        self, parent_fd: int, name: str, expected_stat: os.stat_result
    ) -> None:
        """Journal then move a name into a private fence before deletion.

        Once the public name is atomically moved, the random 0700 fence plus the
        held mutation lock is the trusted serialization boundary. Same-UID actors
        bypassing that advisory boundary can alter the entire cache and are out of
        this controlled-cache threat model.
        """

        fence_fd = None
        fence_name = f"{_UNLINK_FENCE_PREFIX}{secrets.token_hex(16)[:32]}"
        try:
            os.mkdir(fence_name, mode=0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
            fence_fd = os.open(fence_name, _OPEN_DIRECTORY, dir_fd=parent_fd)
            self._write_fence_journal(fence_fd, name, expected_stat)
            os.rename(name, name, src_dir_fd=parent_fd, dst_dir_fd=fence_fd)
            os.fsync(parent_fd)
            os.fsync(fence_fd)
            _safe_close(fence_fd)
            fence_fd = None
            if not self._reconcile_fence_at(parent_fd, fence_name, [0]):
                raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
        except SourceVisualStorageError:
            _safe_close(fence_fd)
            fence_fd = None
            try:
                self._reconcile_fence_at(parent_fd, fence_name, [0])
            except SourceVisualStorageError:
                pass
            raise
        except OSError as exc:
            _safe_close(fence_fd)
            fence_fd = None
            try:
                self._reconcile_fence_at(parent_fd, fence_name, [0])
            except SourceVisualStorageError:
                pass
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        finally:
            _safe_close(fence_fd)

    def _validate_pending_file(self, parent_fd: int, name: str) -> None:
        pending_fd = None
        try:
            pending_fd = self._open_regular_file(parent_fd, name)
        except SourceVisualStorageError as exc:
            raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED") from exc
        finally:
            _safe_close(pending_fd)

    @staticmethod
    def _iter_bounded_entries(
        parent_fd: int, visited: list[int], *, error_code: str
    ) -> Iterator[os.DirEntry[str]]:
        try:
            with os.scandir(parent_fd) as entries:
                for entry in entries:
                    visited[0] += 1
                    if visited[0] > _MAX_CACHE_FILES:
                        raise SourceVisualStorageError("CACHE_SCAN_LIMIT")
                    yield entry
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            raise SourceVisualStorageError(error_code) from exc

    def _fence_entry_names(self, fence_fd: int, visited: list[int]) -> set[str]:
        return {
            entry.name
            for entry in self._iter_bounded_entries(
                fence_fd, visited, error_code="CACHE_RECOVERY_REQUIRED"
            )
        }

    def _collect_parent_recovery(
        self,
        parent_fd: int,
        *,
        temp_parent: bool,
        recovery_count: list[int],
        unverified_count: list[int],
        fences: list[tuple[str | None, str | None, str]],
        prefix: str | None,
        content: str | None,
        visited: list[int],
    ) -> None:
        for entry in self._iter_bounded_entries(
            parent_fd, visited, error_code="CACHE_RECOVERY_REQUIRED"
        ):
            if entry.name.startswith(_UNLINK_FENCE_PREFIX):
                if _UNLINK_FENCE_NAME.fullmatch(entry.name) is None:
                    raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")
                fences.append((prefix, content, entry.name))
                continue
            if entry.name.startswith(_UNLINK_RECOVERY_PREFIX):
                if _UNLINK_RECOVERY_NAME.fullmatch(entry.name) is None:
                    raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")
                self._validate_pending_file(parent_fd, entry.name)
                recovery_count[0] += 1
                continue
            if temp_parent and _UNVERIFIED_STAGE_NAME.fullmatch(entry.name) is not None:
                self._validate_pending_file(parent_fd, entry.name)
                unverified_count[0] += 1

    def _reconcile_recovery_at(self, root_fd: int) -> None:
        """Bound and retire durable unlink journals while the mutation lock is held."""

        recovery_count = [0]
        unverified_count = [0]
        fences: list[tuple[str | None, str | None, str]] = []
        visited = [0]
        temp_fd = None
        try:
            temp_fd = self._open_temp_at(root_fd)
            self._collect_parent_recovery(
                temp_fd,
                temp_parent=True,
                recovery_count=recovery_count,
                unverified_count=unverified_count,
                fences=fences,
                prefix=None,
                content=None,
                visited=visited,
            )
            for prefix_entry in self._iter_bounded_entries(
                root_fd, visited, error_code="CACHE_RECOVERY_REQUIRED"
            ):
                if re.fullmatch(r"[0-9a-f]{2}", prefix_entry.name) is None:
                    continue
                prefix_fd = self._open_child_dir(root_fd, prefix_entry.name, create=False)
                try:
                    for content_entry in self._iter_bounded_entries(
                        prefix_fd, visited, error_code="CACHE_RECOVERY_REQUIRED"
                    ):
                        if _SHA256.fullmatch(content_entry.name) is None:
                            continue
                        content_fd = self._open_child_dir(
                            prefix_fd, content_entry.name, create=False
                        )
                        try:
                            self._collect_parent_recovery(
                                content_fd,
                                temp_parent=False,
                                recovery_count=recovery_count,
                                unverified_count=unverified_count,
                                fences=fences,
                                prefix=prefix_entry.name,
                                content=content_entry.name,
                                visited=visited,
                            )
                        finally:
                            _safe_close(content_fd)
                finally:
                    _safe_close(prefix_fd)
            if (
                recovery_count[0] >= _MAX_RECOVERY_ENTRIES
                or len(fences) > _MAX_RECOVERY_ENTRIES
                or unverified_count[0] > 1
            ):
                raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")

            for prefix, content, fence_name in fences:
                parent_fd = prefix_fd = content_fd = None
                try:
                    if prefix is None:
                        parent_fd = self._open_temp_at(root_fd)
                    else:
                        prefix_fd = self._open_child_dir(root_fd, prefix, create=False)
                        content_fd = self._open_child_dir(
                            prefix_fd, content or "", create=False
                        )
                        parent_fd = content_fd
                    self._reconcile_fence_at(
                        parent_fd, fence_name, recovery_count, visited
                    )
                finally:
                    if parent_fd is not content_fd:
                        _safe_close(parent_fd)
                    _safe_close(content_fd)
                    _safe_close(prefix_fd)
        finally:
            _safe_close(temp_fd)

    def _require_no_unverified_stage(self, temp_fd: int) -> None:
        count = 0
        visited = [0]
        for entry in self._iter_bounded_entries(
            temp_fd, visited, error_code="CACHE_RECOVERY_REQUIRED"
        ):
            if _UNVERIFIED_STAGE_NAME.fullmatch(entry.name) is None:
                continue
            self._validate_pending_file(temp_fd, entry.name)
            count += 1
        if count:
            raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")

    def _discard_staged_file_at(
        self, parent_fd: int, name: str, expected_stat: os.stat_result
    ) -> bool:
        """Remove only a still-identical failed staging inode while guarded."""

        try:
            self._unlink_verified(parent_fd, name, expected_stat)
            os.fsync(parent_fd)
        except SourceVisualStorageError:
            return False
        return True

    def _verify_linked_bytes(
        self,
        parent_fd: int,
        name: str,
        expected_stat: os.stat_result,
        expected_hash: str,
        expected_size: int,
    ) -> None:
        """Confirm a linked name still denotes the verified bytes."""

        file_fd = None
        try:
            file_fd = self._open_regular_file(parent_fd, name)
            current_stat = os.fstat(file_fd)
            current_hash, current_size = _hash_fd(file_fd)
        finally:
            _safe_close(file_fd)
        if (
            not _same_identity(current_stat, expected_stat)
            or current_hash != expected_hash
            or current_size != expected_size
        ):
            raise SourceVisualStorageError("ASSET_HASH_MISMATCH")

    @staticmethod
    def _new_tombstone_name(asset_sha256: str) -> str:
        return f".expired-{secrets.token_hex(8)}-{asset_sha256}.webp"

    def _link_no_replace(
        self,
        *,
        source_parent_fd: int,
        source_name: str,
        source_stat: os.stat_result,
        destination_parent_fd: int,
        destination_name: str,
        expected_hash: str,
        expected_size: int,
        discard_mismatched_destination: bool = False,
    ) -> os.stat_result | None:
        """Hard-link a verified inode without replacing a destination pathname."""

        try:
            os.link(
                source_name,
                destination_name,
                src_dir_fd=source_parent_fd,
                dst_dir_fd=destination_parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            return None
        except OSError as exc:
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc

        destination_fd = None
        try:
            destination_fd = self._open_regular_file(
                destination_parent_fd, destination_name
            )
            destination_stat = os.fstat(destination_fd)
            destination_hash, destination_size = _hash_fd(destination_fd)
        finally:
            _safe_close(destination_fd)
        if (
            _same_identity(destination_stat, source_stat)
            and destination_hash == expected_hash
            and destination_size == expected_size
        ):
            try:
                os.fsync(destination_parent_fd)
            except OSError as exc:
                raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
            return destination_stat

        if discard_mismatched_destination:
            try:
                self._unlink_verified(
                    destination_parent_fd, destination_name, destination_stat
                )
            except SourceVisualStorageError:
                pass
        raise SourceVisualStorageError("ASSET_HASH_MISMATCH")

    def stage(
        self,
        source_id: str,
        content_sha256: str,
        prepared: PreparedVisualAsset,
    ) -> StagedVisualAsset:
        source_id = _validate_source_id(source_id)
        content_sha256 = _validate_hash(content_sha256)
        if not isinstance(prepared, PreparedVisualAsset):
            raise SourceVisualStorageError("INVALID_INPUT")
        if hashlib.sha256(prepared.encoded_bytes).hexdigest() != prepared.asset_sha256:
            raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
        temp_fd = file_fd = verify_fd = None
        temp_stat = None
        temp_name = (
            f"stage-{_stage_identity(source_id, content_sha256, prepared.asset_sha256)}-"
            f"{secrets.token_hex(32)}.tmp"
        )
        unverified_name = f".unverified-{temp_name}"
        try:
            with self.mutation_guard() as root_fd:
                temp_fd = self._open_temp_at(root_fd)
                self._require_no_unverified_stage(temp_fd)
                try:
                    file_fd = os.open(
                        unverified_name,
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                        dir_fd=temp_fd,
                    )
                    temp_stat = os.fstat(file_fd)
                except OSError as exc:
                    # This pathname was only protected by O_EXCL, not an inode
                    # identity.  Leaving it outside the recognised staging
                    # namespace prevents a later stale sweep from deleting a
                    # replacement that raced the initial fstat.
                    raise SourceVisualStorageError("TEMP_CREATE_FAILED") from exc
                try:
                    try:
                        os.link(
                            unverified_name,
                            temp_name,
                            src_dir_fd=temp_fd,
                            dst_dir_fd=temp_fd,
                            follow_symlinks=False,
                        )
                    except OSError as exc:
                        raise SourceVisualStorageError("TEMP_CREATE_FAILED") from exc
                    verify_fd = self._open_regular_file(temp_fd, temp_name)
                    staged_stat = os.fstat(verify_fd)
                    _safe_close(verify_fd)
                    verify_fd = None
                    if not _same_identity(staged_stat, temp_stat):
                        self._discard_staged_file_at(temp_fd, temp_name, staged_stat)
                        raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
                    os.fsync(temp_fd)
                    self._unlink_verified(temp_fd, unverified_name, temp_stat)
                    view = memoryview(prepared.encoded_bytes)
                    while view:
                        written = os.write(file_fd, view)
                        if written <= 0:
                            raise SourceVisualStorageError("ASSET_IO_FAILED")
                        view = view[written:]
                    os.fsync(file_fd)
                    os.close(file_fd)
                    file_fd = None
                    verify_fd = self._open_regular_file(temp_fd, temp_name)
                    digest, size = _hash_fd(verify_fd)
                    if digest != prepared.asset_sha256:
                        raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
                    return StagedVisualAsset(
                        source_id=source_id,
                        content_sha256=content_sha256,
                        asset_sha256=prepared.asset_sha256,
                        temp_name=temp_name,
                        byte_size=size,
                        width=prepared.width,
                        height=prepared.height,
                        mime_type=prepared.mime_type,
                    )
                except SourceVisualStorageError:
                    self._discard_staged_file_at(temp_fd, temp_name, temp_stat)
                    raise
                except OSError as exc:
                    self._discard_staged_file_at(temp_fd, temp_name, temp_stat)
                    raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        finally:
            _safe_close(verify_fd)
            _safe_close(file_fd)
            _safe_close(temp_fd)

    def reconcile_staged_files(
        self,
        *,
        limit: int = 100,
        now: float | None = None,
    ) -> int:
        """Remove a bounded set of old, exact task-owned staging files."""

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
            or (now is not None and (isinstance(now, bool) or not isinstance(now, float)))
        ):
            raise SourceVisualStorageError("INVALID_INPUT")
        current_time = time.time() if now is None else now
        temp_fd = None
        removed = visited = 0
        try:
            with self.mutation_guard() as root_fd:
                temp_fd = self._open_temp_at(root_fd)
                with os.scandir(temp_fd) as entries:
                    for entry in entries:
                        visited += 1
                        if visited > _MAX_CACHE_FILES:
                            raise SourceVisualStorageError("CACHE_SCAN_LIMIT")
                        if _TEMP_NAME.fullmatch(entry.name) is None:
                            continue
                        try:
                            stage_fd = self._open_regular_file(temp_fd, entry.name)
                        except SourceVisualStorageError as exc:
                            if exc.code in {"ASSET_SYMLINK", "ASSET_NOT_REGULAR"}:
                                raise SourceVisualStorageError("TEMP_INVALID") from exc
                            raise
                        try:
                            stage_stat = os.fstat(stage_fd)
                        finally:
                            _safe_close(stage_fd)
                        if current_time - stage_stat.st_mtime < _STALE_STAGE_SECONDS:
                            continue
                        if self._discard_staged_file_at(
                            temp_fd, entry.name, stage_stat
                        ):
                            removed += 1
                        if removed >= limit:
                            break
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        finally:
            _safe_close(temp_fd)
        return removed

    def publish(self, staged: StagedVisualAsset) -> StoredVisualAsset:
        if not isinstance(staged, StagedVisualAsset):
            raise SourceVisualStorageError("TEMP_INVALID")
        temp_identity = _TEMP_NAME.fullmatch(staged.temp_name)
        expected_identity = _stage_identity(
            staged.source_id, staged.content_sha256, staged.asset_sha256
        )
        if temp_identity is None or temp_identity.group(1) != expected_identity:
            raise SourceVisualStorageError("TEMP_INVALID")
        relpath = asset_relpath(
            staged.source_id, staged.content_sha256, staged.asset_sha256
        )
        temp_fd = parent_fd = verify_fd = None
        try:
            with self.mutation_guard() as root_fd:
                temp_fd = self._open_temp_at(root_fd)
                verify_fd = self._open_regular_file(temp_fd, staged.temp_name)
                verified_stat = os.fstat(verify_fd)
                digest, size = _hash_fd(verify_fd)
                if digest != staged.asset_sha256 or size != staged.byte_size:
                    raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
                parent_fd, filename = self._open_asset_parent_at(
                    root_fd, relpath, create=True
                )
                destination_stat = self._link_no_replace(
                    source_parent_fd=temp_fd,
                    source_name=staged.temp_name,
                    source_stat=verified_stat,
                    destination_parent_fd=parent_fd,
                    destination_name=filename,
                    expected_hash=staged.asset_sha256,
                    expected_size=staged.byte_size,
                    discard_mismatched_destination=True,
                )
                installed_here = destination_stat is not None
                if destination_stat is None:
                    existing_fd = self._open_regular_file(parent_fd, filename)
                    try:
                        existing_stat = os.fstat(existing_fd)
                        existing_hash, existing_size = _hash_fd(existing_fd)
                    finally:
                        _safe_close(existing_fd)
                    self._require_path_identity(parent_fd, filename, existing_stat)
                    if (
                        existing_hash != staged.asset_sha256
                        or existing_size != staged.byte_size
                    ):
                        raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
                    destination_stat = existing_stat
                self._unlink_verified(temp_fd, staged.temp_name, verified_stat)
                destination_fd = self._open_regular_file(parent_fd, filename)
                try:
                    final_stat = os.fstat(destination_fd)
                    final_hash, final_size = _hash_fd(destination_fd)
                finally:
                    _safe_close(destination_fd)
                self._require_path_identity(parent_fd, filename, final_stat)
                if (
                    not _same_identity(final_stat, destination_stat)
                    or final_hash != staged.asset_sha256
                    or final_size != staged.byte_size
                ):
                    if installed_here and _same_identity(final_stat, destination_stat):
                        self._discard_staged_file_at(parent_fd, filename, final_stat)
                    raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
                os.fsync(parent_fd)
                os.fsync(temp_fd)
                return StoredVisualAsset(
                    relpath,
                    staged.asset_sha256,
                    size,
                    staged.width,
                    staged.height,
                    staged.mime_type,
                )
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        finally:
            _safe_close(verify_fd)
            _safe_close(parent_fd)
            _safe_close(temp_fd)

    def read_exact(self, record: SourceVisualRecord) -> bytes:
        relpath = self._validate_record(record)
        parent_fd = file_fd = None
        with self.mutation_guard() as root_fd:
            with self._active_lock:
                self._active_reads[relpath] = self._active_reads.get(relpath, 0) + 1
            try:
                parent_fd, filename = self._open_asset_parent_at(
                    root_fd, relpath, create=False
                )
                file_fd = self._open_regular_file(parent_fd, filename)
                digest = hashlib.sha256()
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = os.read(file_fd, 64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_ASSET_BYTES:
                        raise SourceVisualStorageError("ASSET_TOO_LARGE")
                    digest.update(chunk)
                    chunks.append(chunk)
                if digest.hexdigest() != record.asset_sha256:
                    raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
                return b"".join(chunks)
            finally:
                _safe_close(file_fd)
                _safe_close(parent_fd)
                with self._active_lock:
                    remaining = self._active_reads.get(relpath, 1) - 1
                    if remaining > 0:
                        self._active_reads[relpath] = remaining
                    else:
                        self._active_reads.pop(relpath, None)

    def is_read_active(self, record: SourceVisualRecord) -> bool:
        relpath = self._validate_record(record)
        with self._active_lock:
            return self._active_reads.get(relpath, 0) > 0

    def tombstone(self, record: SourceVisualRecord) -> TombstonedVisualAsset | None:
        relpath = self._validate_record(record)
        # Preserve the immediate same-instance busy signal without holding this
        # lock while waiting for the cross-instance mutation guard.
        if self.is_read_active(record):
            raise SourceVisualStorageError("ASSET_BUSY")
        parent_fd = file_fd = None
        try:
            with self.mutation_guard() as root_fd:
                with self._active_lock:
                    if self._active_reads.get(relpath, 0):
                        raise SourceVisualStorageError("ASSET_BUSY")
                parent_fd, filename = self._open_asset_parent_at(
                    root_fd, relpath, create=False
                )
                try:
                    file_fd = self._open_regular_file(parent_fd, filename)
                except SourceVisualStorageError as exc:
                    if exc.code == "ASSET_MISSING":
                        return None
                    raise
                verified_stat = os.fstat(file_fd)
                digest, size = _hash_fd(file_fd)
                if digest != record.asset_sha256:
                    raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
                tombstone_name = self._new_tombstone_name(record.asset_sha256)
                tombstone_stat = self._link_no_replace(
                    source_parent_fd=parent_fd,
                    source_name=filename,
                    source_stat=verified_stat,
                    destination_parent_fd=parent_fd,
                    destination_name=tombstone_name,
                    expected_hash=record.asset_sha256,
                    expected_size=size,
                )
                if tombstone_stat is None:
                    raise SourceVisualStorageError("TOMBSTONE_INVALID")
                self._unlink_verified(parent_fd, filename, verified_stat)
                self._verify_linked_bytes(
                    parent_fd,
                    tombstone_name,
                    tombstone_stat,
                    record.asset_sha256,
                    size,
                )
                os.fsync(parent_fd)
                return TombstonedVisualAsset(
                    relpath, tombstone_name, record.asset_sha256, size
                )
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        finally:
            _safe_close(file_fd)
            _safe_close(parent_fd)

    @staticmethod
    def _validate_tombstone(value: TombstonedVisualAsset) -> None:
        if not isinstance(value, TombstonedVisualAsset):
            raise SourceVisualStorageError("TOMBSTONE_INVALID")
        match = TOMBSTONE.fullmatch(value.tombstone_name)
        relpath = _RELPATH.fullmatch(value.asset_relpath)
        if match is None or relpath is None or match.group(2) != value.asset_sha256:
            raise SourceVisualStorageError("TOMBSTONE_INVALID")
        if relpath.group(3) != value.asset_sha256:
            raise SourceVisualStorageError("TOMBSTONE_INVALID")

    def restore_tombstone(self, tombstone: TombstonedVisualAsset) -> None:
        self._validate_tombstone(tombstone)
        parent_fd = tombstone_fd = None
        try:
            with self.mutation_guard() as root_fd:
                parent_fd, filename = self._open_asset_parent_at(
                    root_fd, tombstone.asset_relpath, create=False
                )
                tombstone_fd = self._open_regular_file(
                    parent_fd, tombstone.tombstone_name
                )
                tombstone_stat = os.fstat(tombstone_fd)
                digest, size = _hash_fd(tombstone_fd)
                if digest != tombstone.asset_sha256 or size != tombstone.byte_size:
                    raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
                destination_stat = self._link_no_replace(
                    source_parent_fd=parent_fd,
                    source_name=tombstone.tombstone_name,
                    source_stat=tombstone_stat,
                    destination_parent_fd=parent_fd,
                    destination_name=filename,
                    expected_hash=tombstone.asset_sha256,
                    expected_size=tombstone.byte_size,
                )
                if destination_stat is None:
                    raise SourceVisualStorageError("TOMBSTONE_INVALID")
                self._unlink_verified(
                    parent_fd, tombstone.tombstone_name, tombstone_stat
                )
                self._verify_linked_bytes(
                    parent_fd,
                    filename,
                    destination_stat,
                    tombstone.asset_sha256,
                    tombstone.byte_size,
                )
                os.fsync(parent_fd)
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        finally:
            _safe_close(tombstone_fd)
            _safe_close(parent_fd)

    def remove_tombstone(self, tombstone: TombstonedVisualAsset) -> None:
        self._validate_tombstone(tombstone)
        parent_fd = tombstone_fd = None
        try:
            with self.mutation_guard() as root_fd:
                parent_fd, _filename = self._open_asset_parent_at(
                    root_fd, tombstone.asset_relpath, create=False
                )
                tombstone_fd = self._open_regular_file(
                    parent_fd, tombstone.tombstone_name
                )
                tombstone_stat = os.fstat(tombstone_fd)
                digest, size = _hash_fd(tombstone_fd)
                if digest != tombstone.asset_sha256 or size != tombstone.byte_size:
                    raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
                quarantine_name = self._new_tombstone_name(tombstone.asset_sha256)
                quarantine_stat = self._link_no_replace(
                    source_parent_fd=parent_fd,
                    source_name=tombstone.tombstone_name,
                    source_stat=tombstone_stat,
                    destination_parent_fd=parent_fd,
                    destination_name=quarantine_name,
                    expected_hash=tombstone.asset_sha256,
                    expected_size=tombstone.byte_size,
                )
                if quarantine_stat is None:
                    raise SourceVisualStorageError("TOMBSTONE_INVALID")
                self._unlink_verified(
                    parent_fd, tombstone.tombstone_name, tombstone_stat
                )
                self._verify_linked_bytes(
                    parent_fd,
                    quarantine_name,
                    quarantine_stat,
                    tombstone.asset_sha256,
                    tombstone.byte_size,
                )
                self._unlink_verified(parent_fd, quarantine_name, quarantine_stat)
                os.fsync(parent_fd)
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        finally:
            _safe_close(tombstone_fd)
            _safe_close(parent_fd)

    def remove_replaced_tombstone(self, tombstone: TombstonedVisualAsset) -> None:
        """Drop a duplicate tombstone only while its canonical replacement stays valid."""

        self._validate_tombstone(tombstone)
        parent_fd = tombstone_fd = canonical_fd = None
        try:
            with self.mutation_guard() as root_fd:
                parent_fd, filename = self._open_asset_parent_at(
                    root_fd, tombstone.asset_relpath, create=False
                )
                tombstone_fd = self._open_regular_file(
                    parent_fd, tombstone.tombstone_name
                )
                tombstone_stat = os.fstat(tombstone_fd)
                tombstone_hash, tombstone_size = _hash_fd(tombstone_fd)
                if (
                    tombstone_hash != tombstone.asset_sha256
                    or tombstone_size != tombstone.byte_size
                ):
                    raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
                canonical_fd = self._open_regular_file(parent_fd, filename)
                canonical_stat = os.fstat(canonical_fd)
                canonical_hash, canonical_size = _hash_fd(canonical_fd)
                if (
                    canonical_hash != tombstone.asset_sha256
                    or canonical_size != tombstone.byte_size
                ):
                    raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
                self._require_path_identity(parent_fd, filename, canonical_stat)
                self._unlink_verified(
                    parent_fd, tombstone.tombstone_name, tombstone_stat
                )
                os.fsync(parent_fd)
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        finally:
            _safe_close(canonical_fd)
            _safe_close(tombstone_fd)
            _safe_close(parent_fd)

    def list_tombstones(self, *, limit: int = 100) -> tuple[TombstonedVisualAsset, ...]:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise SourceVisualStorageError("INVALID_INPUT")
        root_fd = self._ensure_root()
        found: list[TombstonedVisualAsset] = []
        visited = 0
        try:
            with os.scandir(root_fd) as prefixes:
                for prefix in prefixes:
                    visited += 1
                    if visited > 4096:
                        raise SourceVisualStorageError("CACHE_SCAN_LIMIT")
                    if re.fullmatch(r"[0-9a-f]{2}", prefix.name) is None:
                        continue
                    prefix_fd = self._open_child_dir(root_fd, prefix.name, create=False)
                    try:
                        with os.scandir(prefix_fd) as contents:
                            for content in contents:
                                visited += 1
                                if visited > 4096:
                                    raise SourceVisualStorageError("CACHE_SCAN_LIMIT")
                                if _SHA256.fullmatch(content.name) is None:
                                    continue
                                content_fd = self._open_child_dir(
                                    prefix_fd, content.name, create=False
                                )
                                try:
                                    with os.scandir(content_fd) as entries:
                                        for entry in entries:
                                            visited += 1
                                            if visited > 4096:
                                                raise SourceVisualStorageError(
                                                    "CACHE_SCAN_LIMIT"
                                                )
                                            match = TOMBSTONE.fullmatch(entry.name)
                                            if match is None:
                                                continue
                                            try:
                                                tombstone_fd = self._open_regular_file(
                                                    content_fd, entry.name
                                                )
                                            except SourceVisualStorageError as exc:
                                                if exc.code in {
                                                    "ASSET_SYMLINK",
                                                    "ASSET_NOT_REGULAR",
                                                }:
                                                    raise SourceVisualStorageError(
                                                        "TOMBSTONE_INVALID"
                                                    ) from exc
                                                raise
                                            try:
                                                size = os.fstat(tombstone_fd).st_size
                                            finally:
                                                os.close(tombstone_fd)
                                            found.append(
                                                TombstonedVisualAsset(
                                                    f"{prefix.name}/{content.name}/{match.group(2)}.webp",
                                                    entry.name,
                                                    match.group(2),
                                                    size,
                                                )
                                            )
                                            if len(found) >= limit:
                                                return tuple(found)
                                finally:
                                    os.close(content_fd)
                    finally:
                        os.close(prefix_fd)
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        finally:
            _safe_close(root_fd)
        return tuple(found)

    def cache_size_bytes(self) -> int:
        root_fd = self._ensure_root()
        total = 0
        visited = 0
        seen_inodes: set[tuple[int, int]] = set()

        def add_owned_file(parent_fd: int, name: str, *, invalid_code: str) -> None:
            nonlocal total
            try:
                asset_fd = self._open_regular_file(parent_fd, name)
            except SourceVisualStorageError as exc:
                if exc.code in {"ASSET_SYMLINK", "ASSET_NOT_REGULAR"}:
                    raise SourceVisualStorageError(invalid_code) from exc
                raise
            try:
                metadata = os.fstat(asset_fd)
            finally:
                _safe_close(asset_fd)
            identity = (metadata.st_dev, metadata.st_ino)
            if identity not in seen_inodes:
                seen_inodes.add(identity)
                total += metadata.st_size

        def add_fence_file(parent_fd: int, fence_name: str) -> None:
            nonlocal total
            fence_fd = moved_fd = None
            try:
                fence_fd = self._open_child_dir(parent_fd, fence_name, create=False)
                fence_entries = self._fence_entry_names(fence_fd, [0])
                name, _dev, _ino = self._read_fence_journal(fence_fd)
                if fence_entries not in ({_UNLINK_JOURNAL}, {_UNLINK_JOURNAL, name}):
                    raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")
                try:
                    moved_fd = self._open_regular_file(fence_fd, name)
                except SourceVisualStorageError as exc:
                    if exc.code == "ASSET_MISSING":
                        return
                    raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED") from exc
                metadata = os.fstat(moved_fd)
                identity = (metadata.st_dev, metadata.st_ino)
                if identity not in seen_inodes:
                    seen_inodes.add(identity)
                    total += metadata.st_size
            except SourceVisualStorageError:
                raise
            except OSError as exc:
                raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED") from exc
            finally:
                _safe_close(moved_fd)
                _safe_close(fence_fd)

        try:
            with os.scandir(root_fd) as prefixes:
                for prefix in prefixes:
                    visited += 1
                    if visited > _MAX_CACHE_FILES:
                        raise SourceVisualStorageError("CACHE_SCAN_LIMIT")
                    if prefix.name == _TEMP_DIR:
                        temp_fd = self._open_child_dir(
                            root_fd, _TEMP_DIR, create=False
                        )
                        try:
                            with os.scandir(temp_fd) as entries:
                                for entry in entries:
                                    visited += 1
                                    if visited > _MAX_CACHE_FILES:
                                        raise SourceVisualStorageError(
                                            "CACHE_SCAN_LIMIT"
                                        )
                                    if _TEMP_NAME.fullmatch(entry.name) is not None:
                                        add_owned_file(
                                            temp_fd,
                                            entry.name,
                                            invalid_code="TEMP_INVALID",
                                        )
                                    elif _UNVERIFIED_STAGE_NAME.fullmatch(
                                        entry.name
                                    ) is not None:
                                        add_owned_file(
                                            temp_fd,
                                            entry.name,
                                            invalid_code="CACHE_RECOVERY_REQUIRED",
                                        )
                                    elif _UNLINK_RECOVERY_NAME.fullmatch(
                                        entry.name
                                    ) is not None:
                                        add_owned_file(
                                            temp_fd,
                                            entry.name,
                                            invalid_code="CACHE_RECOVERY_REQUIRED",
                                        )
                                    elif _UNLINK_FENCE_NAME.fullmatch(entry.name) is not None:
                                        add_fence_file(temp_fd, entry.name)
                                    elif entry.name.startswith(
                                        (_UNLINK_FENCE_PREFIX, _UNLINK_RECOVERY_PREFIX)
                                    ):
                                        raise SourceVisualStorageError(
                                            "CACHE_RECOVERY_REQUIRED"
                                        )
                        finally:
                            _safe_close(temp_fd)
                        continue
                    if re.fullmatch(r"[0-9a-f]{2}", prefix.name) is None:
                        continue
                    prefix_fd = self._open_child_dir(root_fd, prefix.name, create=False)
                    try:
                        with os.scandir(prefix_fd) as contents:
                            for content in contents:
                                visited += 1
                                if visited > _MAX_CACHE_FILES:
                                    raise SourceVisualStorageError("CACHE_SCAN_LIMIT")
                                if _SHA256.fullmatch(content.name) is None:
                                    continue
                                content_fd = self._open_child_dir(
                                    prefix_fd, content.name, create=False
                                )
                                try:
                                    with os.scandir(content_fd) as entries:
                                        for entry in entries:
                                            visited += 1
                                            if visited > _MAX_CACHE_FILES:
                                                raise SourceVisualStorageError(
                                                    "CACHE_SCAN_LIMIT"
                                                )
                                            if re.fullmatch(
                                                r"[0-9a-f]{64}\.webp", entry.name
                                            ) is not None:
                                                add_owned_file(
                                                    content_fd,
                                                    entry.name,
                                                    invalid_code="ASSET_NOT_REGULAR",
                                                )
                                            elif TOMBSTONE.fullmatch(entry.name) is not None:
                                                add_owned_file(
                                                    content_fd,
                                                    entry.name,
                                                    invalid_code="TOMBSTONE_INVALID",
                                                )
                                            elif (
                                                _UNLINK_RECOVERY_NAME.fullmatch(
                                                    entry.name
                                                )
                                                is not None
                                            ):
                                                add_owned_file(
                                                    content_fd,
                                                    entry.name,
                                                    invalid_code="ASSET_NOT_REGULAR",
                                                )
                                            elif _UNLINK_FENCE_NAME.fullmatch(
                                                entry.name
                                            ) is not None:
                                                add_fence_file(content_fd, entry.name)
                                            elif entry.name.startswith(
                                                (
                                                    _UNLINK_FENCE_PREFIX,
                                                    _UNLINK_RECOVERY_PREFIX,
                                                )
                                            ):
                                                raise SourceVisualStorageError(
                                                    "CACHE_RECOVERY_REQUIRED"
                                                )
                                            else:
                                                continue
                                finally:
                                    os.close(content_fd)
                    finally:
                        os.close(prefix_fd)
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        finally:
            _safe_close(root_fd)
        return total


__all__ = [
    "SourceVisualStorageError",
    "SourceVisualStore",
    "StagedVisualAsset",
    "StoredVisualAsset",
    "TOMBSTONE",
    "TombstonedVisualAsset",
    "asset_relpath",
]
