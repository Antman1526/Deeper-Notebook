"""Bounded, side-effect-free projections for source-derived visual receipts."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from api.schemas.source_visuals import (
    SourceVisualReceiptResponse,
    SourceVisualStatusResponse,
)
from deeper_notebook.source_visuals.contracts import SourceVisualRecord
from deeper_notebook.source_visuals.repository import (
    SourceVisualRepository,
    SourceVisualRepositoryError,
)

_MAX_ROWS = 200
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STATUS_STATES = frozenset({"queued", "processing", "unavailable", "failed"})


@dataclass(frozen=True, slots=True)
class SourceVisualProjection:
    """The only additive visual fields allowed on a source response."""

    visual: SourceVisualReceiptResponse | None = None
    visual_status: SourceVisualStatusResponse | None = None


def visual_asset_url(source_id: str, asset_sha256: str) -> str:
    """Return an immutable opaque asset URL without revealing the cache path."""

    token = hashlib.sha256(f"{source_id}\0{asset_sha256}".encode()).hexdigest()
    return f"/api/sources/{quote(source_id, safe='')}/visual?v={token}"


def _value(row: object, key: str, default: object = None) -> object:
    if isinstance(row, Mapping):
        return row.get(key, default)
    return getattr(row, key, default)


def _datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return (
        result.replace(tzinfo=timezone.utc)
        if result.tzinfo is None
        else result.astimezone(timezone.utc)
    )


def _source_revisions(rows: Sequence[object]) -> dict[str, datetime]:
    revisions: dict[str, datetime] = {}
    for row in rows[:_MAX_ROWS]:
        source_id = _value(row, "id", _value(row, "source_id"))
        updated = _datetime(_value(row, "updated", _value(row, "source_updated_at")))
        if (
            isinstance(source_id, str)
            and source_id.startswith("source:")
            and updated is not None
        ):
            revisions[source_id] = updated
    return revisions


def _receipt(record: SourceVisualRecord) -> SourceVisualReceiptResponse | None:
    try:
        return SourceVisualReceiptResponse(
            source_id=record.source_id,
            content_sha256=record.content_sha256,
            asset_sha256=record.asset_sha256,
            origin=record.origin,
            source_locator=record.source_locator,
            alt_text=record.alt_text,
            width=record.width,
            height=record.height,
            mime_type=record.mime_type,
            asset_url=visual_asset_url(record.source_id, record.asset_sha256),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
    except Exception:
        return None


def _status(value: object) -> SourceVisualStatusResponse | None:
    state = _value(value, "state")
    if state not in _STATUS_STATES:
        return None
    try:
        # Whitelist the public fields rather than dumping worker or DB values.
        return SourceVisualStatusResponse(
            state=state,
            command_id=_value(value, "command_id"),
            error_code=_value(value, "error_code"),
            updated_at=_value(value, "updated_at"),
        )
    except Exception:
        return None


async def project_source_visuals(
    rows: Sequence[object],
    *,
    repository: SourceVisualRepository | object | None = None,
) -> dict[str, SourceVisualProjection]:
    """Batch-project current cache rows once, without hashing source material."""

    revisions = _source_revisions(rows)
    if not revisions:
        return {}
    repo = repository or SourceVisualRepository()
    try:
        current = await repo.list_current(revisions)
    except (SourceVisualRepositoryError, ValueError, TypeError):
        return {}
    if not isinstance(current, Mapping):
        return {}
    statuses = getattr(current, "statuses", {})
    projected: dict[str, SourceVisualProjection] = {}
    for source_id, revision in revisions.items():
        record = current.get(source_id)
        if isinstance(record, SourceVisualRecord):
            if record.source_updated_at != revision:
                continue
            receipt = _receipt(record)
            if receipt is not None:
                projected[source_id] = SourceVisualProjection(visual=receipt)
                continue
        hint = statuses.get(source_id) if isinstance(statuses, Mapping) else None
        status = _status(hint)
        projected[source_id] = SourceVisualProjection(visual_status=status)
    return projected


async def project_search_source_visuals(
    results: Sequence[Mapping[str, Any]],
    *,
    source_rows: Sequence[object],
    repository: SourceVisualRepository | object | None = None,
) -> list[dict[str, Any]]:
    """Add visual fields only to exact source-bearing search result parents."""

    projections = await project_source_visuals(source_rows, repository=repository)
    result: list[dict[str, Any]] = []
    for item in results:
        copied = dict(item)
        # Canonical source hits carry their own id; source-insight hits bind
        # their source through parent_id. Never infer from note metadata.
        source_id = copied.get("id")
        if (
            not (isinstance(source_id, str) and source_id.startswith("source:"))
            and isinstance(copied.get("id"), str)
            and copied["id"].startswith("source_insight:")
        ):
            source_id = copied.get("parent_id")
        if isinstance(source_id, str) and source_id.startswith("source:"):
            projection = projections.get(source_id)
            if projection is not None:
                copied["visual"] = (
                    projection.visual.model_dump(mode="json")
                    if projection.visual is not None
                    else None
                )
                copied["visual_status"] = (
                    projection.visual_status.model_dump(mode="json")
                    if projection.visual_status is not None
                    else None
                )
        result.append(copied)
    return result


async def project_capture_linked_sources(
    items: Sequence[Mapping[str, Any]],
    *,
    repository: SourceVisualRepository | object | None = None,
) -> list[dict[str, Any]]:
    """Link a capture item only to an exact current full-file hash match."""

    values = tuple(
        dict.fromkeys(
            value
            for item in items[:_MAX_ROWS]
            if isinstance((value := item.get("sha256")), str)
            and _SHA256.fullmatch(value)
        )
    )
    copies = [dict(item) for item in items]
    if not values:
        return copies
    repo = repository or SourceVisualRepository()
    try:
        records = await repo.list_current_by_source_file_sha256(values)
    except (SourceVisualRepositoryError, ValueError, TypeError, AttributeError):
        return copies
    by_file_hash: dict[str, SourceVisualRecord] = {}
    for record in records if isinstance(records, Sequence) else ():
        if (
            isinstance(record, SourceVisualRecord)
            and record.source_file_sha256 in values
        ):
            by_file_hash.setdefault(record.source_file_sha256, record)
    for copied in copies:
        file_hash = copied.get("sha256")
        record = by_file_hash.get(file_hash) if isinstance(file_hash, str) else None
        receipt = _receipt(record) if record is not None else None
        if receipt is not None:
            copied["linked_source"] = {
                "id": record.source_id,
                "visual": receipt.model_dump(mode="json"),
            }
    return copies


__all__ = [
    "SourceVisualProjection",
    "project_capture_linked_sources",
    "project_search_source_visuals",
    "project_source_visuals",
    "visual_asset_url",
]
