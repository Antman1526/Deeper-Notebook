"""Bounded connector-trust manifest parsing without stale-path persistence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Literal

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_MANIFEST_RECORDS = 1000
MAX_SHORT_TEXT = 512
MAX_SOURCE_PATH = 8192
MAX_DERIVED_FROM = 256


class TrustManifestError(ValueError):
    """A stable trust error that never renders source data or local paths."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class TrustManifestEntry:
    manifest_id: str
    canonical_relative_path: str
    status: Literal["approved"]
    reviewer: str
    reviewed_at: datetime
    source_type: str
    evidence_class: Literal["source", "synthesis"]
    content_hash: str
    derived_from: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TrustManifest:
    entries: tuple[TrustManifestEntry, ...]


def _field(record: dict[str, Any], camel: str, snake: str) -> Any:
    if camel in record:
        return record[camel]
    return record.get(snake)


def _required_text(
    value: Any,
    code: str,
    *,
    max_length: int = MAX_SHORT_TEXT,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustManifestError(code)
    cleaned = value.strip()
    if len(cleaned) > max_length:
        raise TrustManifestError(code.replace("missing_", "") + "_too_long")
    return cleaned


def _relative_suffix(vault_root: str, source_path: str) -> str:
    old_root = vault_root.replace("\\", "/").rstrip("/")
    old_source = source_path.replace("\\", "/")
    root_key = old_root.casefold()
    source_key = old_source.casefold()
    if not old_root or not (
        source_key == root_key or source_key.startswith(root_key + "/")
    ):
        raise TrustManifestError("source_outside_manifest_root")
    suffix = old_source[len(old_root) :].lstrip("/")
    if not suffix:
        raise TrustManifestError("source_is_manifest_root")
    parts = suffix.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise TrustManifestError("invalid_canonical_relative_path")
    relative = PurePosixPath(*parts)
    if relative.is_absolute() or relative.as_posix() != suffix:
        raise TrustManifestError("invalid_canonical_relative_path")
    return suffix


def parse_trust_manifest(content: bytes) -> TrustManifest:
    """Parse the supported JSON manifest shape into path-safe metadata."""

    if len(content) > MAX_MANIFEST_BYTES:
        raise TrustManifestError("manifest_too_large")
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustManifestError("invalid_manifest") from exc
    if not isinstance(payload, dict):
        raise TrustManifestError("invalid_manifest")
    vault_root = _required_text(
        _field(payload, "vaultRoot", "vault_root"),
        "missing_vault_root",
        max_length=MAX_SOURCE_PATH,
    )
    has_records = "records" in payload
    has_documents = "documents" in payload
    if has_records == has_documents:
        raise TrustManifestError("invalid_records")
    document_mode = has_documents
    raw_records = payload.get("documents" if document_mode else "records")
    if not isinstance(raw_records, list):
        raise TrustManifestError("invalid_records")
    if len(raw_records) > MAX_MANIFEST_RECORDS:
        raise TrustManifestError("too_many_records")

    entries: list[TrustManifestEntry] = []
    seen: set[str] = set()
    for raw in raw_records:
        if not isinstance(raw, dict):
            raise TrustManifestError("invalid_record")
        manifest_id = _required_text(
            raw.get("id")
            if document_mode
            else _field(raw, "manifestId", "manifest_id"),
            "missing_manifest_id",
        )
        if manifest_id in seen:
            raise TrustManifestError("duplicate_manifest_id")
        seen.add(manifest_id)
        source_path = _required_text(
            _field(raw, "sourcePath", "source_path"),
            "missing_source_path",
            max_length=MAX_SOURCE_PATH,
        )
        approval = raw.get("approval") if document_mode else raw
        if not isinstance(approval, dict):
            raise TrustManifestError("invalid_status")
        status = _field(approval, "status", "status")
        if status != "approved":
            raise TrustManifestError("invalid_status")
        reviewer = _required_text(
            _field(approval, "reviewer", "reviewer"),
            "missing_reviewer",
        )
        reviewed_text = _required_text(
            _field(approval, "reviewedAt", "reviewed_at"),
            "missing_reviewed_at",
        )
        try:
            reviewed_at = datetime.fromisoformat(reviewed_text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise TrustManifestError("invalid_reviewed_at") from exc
        if reviewed_at.tzinfo is None:
            raise TrustManifestError("invalid_reviewed_at")
        source_type = _required_text(
            _field(raw, "sourceType", "source_type"),
            "missing_source_type",
        )
        evidence_class = _field(raw, "evidenceClass", "evidence_class")
        if evidence_class not in {"source", "synthesis"}:
            raise TrustManifestError("invalid_evidence_class")
        content_hash = _required_text(
            _field(raw, "contentHash", "content_hash"),
            "missing_content_hash",
        ).casefold()
        if document_mode and content_hash.startswith("sha256:"):
            content_hash = content_hash.removeprefix("sha256:")
        if not _SHA256.fullmatch(content_hash):
            raise TrustManifestError("invalid_content_hash")
        derived = _field(raw, "derivedFrom", "derived_from")
        if not isinstance(derived, list) or not all(
            isinstance(item, str) and item for item in derived
        ):
            raise TrustManifestError("invalid_derived_from")
        if len(derived) > MAX_DERIVED_FROM:
            raise TrustManifestError("too_many_derived_from")
        if any(len(item) > MAX_SHORT_TEXT for item in derived):
            raise TrustManifestError("derived_from_too_long")
        entries.append(
            TrustManifestEntry(
                manifest_id=manifest_id,
                canonical_relative_path=_relative_suffix(vault_root, source_path),
                status="approved",
                reviewer=reviewer,
                reviewed_at=reviewed_at,
                source_type=source_type,
                evidence_class=evidence_class,
                content_hash=content_hash,
                derived_from=tuple(derived),
            )
        )
    return TrustManifest(entries=tuple(entries))


__all__ = [
    "TrustManifest",
    "TrustManifestEntry",
    "TrustManifestError",
    "parse_trust_manifest",
]
