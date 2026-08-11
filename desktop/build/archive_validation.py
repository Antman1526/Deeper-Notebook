"""Bounded validation for bundled runtime archives.

Archive readers are deliberately kept separate from extraction.  Callers must
validate the complete member list before invoking ``extractall``; this keeps
the standard-library extraction primitive behind an explicit layout and path
contract (and preserves the relative symlinks shipped by Python and Node).
"""

from __future__ import annotations

import stat
from pathlib import PurePosixPath
from typing import Iterable

_MAX_ARCHIVE_MEMBERS = 50_000
_MAX_MEMBER_NAME_BYTES = 4096
_MAX_LINK_TARGET_BYTES = 4096
_MAX_DECLARED_BYTES = 4 * 1024**3


def _normalise_member_name(name: str) -> PurePosixPath:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise ValueError("archive member name is malformed")
    if len(name.encode("utf-8", errors="surrogatepass")) > _MAX_MEMBER_NAME_BYTES:
        raise ValueError("archive member name is too long")
    if "\\" in name:
        raise ValueError("archive member uses a backslash path separator")
    if name.startswith("/"):
        raise ValueError(f"archive member is absolute: {name!r}")

    parts = [part for part in name.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"archive member traverses its root: {name!r}")
    return PurePosixPath(*parts)


def _validate_link_target(member_name: PurePosixPath, linkname: str) -> PurePosixPath:
    if not isinstance(linkname, str) or not linkname or "\x00" in linkname:
        raise ValueError(f"archive link target is malformed: {member_name}")
    if len(linkname.encode("utf-8", errors="surrogatepass")) > _MAX_LINK_TARGET_BYTES:
        raise ValueError(f"archive link target is too long: {member_name}")
    if "\\" in linkname or linkname.startswith("/"):
        raise ValueError(f"archive link target escapes its root: {member_name}")

    resolved = list(member_name.parent.parts)
    for part in linkname.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not resolved:
                raise ValueError(f"archive link target escapes its root: {member_name}")
            resolved.pop()
        else:
            resolved.append(part)
    if not resolved:
        raise ValueError(f"archive link target is empty: {member_name}")
    return PurePosixPath(*resolved)


def _validate_layout(
    names: Iterable[PurePosixPath],
    *,
    expected_root: str,
    required_members: Iterable[str] = (),
    exact_members: Iterable[str] | None = None,
) -> set[PurePosixPath]:
    name_set = set(names)
    root = _normalise_member_name(expected_root)
    if any(not name.parts or name.parts[0] != root.parts[0] for name in name_set):
        raise ValueError(f"archive contains an unexpected top-level layout (expected {root})")
    if not any(name == root or root in name.parents for name in name_set):
        raise ValueError(f"archive is missing expected root {root}")

    required = {_normalise_member_name(name) for name in required_members}
    if not required.issubset(name_set):
        missing = sorted(str(name) for name in required - name_set)
        raise ValueError(f"archive is missing required members: {missing}")

    if exact_members is not None:
        exact = {_normalise_member_name(name) for name in exact_members}
        if name_set != exact:
            raise ValueError("archive contains unexpected members")
    return name_set


def validate_tar_members(
    members: Iterable[object],
    *,
    expected_root: str,
    required_members: Iterable[str] = (),
    exact_members: Iterable[str] | None = None,
    allow_symlinks: bool = True,
) -> None:
    """Validate tar member paths, links, types, duplicates, and layout."""
    seen: set[PurePosixPath] = set()
    names: list[PurePosixPath] = []
    declared_bytes = 0
    root = _normalise_member_name(expected_root)
    for index, member in enumerate(members, start=1):
        if index > _MAX_ARCHIVE_MEMBERS:
            raise ValueError("archive contains too many members")
        name = _normalise_member_name(getattr(member, "name", ""))
        if name in seen:
            raise ValueError(f"archive contains duplicate member target: {name}")
        seen.add(name)
        names.append(name)

        if getattr(member, "isdev", lambda: False)():
            raise ValueError(f"archive contains a device member: {name}")
        if getattr(member, "islnk", lambda: False)():
            raise ValueError(f"archive hard links are not supported: {name}")
        is_link = getattr(member, "issym", lambda: False)()
        is_file = getattr(member, "isfile", lambda: False)()
        is_dir = getattr(member, "isdir", lambda: False)()
        if is_link:
            if not allow_symlinks:
                raise ValueError(f"archive links are not allowed: {name}")
            target = _validate_link_target(name, getattr(member, "linkname", ""))
            if not target.parts or target.parts[0] != root.parts[0]:
                raise ValueError(f"archive link target escapes its root: {name}")
        elif is_file:
            size = int(getattr(member, "size", 0) or 0)
            if size < 0:
                raise ValueError(f"archive member has a negative size: {name}")
            declared_bytes += size
            if declared_bytes > _MAX_DECLARED_BYTES:
                raise ValueError("archive declares too many file bytes")
        elif not is_dir:
            raise ValueError(f"archive contains an unsupported member type: {name}")

    _validate_layout(
        names,
        expected_root=expected_root,
        required_members=required_members,
        exact_members=exact_members,
    )


def _zipinfo_is_symlink(info: object) -> bool:
    external_attr = int(getattr(info, "external_attr", 0) or 0)
    mode = (external_attr >> 16) & 0o170000
    return stat.S_ISLNK(mode)


def _zipinfo_is_special(info: object) -> bool:
    external_attr = int(getattr(info, "external_attr", 0) or 0)
    mode = (external_attr >> 16) & 0o170000
    return mode not in {0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}


def validate_zip_members(
    members: Iterable[object],
    *,
    expected_root: str,
    required_members: Iterable[str] = (),
    exact_members: Iterable[str] | None = None,
) -> None:
    """Validate ZIP member paths, duplicate targets, special files, and layout.

    ZIP symlinks are rejected rather than materialised: the supported Windows
    Node/uv/Python layouts contain regular files only, while tar archives carry
    the nine legitimate Python relative symlinks.
    """
    seen: set[PurePosixPath] = set()
    names: list[PurePosixPath] = []
    declared_bytes = 0
    for index, info in enumerate(members, start=1):
        if index > _MAX_ARCHIVE_MEMBERS:
            raise ValueError("archive contains too many members")
        name = _normalise_member_name(getattr(info, "filename", ""))
        if name in seen:
            raise ValueError(f"archive contains duplicate member target: {name}")
        seen.add(name)
        names.append(name)
        if _zipinfo_is_special(info):
            raise ValueError(f"archive contains a device or special member: {name}")
        if _zipinfo_is_symlink(info):
            raise ValueError(f"archive links are not allowed in ZIP layouts: {name}")
        size = int(getattr(info, "file_size", 0) or 0)
        if size < 0:
            raise ValueError(f"archive member has a negative size: {name}")
        declared_bytes += size
        if declared_bytes > _MAX_DECLARED_BYTES:
            raise ValueError("archive declares too many file bytes")

    _validate_layout(
        names,
        expected_root=expected_root,
        required_members=required_members,
        exact_members=exact_members,
    )
