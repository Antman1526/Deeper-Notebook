"""Canonical source authority for source-derived visual work.

This module deliberately keeps the authority boundary small: source metadata is
normalised into a stable fingerprint, and an uploaded file is hashed only after
its path and descriptor have been checked against the controlled upload root.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from deeper_notebook.source_visuals.contracts import SourceVisualAuthority

_HASH_LENGTH = 64
_READ_SIZE = 1024 * 1024
_PUBLIC_ERROR_CODES = frozenset(
    {
        "SOURCE_ID_INVALID",
        "SOURCE_REVISION_MISSING",
        "SOURCE_FILE_INVALID",
        "SOURCE_FILE_MISSING",
        "SOURCE_FILE_SYMLINK",
        "SOURCE_FILE_NOT_REGULAR",
        "SOURCE_FILE_OUTSIDE_ROOT",
        "SOURCE_FILE_UNREADABLE",
        "SOURCE_FILE_READ_FAILED",
        "SOURCE_FILE_CHANGED",
        "UPLOAD_ROOT_UNAVAILABLE",
        "SOURCE_HASH_INVALID",
    }
)


class SourceVisualAuthorityError(ValueError):
    """Safe, bounded failure for source authority computation.

    Only the public error code is exposed.  In particular, source text and
    filesystem paths never become part of an exception message.
    """

    def __init__(self, code: str):
        self.code = code if code in _PUBLIC_ERROR_CODES else "SOURCE_FILE_INVALID"
        super().__init__(self.code)


def canonical_fingerprint_payload(
    *,
    source_id: str,
    normalized_source_type: str,
    asset_url: str | None,
    source_file_sha256: str | None,
    full_text_sha256: str | None,
    extractor_version: str,
) -> dict[str, object]:
    """Return the versioned, explicit-null fingerprint payload."""

    return {
        "schema_version": 1,
        "source_id": source_id,
        "source_type": normalized_source_type,
        "asset_url": asset_url,
        "source_file_sha256": source_file_sha256,
        "full_text_sha256": full_text_sha256,
        "extractor_version": extractor_version,
    }


def fingerprint_payload(payload: Mapping[str, object]) -> str:
    """Hash a canonical payload using compact, deterministic JSON."""

    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _get(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _first(value: object, *names: str) -> object:
    for name in names:
        candidate = _get(value, name)
        if candidate is not None:
            return candidate
    return None


def _normalise_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _validate_hash(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != _HASH_LENGTH:
        raise SourceVisualAuthorityError("SOURCE_HASH_INVALID")
    try:
        int(value, 16)
    except ValueError as exc:
        raise SourceVisualAuthorityError("SOURCE_HASH_INVALID") from exc
    if value.lower() != value:
        raise SourceVisualAuthorityError("SOURCE_HASH_INVALID")
    return value


def _source_id(source: object) -> str:
    value = _first(source, "source_id", "id")
    if value is None:
        raise SourceVisualAuthorityError("SOURCE_ID_INVALID")
    result = str(value)
    if not result.startswith("source:"):
        raise SourceVisualAuthorityError("SOURCE_ID_INVALID")
    return result


def _source_file_path(source: object) -> Path | None:
    direct = _first(source, "controlled_file_path", "source_file_path", "file_path")
    asset = _get(source, "asset")
    if direct is None and asset is not None:
        direct = _get(asset, "file_path")
    if direct is None:
        return None
    if isinstance(direct, Path):
        return direct
    if not isinstance(direct, str) or not direct:
        raise SourceVisualAuthorityError("SOURCE_FILE_INVALID")
    try:
        return Path(direct)
    except (OSError, ValueError):
        raise SourceVisualAuthorityError("SOURCE_FILE_INVALID") from None


def _asset_url(source: object) -> str | None:
    value = _first(source, "asset_url", "url")
    asset = _get(source, "asset")
    if value is None and asset is not None:
        value = _get(asset, "url")
    if value is None:
        return None
    return str(value) or None


def _upload_root(source: object) -> Path | None:
    value = _first(source, "upload_root", "controlled_upload_root")
    if value is None:
        value = os.environ.get("UPLOADS_FOLDER")
    if value is None:
        try:
            from deeper_notebook.config import UPLOADS_FOLDER

            value = UPLOADS_FOLDER
        except Exception:
            return None
    try:
        return Path(value).resolve(strict=False)
    except (OSError, ValueError):
        return None


def _file_identity(stat_result: os.stat_result | object) -> tuple[object, ...]:
    return (
        getattr(stat_result, "st_dev", None),
        getattr(stat_result, "st_ino", None),
        getattr(stat_result, "st_mode", None),
        getattr(stat_result, "st_size", None),
        getattr(stat_result, "st_mtime_ns", None),
    )


def _hash_controlled_file(path: Path, upload_root: Path) -> tuple[str, str]:
    try:
        resolved_path = path.resolve(strict=False)
    except (OSError, ValueError):
        raise SourceVisualAuthorityError("SOURCE_FILE_INVALID") from None
    try:
        inside_root = resolved_path.is_relative_to(upload_root)
    except AttributeError:  # pragma: no cover - Python 3.11 compatibility
        inside_root = str(resolved_path).startswith(str(upload_root) + os.sep)
    if not inside_root or resolved_path == upload_root:
        raise SourceVisualAuthorityError("SOURCE_FILE_OUTSIDE_ROOT")

    if path.is_symlink():
        raise SourceVisualAuthorityError("SOURCE_FILE_SYMLINK")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_descriptor = os.open(os.fspath(path), flags)
    except FileNotFoundError:
        raise SourceVisualAuthorityError("SOURCE_FILE_MISSING") from None
    except OSError as exc:
        if getattr(exc, "errno", None) in {40, 62}:  # ELOOP on common Unix hosts
            raise SourceVisualAuthorityError("SOURCE_FILE_SYMLINK") from None
        raise SourceVisualAuthorityError("SOURCE_FILE_UNREADABLE") from None

    try:
        try:
            before = os.fstat(file_descriptor)
        except OSError:
            raise SourceVisualAuthorityError("SOURCE_FILE_UNREADABLE") from None
        if not stat.S_ISREG(getattr(before, "st_mode", 0)):
            raise SourceVisualAuthorityError("SOURCE_FILE_NOT_REGULAR")

        digest = hashlib.sha256()
        try:
            while True:
                chunk = os.read(file_descriptor, _READ_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
            after = os.fstat(file_descriptor)
        except OSError:
            raise SourceVisualAuthorityError("SOURCE_FILE_READ_FAILED") from None
        if _file_identity(before) != _file_identity(after):
            raise SourceVisualAuthorityError("SOURCE_FILE_CHANGED")
        return digest.hexdigest(), str(path)
    finally:
        os.close(file_descriptor)


async def compute_source_visual_authority(source: object) -> SourceVisualAuthority:
    """Compute the immutable authority snapshot for a Source-like object."""

    source_id = _source_id(source)
    source_updated_at = _normalise_datetime(
        _first(source, "source_updated_at", "updated")
    )
    if source_updated_at is None:
        raise SourceVisualAuthorityError("SOURCE_REVISION_MISSING")

    normalized_source_type = _first(
        source, "normalized_source_type", "source_type"
    )
    if normalized_source_type is None:
        normalized_source_type = "unknown"
    normalized_source_type = str(normalized_source_type)

    extractor_version = _first(source, "extractor_version") or "source-visual-v1"
    extractor_version = str(extractor_version)

    controlled_path = _source_file_path(source)
    source_file_sha256 = _validate_hash(_first(source, "source_file_sha256"))
    controlled_file_path: str | None = None
    if controlled_path is not None:
        root = _upload_root(source)
        if root is None:
            raise SourceVisualAuthorityError("UPLOAD_ROOT_UNAVAILABLE")
        source_file_sha256, controlled_file_path = _hash_controlled_file(
            controlled_path, root
        )

    full_text_sha256 = _validate_hash(_first(source, "full_text_sha256"))
    if full_text_sha256 is None:
        full_text = _first(source, "full_text")
        if full_text is not None:
            if not isinstance(full_text, str):
                raise SourceVisualAuthorityError("SOURCE_HASH_INVALID")
            full_text_sha256 = hashlib.sha256(full_text.encode("utf-8")).hexdigest()

    asset_url = _asset_url(source)
    payload = canonical_fingerprint_payload(
        source_id=source_id,
        normalized_source_type=normalized_source_type,
        asset_url=asset_url,
        source_file_sha256=source_file_sha256,
        full_text_sha256=full_text_sha256,
        extractor_version=extractor_version,
    )
    return SourceVisualAuthority(
        source_id=source_id,
        source_updated_at=source_updated_at,
        normalized_source_type=normalized_source_type,
        asset_url=asset_url,
        controlled_file_path=controlled_file_path,
        source_file_sha256=source_file_sha256,
        full_text_sha256=full_text_sha256,
        content_sha256=fingerprint_payload(payload),
        extractor_version=extractor_version,
    )


__all__ = [
    "SourceVisualAuthorityError",
    "canonical_fingerprint_payload",
    "compute_source_visual_authority",
    "fingerprint_payload",
]
