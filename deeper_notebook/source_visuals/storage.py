"""Exact-root storage for rebuildable source-derived visual assets."""

from __future__ import annotations

import errno
import hashlib
import os
import re
import secrets
import stat
import threading
from dataclasses import dataclass
from pathlib import Path

from deeper_notebook.config import DATA_FOLDER
from deeper_notebook.source_visuals.contracts import (
    PreparedVisualAsset,
    SourceVisualRecord,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_ID = re.compile(r"^source:[A-Za-z0-9_-]+$")
_RELPATH = re.compile(r"^([0-9a-f]{2})/([0-9a-f]{64})/([0-9a-f]{64})\.webp$")
_TEMP_NAME = re.compile(r"^stage-([0-9a-f]{64})-([0-9a-f]{64})\.tmp$")
TOMBSTONE = re.compile(r"^\.expired-([0-9a-f]{16})-([0-9a-f]{64})\.webp$")
_TEMP_DIR = ".tmp"
_TEMP_MARKER = ".deeper-notebook-source-visual-cache-v1"
_MAX_ASSET_BYTES = 1_572_864
_MAX_CACHE_FILES = 4096
_OPEN_DIRECTORY = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
)
_OPEN_FILE = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
_PUBLIC_CODES = frozenset(
    {
        "INVALID_INPUT",
        "CACHE_ROOT_INVALID",
        "CACHE_ROOT_SYMLINK",
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

    @staticmethod
    def _ensure_owned_dir(path: Path, *, root: bool = False) -> None:
        try:
            if path.is_symlink():
                raise SourceVisualStorageError(
                    "CACHE_ROOT_SYMLINK" if root else "CACHE_PATH_SYMLINK"
                )
            path.mkdir(mode=0o700, parents=False, exist_ok=True)
            metadata = path.lstat()
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise SourceVisualStorageError(
                    "CACHE_ROOT_SYMLINK" if root else "CACHE_PATH_SYMLINK"
                ) from None
            raise SourceVisualStorageError("CACHE_ROOT_INVALID") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise SourceVisualStorageError(
                "CACHE_ROOT_SYMLINK" if root else "CACHE_PATH_SYMLINK"
            )
        if not stat.S_ISDIR(metadata.st_mode):
            raise SourceVisualStorageError("CACHE_ROOT_INVALID")

    def _ensure_root(self) -> int:
        try:
            if self._data_folder.is_symlink():
                raise SourceVisualStorageError("CACHE_ROOT_SYMLINK")
            self._data_folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._ensure_owned_dir(self._data_folder)
            cache_parent = self._data_folder / "source-visual-cache"
            self._ensure_owned_dir(cache_parent, root=True)
            self._ensure_owned_dir(self._root, root=True)
            return os.open(self._root, _OPEN_DIRECTORY)
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise SourceVisualStorageError("CACHE_ROOT_SYMLINK") from None
            raise SourceVisualStorageError("CACHE_ROOT_INVALID") from exc

    @staticmethod
    def _open_child_dir(parent_fd: int, name: str, *, create: bool) -> int:
        if "/" in name or name in {"", ".", ".."}:
            raise SourceVisualStorageError("ASSET_RELPATH_INVALID")
        if create:
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            except FileExistsError:
                pass
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

    def _open_asset_parent(self, relpath: str, *, create: bool) -> tuple[int, str]:
        match = _RELPATH.fullmatch(relpath)
        if match is None:
            raise SourceVisualStorageError("ASSET_RELPATH_INVALID")
        root_fd = prefix_fd = None
        try:
            root_fd = self._ensure_root()
            prefix_fd = self._open_child_dir(root_fd, match.group(1), create=create)
            content_fd = self._open_child_dir(prefix_fd, match.group(2), create=create)
            return content_fd, f"{match.group(3)}.webp"
        finally:
            _safe_close(prefix_fd)
            _safe_close(root_fd)

    def _open_temp(self) -> tuple[int, int]:
        root_fd = temp_fd = None
        try:
            root_fd = self._ensure_root()
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
            return root_fd, temp_fd
        except Exception:
            _safe_close(temp_fd)
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
        root_fd = temp_fd = file_fd = verify_fd = None
        created = False
        temp_name = (
            f"stage-{_stage_identity(source_id, content_sha256, prepared.asset_sha256)}-"
            f"{secrets.token_hex(32)}.tmp"
        )
        try:
            root_fd, temp_fd = self._open_temp()
            try:
                file_fd = os.open(
                    temp_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=temp_fd,
                )
                created = True
            except OSError as exc:
                raise SourceVisualStorageError("TEMP_CREATE_FAILED") from exc
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
        except Exception:
            if created and temp_fd is not None:
                try:
                    os.unlink(temp_name, dir_fd=temp_fd)
                except OSError:
                    pass
            raise
        finally:
            _safe_close(verify_fd)
            _safe_close(file_fd)
            _safe_close(temp_fd)
            _safe_close(root_fd)

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
        root_fd = temp_fd = parent_fd = verify_fd = None
        try:
            root_fd, temp_fd = self._open_temp()
            verify_fd = self._open_regular_file(temp_fd, staged.temp_name)
            digest, size = _hash_fd(verify_fd)
            if digest != staged.asset_sha256 or size != staged.byte_size:
                raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
            parent_fd, filename = self._open_asset_parent(relpath, create=True)
            try:
                existing_fd = self._open_regular_file(parent_fd, filename)
            except SourceVisualStorageError as exc:
                if exc.code != "ASSET_MISSING":
                    raise
            else:
                try:
                    existing_hash, existing_size = _hash_fd(existing_fd)
                finally:
                    os.close(existing_fd)
                if existing_hash == staged.asset_sha256 and existing_size == size:
                    os.unlink(staged.temp_name, dir_fd=temp_fd)
                    os.fsync(temp_fd)
                    return StoredVisualAsset(
                        relpath,
                        staged.asset_sha256,
                        size,
                        staged.width,
                        staged.height,
                        staged.mime_type,
                    )
            os.replace(
                staged.temp_name,
                filename,
                src_dir_fd=temp_fd,
                dst_dir_fd=parent_fd,
            )
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
            _safe_close(root_fd)

    def read_exact(self, record: SourceVisualRecord) -> bytes:
        relpath = self._validate_record(record)
        with self._active_lock:
            self._active_reads[relpath] = self._active_reads.get(relpath, 0) + 1
        parent_fd = file_fd = None
        try:
            parent_fd, filename = self._open_asset_parent(relpath, create=False)
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
        with self._active_lock:
            if self._active_reads.get(relpath, 0):
                raise SourceVisualStorageError("ASSET_BUSY")
            parent_fd = file_fd = None
            try:
                parent_fd, filename = self._open_asset_parent(relpath, create=False)
                try:
                    file_fd = self._open_regular_file(parent_fd, filename)
                except SourceVisualStorageError as exc:
                    if exc.code == "ASSET_MISSING":
                        return None
                    raise
                digest, size = _hash_fd(file_fd)
                if digest != record.asset_sha256:
                    raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
                tombstone_name = (
                    f".expired-{secrets.token_hex(8)}-{record.asset_sha256}.webp"
                )
                try:
                    os.stat(tombstone_name, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise SourceVisualStorageError("TOMBSTONE_INVALID")
                os.rename(
                    filename,
                    tombstone_name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
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
        parent_fd = None
        try:
            parent_fd, filename = self._open_asset_parent(
                tombstone.asset_relpath, create=False
            )
            try:
                os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise SourceVisualStorageError("TOMBSTONE_INVALID")
            tombstone_fd = self._open_regular_file(parent_fd, tombstone.tombstone_name)
            try:
                digest, size = _hash_fd(tombstone_fd)
            finally:
                os.close(tombstone_fd)
            if digest != tombstone.asset_sha256 or size != tombstone.byte_size:
                raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
            os.replace(
                tombstone.tombstone_name,
                filename,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            os.fsync(parent_fd)
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        finally:
            _safe_close(parent_fd)

    def remove_tombstone(self, tombstone: TombstonedVisualAsset) -> None:
        self._validate_tombstone(tombstone)
        parent_fd = tombstone_fd = None
        try:
            parent_fd, _filename = self._open_asset_parent(
                tombstone.asset_relpath, create=False
            )
            tombstone_fd = self._open_regular_file(parent_fd, tombstone.tombstone_name)
            digest, size = _hash_fd(tombstone_fd)
            if digest != tombstone.asset_sha256 or size != tombstone.byte_size:
                raise SourceVisualStorageError("ASSET_HASH_MISMATCH")
            os.unlink(tombstone.tombstone_name, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except SourceVisualStorageError:
            raise
        except OSError as exc:
            raise SourceVisualStorageError("ASSET_IO_FAILED") from exc
        finally:
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
                                            tombstone_fd = self._open_regular_file(
                                                content_fd, entry.name
                                            )
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
        try:
            with os.scandir(root_fd) as prefixes:
                for prefix in prefixes:
                    visited += 1
                    if visited > _MAX_CACHE_FILES:
                        raise SourceVisualStorageError("CACHE_SCAN_LIMIT")
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
                                            if (
                                                re.fullmatch(
                                                    r"[0-9a-f]{64}\.webp", entry.name
                                                )
                                                is None
                                            ):
                                                continue
                                            asset_fd = self._open_regular_file(
                                                content_fd, entry.name
                                            )
                                            try:
                                                total += os.fstat(asset_fd).st_size
                                            finally:
                                                os.close(asset_fd)
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
