"""Descriptor-safe storage for app-owned overlay Markdown.

External vaults are deliberately outside this module's authority.  Every public
path accepted here is a canonical path beneath the owned ``Daily`` or ``Notes``
directory, and every mutation is performed relative to a retained directory
descriptor on POSIX.
"""

from __future__ import annotations

import errno
import hashlib
import hmac
import os
import stat
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from deeper_notebook.overlay.paths import (
    OverlayLayout,
    OverlayPathError,
    validate_relative_path,
)

_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o600
_READ_CHUNK_BYTES = 64 * 1024
_HASH_HEX_LENGTH = 64
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class OverlayStorageError(OSError):
    """A fail-closed overlay storage boundary error with a stable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class OverlayConflictError(OverlayStorageError):
    """A create or compare-and-swap conflict."""


@dataclass(frozen=True, slots=True)
class StoredOverlayBytes:
    relative_path: str
    markdown: str
    content_hash: str
    byte_size: int
    modified_ns: int


@dataclass(frozen=True, slots=True)
class OverlaySnapshot:
    relative_snapshot: str
    content_hash: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class _OwnedDirectory:
    descriptor: int
    device: int
    inode: int

    @property
    def identity(self) -> tuple[int, int]:
        return (self.device, self.inode)


@dataclass(frozen=True, slots=True)
class _PosixLayout:
    data_root: _OwnedDirectory
    overlay_parent: _OwnedDirectory
    canonical: _OwnedDirectory
    daily: _OwnedDirectory
    notes: _OwnedDirectory
    state: _OwnedDirectory
    revisions: _OwnedDirectory
    receipts: _OwnedDirectory
    recovery: _OwnedDirectory


@dataclass(frozen=True, slots=True)
class _WindowsOwnedPath:
    path: Path
    directories: tuple[tuple[Path, tuple[int, int]], ...]


class OverlayStorage:
    """Read and atomically mutate only the application's owned Markdown."""

    def __init__(
        self,
        layout: OverlayLayout,
        *,
        max_markdown_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        if (
            isinstance(max_markdown_bytes, bool)
            or not isinstance(max_markdown_bytes, int)
            or max_markdown_bytes <= 0
        ):
            raise ValueError("max_markdown_bytes must be a positive integer")
        if not isinstance(layout, OverlayLayout):
            raise OverlayStorageError("invalid_overlay_layout")
        data_root = layout.canonical_root.parent.parent
        if (
            not data_root.is_absolute()
            or data_root.parent == data_root
            or layout != OverlayLayout.from_data_root(data_root)
        ):
            raise OverlayStorageError("invalid_overlay_layout")
        self.layout = layout
        self.max_markdown_bytes = max_markdown_bytes

    @staticmethod
    def _encode(markdown: str, maximum: int) -> bytes:
        if not isinstance(markdown, str):
            raise OverlayStorageError("overlay_invalid_markdown")
        try:
            encoded = markdown.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        except UnicodeEncodeError as error:
            raise OverlayStorageError("overlay_invalid_markdown") from error
        if len(encoded) > maximum:
            raise OverlayStorageError("overlay_file_too_large")
        return encoded

    def read(self, relative_path: str) -> StoredOverlayBytes:
        """Read one owned Markdown file through a fail-closed boundary."""
        parts = self._validated_parts(relative_path)
        if os.name == "nt":  # pragma: no cover - exercised on Windows
            return self._windows_read(relative_path, parts)
        with self._posix_layout() as opened:
            with self._posix_parent(opened, parts) as parent:
                return self._read_named(parent.descriptor, parts[-1], relative_path)

    def create(
        self,
        relative_path: str,
        markdown: str,
        *,
        operation_id: str,
    ) -> StoredOverlayBytes:
        """Create one owned Markdown file, never replacing an existing entry."""
        parts = self._validated_parts(relative_path)
        payload = self._encode(markdown, self.max_markdown_bytes)
        self._accept_opaque_operation_id(operation_id)
        if os.name == "nt":  # pragma: no cover - exercised on Windows
            return self._windows_create(relative_path, parts, payload)
        with self._posix_layout() as opened:
            with self._posix_parent(opened, parts) as parent:
                return self._create_named(
                    parent.descriptor,
                    parts[-1],
                    relative_path,
                    payload,
                )

    def replace(
        self,
        relative_path: str,
        markdown: str,
        *,
        expected_hash: str,
        revision: int,
        operation_id: str,
    ) -> StoredOverlayBytes:
        """Compare-and-swap one file after durably snapshotting prior bytes."""
        parts = self._validated_parts(relative_path)
        payload = self._encode(markdown, self.max_markdown_bytes)
        self._validate_hash(expected_hash)
        self._validate_revision(revision)
        self._accept_opaque_operation_id(operation_id)
        if os.name == "nt":  # pragma: no cover - exercised on Windows
            return self._windows_replace(
                relative_path,
                parts,
                payload,
                expected_hash,
                revision,
            )

        with self._posix_layout() as opened:
            with self._posix_parent(opened, parts) as parent:
                current, current_identity = self._read_named_with_identity(
                    parent.descriptor,
                    parts[-1],
                    relative_path,
                )
                if not hmac.compare_digest(current.content_hash, expected_hash):
                    raise OverlayConflictError("overlay_hash_conflict")

                self.snapshot(relative_path, max(revision - 1, 1), current)
                temporary_name, temporary_identity = self._write_posix_temp(
                    parent.descriptor,
                    payload,
                )
                try:
                    self._verify_named_identity(
                        parent.descriptor,
                        parts[-1],
                        current_identity,
                        changed_code="overlay_file_changed",
                    )
                    self._verify_named_identity(
                        parent.descriptor,
                        temporary_name,
                        temporary_identity,
                        changed_code="overlay_temp_changed",
                    )
                    os.replace(
                        temporary_name,
                        parts[-1],
                        src_dir_fd=parent.descriptor,
                        dst_dir_fd=parent.descriptor,
                    )
                    self._fsync_directory(parent.descriptor)
                    self._verify_named_identity(
                        parent.descriptor,
                        parts[-1],
                        temporary_identity,
                        changed_code="overlay_temp_changed",
                    )
                except BaseException:
                    self._unlink_if_identity(
                        parent.descriptor,
                        temporary_name,
                        temporary_identity,
                    )
                    raise
                return self._read_named(
                    parent.descriptor,
                    parts[-1],
                    relative_path,
                )

    def snapshot(
        self,
        note_id: str,
        revision: int,
        content: StoredOverlayBytes,
    ) -> OverlaySnapshot:
        """Create or replay one immutable, hash-bound revision snapshot."""
        self._validate_revision(revision)
        if not isinstance(note_id, str) or not note_id:
            raise OverlayStorageError("invalid_snapshot_identity")
        try:
            note_key = hashlib.sha256(note_id.encode("utf-8")).hexdigest()
        except UnicodeEncodeError as error:
            raise OverlayStorageError("invalid_snapshot_identity") from error
        payload = self._validated_record_payload(content)
        filename = f"{note_key}-r{revision}-{content.content_hash}.md"
        relative_snapshot = f"revisions/{filename}"

        if os.name == "nt":  # pragma: no cover - exercised on Windows
            self._windows_snapshot(filename, payload)
        else:
            with self._posix_layout() as opened:
                try:
                    self._create_named(
                        opened.revisions.descriptor,
                        filename,
                        relative_snapshot,
                        payload,
                    )
                except OverlayConflictError:
                    replay = self._read_named(
                        opened.revisions.descriptor,
                        filename,
                        relative_snapshot,
                    )
                    if not hmac.compare_digest(
                        replay.content_hash,
                        content.content_hash,
                    ):
                        raise OverlayConflictError(
                            "overlay_snapshot_conflict"
                        ) from None

        return OverlaySnapshot(
            relative_snapshot=relative_snapshot,
            content_hash=content.content_hash,
            byte_size=content.byte_size,
        )

    @staticmethod
    def _accept_opaque_operation_id(operation_id: str) -> None:
        if not isinstance(operation_id, str) or not operation_id:
            raise OverlayStorageError("invalid_operation_id")

    @staticmethod
    def _validate_hash(expected_hash: str) -> None:
        if (
            not isinstance(expected_hash, str)
            or len(expected_hash) != _HASH_HEX_LENGTH
            or any(character not in "0123456789abcdef" for character in expected_hash)
        ):
            raise OverlayStorageError("invalid_expected_hash")

    @staticmethod
    def _validate_revision(revision: int) -> None:
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise OverlayStorageError("invalid_revision")

    @staticmethod
    def _validated_parts(relative_path: str) -> tuple[str, ...]:
        try:
            canonical = validate_relative_path(relative_path)
        except OverlayPathError as error:
            raise OverlayStorageError("invalid_relative_path") from error
        parts = tuple(canonical.split("/"))
        if (
            len(parts) < 2
            or parts[0] not in {"Daily", "Notes"}
            or not parts[-1].endswith(".md")
            or parts[-1] == ".md"
        ):
            raise OverlayStorageError("invalid_relative_path")
        if any(unicodedata.normalize("NFC", part) != part for part in parts):
            raise OverlayStorageError("overlay_unicode_collision")
        return parts

    def _validated_record_payload(self, content: StoredOverlayBytes) -> bytes:
        if not isinstance(content, StoredOverlayBytes):
            raise OverlayStorageError("invalid_snapshot_content")
        payload = self._encode(content.markdown, self.max_markdown_bytes)
        digest = hashlib.sha256(payload).hexdigest()
        if content.byte_size != len(payload) or not hmac.compare_digest(
            content.content_hash, digest
        ):
            raise OverlayStorageError("invalid_snapshot_content")
        return payload

    @staticmethod
    def _identity(file_status: os.stat_result) -> tuple[int, int]:
        return (file_status.st_dev, file_status.st_ino)

    @staticmethod
    def _metadata(file_status: os.stat_result) -> tuple[int, ...]:
        return (
            file_status.st_dev,
            file_status.st_ino,
            file_status.st_mode,
            file_status.st_nlink,
            file_status.st_size,
            file_status.st_mtime_ns,
            file_status.st_ctime_ns,
        )

    @staticmethod
    def _is_reparse(file_status: os.stat_result) -> bool:
        attributes = getattr(file_status, "st_file_attributes", 0)
        return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)

    @classmethod
    def _require_regular(cls, file_status: os.stat_result) -> None:
        if (
            not stat.S_ISREG(file_status.st_mode)
            or file_status.st_nlink != 1
            or cls._is_reparse(file_status)
        ):
            raise OverlayStorageError("overlay_unsafe_file")

    @classmethod
    def _require_directory(cls, directory_status: os.stat_result) -> None:
        if not stat.S_ISDIR(directory_status.st_mode) or cls._is_reparse(
            directory_status
        ):
            raise OverlayStorageError("overlay_unsafe_directory")

    @staticmethod
    def _directory_open_flags() -> int:
        return (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )

    @staticmethod
    def _file_open_flags() -> int:
        return (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_BINARY", 0)
        )

    @staticmethod
    def _write_open_flags() -> int:
        return (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_BINARY", 0)
        )

    @classmethod
    def _open_root_directory(cls, path: Path) -> _OwnedDirectory:
        if not path.is_absolute():
            raise OverlayStorageError("invalid_overlay_layout")
        try:
            descriptor = os.open(Path(path.anchor), cls._directory_open_flags())
        except OSError as error:
            raise OverlayStorageError("overlay_storage_unavailable") from error
        try:
            for segment in path.parts[1:]:
                cls._reject_unicode_collision(descriptor, segment)
                before = os.stat(
                    segment,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
                cls._require_directory(before)
                child_descriptor = os.open(
                    segment,
                    cls._directory_open_flags(),
                    dir_fd=descriptor,
                )
                try:
                    after = os.fstat(child_descriptor)
                    cls._require_directory(after)
                    if cls._identity(before) != cls._identity(after):
                        raise OverlayStorageError("overlay_root_changed")
                except BaseException:
                    os.close(child_descriptor)
                    raise
                os.close(descriptor)
                descriptor = child_descriptor
        except OSError as error:
            if isinstance(error, OverlayStorageError):
                os.close(descriptor)
                raise
            os.close(descriptor)
            raise OverlayStorageError("overlay_storage_unavailable") from error
        final_status = os.fstat(descriptor)
        return _OwnedDirectory(
            descriptor,
            final_status.st_dev,
            final_status.st_ino,
        )

    @classmethod
    def _ensure_posix_directory(
        cls,
        parent_descriptor: int,
        name: str,
    ) -> _OwnedDirectory:
        cls._reject_unicode_collision(parent_descriptor, name)
        created = False
        try:
            before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            try:
                os.mkdir(name, _DIRECTORY_MODE, dir_fd=parent_descriptor)
                created = True
            except FileExistsError:
                pass
            before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        cls._require_directory(before)
        try:
            descriptor = os.open(
                name,
                cls._directory_open_flags(),
                dir_fd=parent_descriptor,
            )
        except OSError as error:
            raise OverlayStorageError("overlay_unsafe_directory") from error
        try:
            after = os.fstat(descriptor)
            cls._require_directory(after)
            if cls._identity(before) != cls._identity(after):
                raise OverlayStorageError("overlay_root_changed")
            try:
                os.fchmod(descriptor, _DIRECTORY_MODE)
            except (AttributeError, NotImplementedError):  # pragma: no cover
                pass
            cls._fsync_directory(descriptor)
            if created:
                cls._fsync_directory(parent_descriptor)
            return _OwnedDirectory(descriptor, after.st_dev, after.st_ino)
        except BaseException:
            os.close(descriptor)
            raise

    @classmethod
    def _reject_unicode_collision(cls, directory_descriptor: int, name: str) -> None:
        normalized = unicodedata.normalize("NFC", name)
        try:
            entries = os.listdir(directory_descriptor)
        except OSError as error:
            raise OverlayStorageError("overlay_storage_unavailable") from error
        aliases = [
            entry
            for entry in entries
            if entry != name and unicodedata.normalize("NFC", entry) == normalized
        ]
        if not aliases:
            return
        try:
            requested = os.stat(
                name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            raise OverlayStorageError("overlay_unicode_collision") from None
        requested_identity = cls._identity(requested)
        for alias in aliases:
            alias_status = os.stat(
                alias,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if cls._identity(alias_status) != requested_identity:
                raise OverlayStorageError("overlay_unicode_collision")

    @staticmethod
    def _verify_path_identity(path: Path, identity: tuple[int, int]) -> None:
        try:
            status = path.lstat()
        except OSError as error:
            raise OverlayStorageError("overlay_root_changed") from error
        if (
            not stat.S_ISDIR(status.st_mode)
            or OverlayStorage._is_reparse(status)
            or OverlayStorage._identity(status) != identity
        ):
            raise OverlayStorageError("overlay_root_changed")

    @classmethod
    def _verify_directory_entry(
        cls,
        parent_descriptor: int,
        name: str,
        owned: _OwnedDirectory,
    ) -> None:
        try:
            status = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as error:
            raise OverlayStorageError("overlay_root_changed") from error
        cls._require_directory(status)
        if cls._identity(status) != owned.identity:
            raise OverlayStorageError("overlay_root_changed")

    @contextmanager
    def _posix_layout(self) -> Iterator[_PosixLayout]:
        data_root_path = self.layout.canonical_root.parent.parent
        data_root = self._open_root_directory(data_root_path)
        opened: list[_OwnedDirectory] = [data_root]
        try:
            overlay_parent = self._ensure_posix_directory(
                data_root.descriptor,
                self.layout.canonical_root.parent.name,
            )
            opened.append(overlay_parent)
            canonical = self._ensure_posix_directory(
                overlay_parent.descriptor,
                self.layout.canonical_root.name,
            )
            opened.append(canonical)
            daily = self._ensure_posix_directory(canonical.descriptor, "Daily")
            opened.append(daily)
            notes = self._ensure_posix_directory(canonical.descriptor, "Notes")
            opened.append(notes)
            state = self._ensure_posix_directory(
                data_root.descriptor,
                self.layout.state_root.name,
            )
            opened.append(state)
            revisions = self._ensure_posix_directory(state.descriptor, "revisions")
            opened.append(revisions)
            receipts = self._ensure_posix_directory(state.descriptor, "receipts")
            opened.append(receipts)
            recovery = self._ensure_posix_directory(state.descriptor, "recovery")
            opened.append(recovery)
            layout = _PosixLayout(
                data_root=data_root,
                overlay_parent=overlay_parent,
                canonical=canonical,
                daily=daily,
                notes=notes,
                state=state,
                revisions=revisions,
                receipts=receipts,
                recovery=recovery,
            )
            self._verify_layout(layout, data_root_path)
            try:
                yield layout
            finally:
                self._verify_layout(layout, data_root_path)
        finally:
            for directory in reversed(opened):
                os.close(directory.descriptor)

    def _verify_layout(self, opened: _PosixLayout, data_root_path: Path) -> None:
        self._verify_path_identity(data_root_path, opened.data_root.identity)
        self._verify_path_identity(
            self.layout.canonical_root,
            opened.canonical.identity,
        )
        self._verify_path_identity(self.layout.state_root, opened.state.identity)
        self._verify_directory_entry(
            opened.data_root.descriptor,
            self.layout.canonical_root.parent.name,
            opened.overlay_parent,
        )
        self._verify_directory_entry(
            opened.overlay_parent.descriptor,
            self.layout.canonical_root.name,
            opened.canonical,
        )
        self._verify_directory_entry(
            opened.canonical.descriptor,
            "Daily",
            opened.daily,
        )
        self._verify_directory_entry(
            opened.canonical.descriptor,
            "Notes",
            opened.notes,
        )
        self._verify_directory_entry(
            opened.data_root.descriptor,
            self.layout.state_root.name,
            opened.state,
        )
        for name, directory in (
            ("revisions", opened.revisions),
            ("receipts", opened.receipts),
            ("recovery", opened.recovery),
        ):
            self._verify_directory_entry(opened.state.descriptor, name, directory)

    @contextmanager
    def _posix_parent(
        self,
        opened: _PosixLayout,
        parts: tuple[str, ...],
    ) -> Iterator[_OwnedDirectory]:
        base = opened.daily if parts[0] == "Daily" else opened.notes
        current = base
        intermediates: list[tuple[_OwnedDirectory, str, _OwnedDirectory]] = []
        try:
            for segment in parts[1:-1]:
                self._reject_unicode_collision(current.descriptor, segment)
                try:
                    before = os.stat(
                        segment,
                        dir_fd=current.descriptor,
                        follow_symlinks=False,
                    )
                    self._require_directory(before)
                    descriptor = os.open(
                        segment,
                        self._directory_open_flags(),
                        dir_fd=current.descriptor,
                    )
                except OSError as error:
                    raise OverlayStorageError("overlay_unsafe_directory") from error
                after = os.fstat(descriptor)
                self._require_directory(after)
                if self._identity(before) != self._identity(after):
                    os.close(descriptor)
                    raise OverlayStorageError("overlay_root_changed")
                child = _OwnedDirectory(descriptor, after.st_dev, after.st_ino)
                intermediates.append((current, segment, child))
                current = child
            self._reject_unicode_collision(current.descriptor, parts[-1])
            try:
                yield current
            finally:
                for parent, name, child in intermediates:
                    self._verify_directory_entry(parent.descriptor, name, child)
        finally:
            for _, _, child in reversed(intermediates):
                os.close(child.descriptor)

    def _read_all(self, file_descriptor: int) -> bytes:
        chunks: list[bytes] = []
        remaining = self.max_markdown_bytes + 1
        while remaining > 0:
            chunk = os.read(file_descriptor, min(_READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > self.max_markdown_bytes:
            raise OverlayStorageError("overlay_file_too_large")
        return payload

    def _read_named(
        self,
        parent_descriptor: int,
        name: str,
        relative_path: str,
    ) -> StoredOverlayBytes:
        content, _identity = self._read_named_with_identity(
            parent_descriptor,
            name,
            relative_path,
        )
        return content

    def _read_named_with_identity(
        self,
        parent_descriptor: int,
        name: str,
        relative_path: str,
    ) -> tuple[StoredOverlayBytes, tuple[int, int]]:
        self._reject_unicode_collision(parent_descriptor, name)
        try:
            descriptor = os.open(
                name,
                self._file_open_flags(),
                dir_fd=parent_descriptor,
            )
        except FileNotFoundError as error:
            raise OverlayStorageError("overlay_not_found") from error
        except OSError as error:
            raise OverlayStorageError("overlay_unsafe_file") from error
        try:
            before = os.fstat(descriptor)
            self._require_regular(before)
            payload = self._read_all(descriptor)
            after = os.fstat(descriptor)
            self._require_regular(after)
            if self._metadata(before) != self._metadata(after):
                raise OverlayStorageError("overlay_file_changed")
            self._verify_named_identity(
                parent_descriptor,
                name,
                self._identity(before),
                changed_code="overlay_file_changed",
            )
            return (
                self._record(relative_path, payload, after.st_mtime_ns),
                self._identity(after),
            )
        finally:
            os.close(descriptor)

    def _record(
        self,
        relative_path: str,
        payload: bytes,
        modified_ns: int,
    ) -> StoredOverlayBytes:
        if b"\r" in payload:
            raise OverlayStorageError("overlay_invalid_markdown")
        try:
            markdown = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise OverlayStorageError("overlay_invalid_markdown") from error
        return StoredOverlayBytes(
            relative_path=relative_path,
            markdown=markdown,
            content_hash=hashlib.sha256(payload).hexdigest(),
            byte_size=len(payload),
            modified_ns=modified_ns,
        )

    def _create_named(
        self,
        parent_descriptor: int,
        name: str,
        relative_path: str,
        payload: bytes,
    ) -> StoredOverlayBytes:
        self._reject_unicode_collision(parent_descriptor, name)
        try:
            descriptor = os.open(
                name,
                self._write_open_flags(),
                _FILE_MODE,
                dir_fd=parent_descriptor,
            )
        except FileExistsError as error:
            try:
                existing = os.stat(
                    name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                self._require_regular(existing)
            except OverlayStorageError:
                raise
            except OSError:
                pass
            raise OverlayConflictError("overlay_file_exists") from error
        except OSError as error:
            raise OverlayStorageError("overlay_storage_unavailable") from error

        created_status = os.fstat(descriptor)
        created_identity = self._identity(created_status)
        completed = False
        try:
            self._require_regular(created_status)
            try:
                os.fchmod(descriptor, _FILE_MODE)
            except (AttributeError, NotImplementedError):  # pragma: no cover
                pass
            self._write_all(descriptor, payload)
            os.fsync(descriptor)
            final_status = os.fstat(descriptor)
            self._require_regular(final_status)
            if self._identity(final_status) != created_identity:
                raise OverlayStorageError("overlay_file_changed")
            completed = True
        finally:
            os.close(descriptor)
            if not completed:
                self._unlink_if_identity(parent_descriptor, name, created_identity)

        self._verify_named_identity(
            parent_descriptor,
            name,
            created_identity,
            changed_code="overlay_file_changed",
        )
        self._fsync_directory(parent_descriptor)
        return self._read_named(parent_descriptor, name, relative_path)

    @staticmethod
    def _write_all(file_descriptor: int, payload: bytes) -> None:
        view = memoryview(payload)
        written = 0
        while written < len(view):
            count = os.write(file_descriptor, view[written:])
            if count <= 0:
                raise OverlayStorageError("overlay_storage_unavailable")
            written += count

    def _write_posix_temp(
        self,
        parent_descriptor: int,
        payload: bytes,
    ) -> tuple[str, tuple[int, int]]:
        descriptor = -1
        name = ""
        for _ in range(128):
            name = f".overlay-{os.urandom(16).hex()}.tmp"
            try:
                descriptor = os.open(
                    name,
                    self._write_open_flags(),
                    _FILE_MODE,
                    dir_fd=parent_descriptor,
                )
                break
            except FileExistsError:
                continue
        if descriptor < 0:
            raise OverlayStorageError("overlay_temp_unavailable")
        created = os.fstat(descriptor)
        identity = self._identity(created)
        completed = False
        try:
            self._require_regular(created)
            try:
                os.fchmod(descriptor, _FILE_MODE)
            except (AttributeError, NotImplementedError):  # pragma: no cover
                pass
            self._write_all(descriptor, payload)
            os.fsync(descriptor)
            after = os.fstat(descriptor)
            self._require_regular(after)
            if self._identity(after) != identity:
                raise OverlayStorageError("overlay_temp_changed")
            completed = True
        finally:
            os.close(descriptor)
            if not completed:
                self._unlink_if_identity(parent_descriptor, name, identity)
        return name, identity

    @classmethod
    def _verify_named_identity(
        cls,
        parent_descriptor: int,
        name: str,
        identity: tuple[int, int],
        *,
        changed_code: str,
    ) -> None:
        try:
            status = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as error:
            raise OverlayStorageError(changed_code) from error
        cls._require_regular(status)
        if cls._identity(status) != identity:
            raise OverlayStorageError(changed_code)

    @classmethod
    def _unlink_if_identity(
        cls,
        parent_descriptor: int,
        name: str,
        identity: tuple[int, int],
    ) -> None:
        try:
            status = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return
        except OSError:
            return
        if cls._identity(status) != identity or not stat.S_ISREG(status.st_mode):
            return
        try:
            os.unlink(name, dir_fd=parent_descriptor)
        except OSError:
            return

    @staticmethod
    def _fsync_directory(directory_descriptor: int) -> None:
        try:
            os.fsync(directory_descriptor)
        except OSError as error:
            if error.errno not in {
                errno.EBADF,
                errno.EINVAL,
                errno.ENOTSUP,
                errno.EROFS,
            }:
                raise

    # Windows uses checked absolute paths because dir_fd traversal is unavailable.
    # Each component and retained root identity is revalidated before and after IO.

    def _windows_owned_path(self, parts: tuple[str, ...]) -> _WindowsOwnedPath:
        data_root = self.layout.canonical_root.parent.parent
        directories: list[tuple[Path, tuple[int, int]]] = []
        for path, create in (
            (data_root, False),
            (self.layout.canonical_root.parent, True),
            (self.layout.canonical_root, True),
            (self.layout.daily_root, True),
            (self.layout.unique_root, True),
            (self.layout.state_root, True),
            (self.layout.revisions_root, True),
            (self.layout.receipts_root, True),
            (self.layout.recovery_root, True),
        ):
            directories.append(
                (path, self._windows_ensure_directory(path, create=create))
            )
        root = (
            self.layout.daily_root if parts[0] == "Daily" else self.layout.unique_root
        )
        current = root
        for segment in parts[1:-1]:
            self._windows_reject_unicode_collision(current, segment)
            current /= segment
            directories.append(
                (
                    current,
                    self._windows_ensure_directory(current, create=False),
                )
            )
        self._windows_reject_unicode_collision(current, parts[-1])
        owned = _WindowsOwnedPath(
            path=current / parts[-1],
            directories=tuple(directories),
        )
        self._windows_verify_directories(owned)
        return owned

    @classmethod
    def _windows_reject_unicode_collision(cls, parent: Path, name: str) -> None:
        normalized = unicodedata.normalize("NFC", name)
        try:
            aliases = [
                entry
                for entry in parent.iterdir()
                if entry.name != name
                and unicodedata.normalize("NFC", entry.name) == normalized
            ]
        except OSError as error:
            raise OverlayStorageError("overlay_storage_unavailable") from error
        if not aliases:
            return
        requested = parent / name
        try:
            requested_identity = cls._identity(requested.lstat())
        except FileNotFoundError:
            raise OverlayStorageError("overlay_unicode_collision") from None
        for alias in aliases:
            if cls._identity(alias.lstat()) != requested_identity:
                raise OverlayStorageError("overlay_unicode_collision")

    @classmethod
    def _windows_ensure_directory(
        cls,
        path: Path,
        *,
        create: bool,
    ) -> tuple[int, int]:
        try:
            status = path.lstat()
        except FileNotFoundError:
            if not create:
                raise OverlayStorageError("overlay_storage_unavailable") from None
            os.mkdir(path, _DIRECTORY_MODE)
            status = path.lstat()
        cls._require_directory(status)
        if path.resolve(strict=True) != path.absolute():
            raise OverlayStorageError("overlay_root_changed")
        try:
            os.chmod(path, _DIRECTORY_MODE)
        except OSError:
            pass
        return cls._identity(status)

    @classmethod
    def _windows_verify_directories(cls, owned: _WindowsOwnedPath) -> None:
        for path, identity in owned.directories:
            try:
                status = path.lstat()
            except OSError as error:
                raise OverlayStorageError("overlay_root_changed") from error
            cls._require_directory(status)
            if cls._identity(status) != identity:
                raise OverlayStorageError("overlay_root_changed")

    def _windows_read(
        self,
        relative_path: str,
        parts: tuple[str, ...],
    ) -> StoredOverlayBytes:
        content, _identity = self._windows_read_owned(
            self._windows_owned_path(parts),
            relative_path,
        )
        return content

    def _windows_read_owned(
        self,
        owned: _WindowsOwnedPath,
        relative_path: str,
    ) -> tuple[StoredOverlayBytes, tuple[int, int]]:
        path = owned.path
        self._windows_verify_directories(owned)
        try:
            before_path = path.lstat()
            self._require_regular(before_path)
            descriptor = os.open(path, self._file_open_flags())
        except FileNotFoundError as error:
            raise OverlayStorageError("overlay_not_found") from error
        except OSError as error:
            if isinstance(error, OverlayStorageError):
                raise
            raise OverlayStorageError("overlay_unsafe_file") from error
        try:
            before = os.fstat(descriptor)
            self._require_regular(before)
            if self._identity(before_path) != self._identity(before):
                raise OverlayStorageError("overlay_file_changed")
            payload = self._read_all(descriptor)
            after = os.fstat(descriptor)
            if self._metadata(before) != self._metadata(after):
                raise OverlayStorageError("overlay_file_changed")
            final_path = path.lstat()
            if self._identity(final_path) != self._identity(before):
                raise OverlayStorageError("overlay_file_changed")
            self._windows_verify_directories(owned)
            return (
                self._record(relative_path, payload, after.st_mtime_ns),
                self._identity(after),
            )
        finally:
            os.close(descriptor)

    def _windows_create(
        self,
        relative_path: str,
        parts: tuple[str, ...],
        payload: bytes,
    ) -> StoredOverlayBytes:
        owned = self._windows_owned_path(parts)
        path = owned.path
        try:
            descriptor = os.open(path, self._write_open_flags(), _FILE_MODE)
        except FileExistsError as error:
            try:
                self._require_regular(path.lstat())
            except OverlayStorageError:
                raise
            raise OverlayConflictError("overlay_file_exists") from error
        identity = self._identity(os.fstat(descriptor))
        completed = False
        try:
            self._write_all(descriptor, payload)
            os.fsync(descriptor)
            completed = True
        finally:
            os.close(descriptor)
            if not completed:
                self._windows_unlink_if_identity(path, identity)
        if self._identity(path.lstat()) != identity:
            raise OverlayStorageError("overlay_file_changed")
        self._windows_verify_directories(owned)
        content, _identity = self._windows_read_owned(owned, relative_path)
        return content

    def _windows_replace(
        self,
        relative_path: str,
        parts: tuple[str, ...],
        payload: bytes,
        expected_hash: str,
        revision: int,
    ) -> StoredOverlayBytes:
        owned = self._windows_owned_path(parts)
        current, current_identity = self._windows_read_owned(owned, relative_path)
        if not hmac.compare_digest(current.content_hash, expected_hash):
            raise OverlayConflictError("overlay_hash_conflict")
        self.snapshot(relative_path, max(revision - 1, 1), current)
        self._windows_verify_directories(owned)
        destination = owned.path
        try:
            destination_status = destination.lstat()
        except OSError as error:
            raise OverlayStorageError("overlay_file_changed") from error
        if self._identity(destination_status) != current_identity:
            raise OverlayStorageError("overlay_file_changed")
        temporary = destination.parent / f".overlay-{os.urandom(16).hex()}.tmp"
        descriptor = os.open(temporary, self._write_open_flags(), _FILE_MODE)
        identity = self._identity(os.fstat(descriptor))
        completed = False
        try:
            self._write_all(descriptor, payload)
            os.fsync(descriptor)
            completed = True
        finally:
            os.close(descriptor)
            if not completed:
                self._windows_unlink_if_identity(temporary, identity)
        try:
            if self._identity(temporary.lstat()) != identity:
                raise OverlayStorageError("overlay_temp_changed")
            self._windows_verify_directories(owned)
            if self._identity(destination.lstat()) != current_identity:
                raise OverlayStorageError("overlay_file_changed")
            os.replace(temporary, destination)
            if self._identity(destination.lstat()) != identity:
                raise OverlayStorageError("overlay_temp_changed")
            self._windows_verify_directories(owned)
        except BaseException:
            self._windows_unlink_if_identity(temporary, identity)
            raise
        content, _identity = self._windows_read_owned(owned, relative_path)
        return content

    def _windows_snapshot(self, filename: str, payload: bytes) -> None:
        parts = ("Notes", "placeholder.md")
        layout = self._windows_owned_path(parts)
        owned = _WindowsOwnedPath(
            path=self.layout.revisions_root / filename,
            directories=layout.directories,
        )
        path = owned.path
        self._windows_verify_directories(owned)
        try:
            descriptor = os.open(path, self._write_open_flags(), _FILE_MODE)
        except FileExistsError:
            existing, _identity = self._windows_read_owned(
                owned,
                f"revisions/{filename}",
            )
            existing_bytes = self._encode(existing.markdown, self.max_markdown_bytes)
            if not hmac.compare_digest(
                hashlib.sha256(existing_bytes).digest(),
                hashlib.sha256(payload).digest(),
            ):
                raise OverlayConflictError("overlay_snapshot_conflict") from None
            return
        identity = self._identity(os.fstat(descriptor))
        completed = False
        try:
            self._write_all(descriptor, payload)
            os.fsync(descriptor)
            completed = True
        finally:
            os.close(descriptor)
            if not completed:
                self._windows_unlink_if_identity(path, identity)
        if self._identity(path.lstat()) != identity:
            raise OverlayStorageError("overlay_file_changed")
        self._windows_verify_directories(owned)

    @classmethod
    def _windows_unlink_if_identity(
        cls,
        path: Path,
        identity: tuple[int, int],
    ) -> None:
        try:
            status = path.lstat()
        except OSError:
            return
        if cls._identity(status) != identity or not stat.S_ISREG(status.st_mode):
            return
        try:
            path.unlink()
        except OSError:
            return
