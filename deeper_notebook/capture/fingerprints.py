"""Streaming content fingerprints for restart-safe capture deduplication."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .contracts import CaptureFingerprint

_HASH_CHUNK_BYTES = 1024 * 1024


class CaptureFingerprintError(RuntimeError):
    """A file changed or became unreadable while it was being fingerprinted."""


def fingerprint_file(path: Path) -> CaptureFingerprint:
    """Hash a stable regular file without loading its content into memory."""
    try:
        before = path.stat()
        if not path.is_file():
            raise CaptureFingerprintError("capture candidate is not a regular file")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(_HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
        after = path.stat()
    except OSError as exc:
        raise CaptureFingerprintError("capture candidate could not be read") from exc
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise CaptureFingerprintError("capture candidate changed while hashing")
    return CaptureFingerprint(sha256=digest.hexdigest(), byte_size=after.st_size)
