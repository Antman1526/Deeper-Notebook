"""Durable metadata for bounded Anki import and export jobs.

The archive bytes remain in task-owned application storage.  SurrealDB stores
only bounded projections, opaque file tokens, hashes, and publication state so
status and download requests can be rehydrated by a fresh worker.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from surrealdb import RecordID  # type: ignore[import-untyped]

from deeper_notebook.database.repository import ensure_record_id, repo_query

JOB_TTL = timedelta(hours=24)
EXPORT_TTL = timedelta(hours=24)
CLAIM_TTL = timedelta(minutes=10)
MAX_METADATA_ROWS = 256
_HEX64 = r"^[a-f0-9]{64}$"


class AnkiJobMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    job_id: str = Field(pattern=r"^anki_job:[a-f0-9]{64}$")
    plan_id: str = Field(min_length=1, max_length=512)
    file_token: str = Field(pattern=r"^upload-[a-f0-9]{64}\.apkg$")
    package_sha256: str = Field(pattern=_HEX64)
    collection_sha256: str = Field(pattern=_HEX64)
    collection_member: Literal["collection.anki2", "collection.anki21"]
    card_count: int = Field(ge=0, le=10_000)
    transformed_count: int = Field(ge=0, le=10_000)
    skipped_count: int = Field(ge=0, le=10_000)
    rejected_count: int = Field(ge=0, le=10_000)
    status: Literal[
        "preview_ready", "processing", "publishing", "failed", "cancelled", "published"
    ] = "preview_ready"
    claim_request_id: str | None = Field(default=None, max_length=256)
    claim_options_sha256: str | None = Field(default=None, pattern=_HEX64)
    claim_package_sha256: str | None = Field(default=None, pattern=_HEX64)
    claim_payload_sha256: str | None = Field(default=None, pattern=_HEX64)
    claim_owner_token: str | None = Field(default=None, pattern=_HEX64)
    claim_expires_at: datetime | None = None
    receipt_id: str | None = Field(default=None, max_length=512)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class AnkiExportMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    download_id: str = Field(pattern=r"^anki_download:[a-f0-9]{64}$")
    plan_id: str = Field(min_length=1, max_length=512)
    file_token: str = Field(pattern=r"^export-[a-f0-9]{64}\.apkg$")
    plan_revision: int = Field(ge=1)
    syllabus_version: int = Field(ge=1)
    package_sha256: str = Field(pattern=_HEX64)
    receipt_id: str = Field(min_length=1, max_length=512)
    card_count: int = Field(ge=0, le=10_000)
    stable_note_guids: tuple[str, ...] = Field(max_length=10_000)
    stable_model_ids: tuple[int, ...] = Field(max_length=16)
    stable_deck_ids: tuple[int, ...] = Field(max_length=1_000)
    created_at: datetime
    expires_at: datetime


class AnkiMetadataCapacityError(RuntimeError):
    """The bounded durable metadata table has reached its active-row cap."""


async def _active_job_count() -> int | None:
    try:
        rows = await repo_query(
            "SELECT count() AS total FROM study_anki_job "
            "WHERE expires_at > time::now() GROUP ALL;"
        )
        total = rows[0].get("total", 0) if rows else 0
        return total if isinstance(total, int) else None
    except Exception:
        return None


async def _active_export_count() -> int | None:
    try:
        rows = await repo_query(
            "SELECT count() AS total FROM study_anki_export "
            "WHERE expires_at > time::now() GROUP ALL;"
        )
        total = rows[0].get("total", 0) if rows else 0
        return total if isinstance(total, int) else None
    except Exception:
        return None


def _rows(value: object) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if "result" in value and len(value) <= 3:
            return _rows(value["result"])
        return [value]
    if isinstance(value, (list, tuple)):
        flattened: list[dict[str, Any]] = []
        for item in value:
            flattened.extend(_rows(item))
        return flattened
    return []


def _tuple_fields(row: dict[str, Any]) -> dict[str, Any]:
    for field in ("stable_note_guids", "stable_model_ids", "stable_deck_ids"):
        if isinstance(row.get(field), list):
            row[field] = tuple(row[field])
    return row


def _metadata(value: object, model: type[BaseModel]) -> BaseModel | None:
    rows = _rows(value)
    if not rows:
        return None
    row = _tuple_fields(dict(rows[0]))
    allowed = set(model.model_fields)
    row = {key: value for key, value in row.items() if key in allowed}
    # Surreal's datetime values are usually native; accept its ISO projection
    # when a worker crosses a process/client boundary.
    for field in ("created_at", "updated_at", "expires_at", "claim_expires_at"):
        if isinstance(row.get(field), str):
            row[field] = datetime.fromisoformat(row[field].replace("Z", "+00:00"))
        if isinstance(row.get(field), datetime) and row[field].tzinfo is None:
            row[field] = row[field].replace(tzinfo=UTC)
    return model.model_validate(row)


def _canonical_record(table: str, value: str):
    try:
        if (
            table == "study_anki_job"
            and isinstance(value, str)
            and value.startswith("anki_job:")
        ):
            record = RecordID(table, value.split(":", 1)[1])
        elif (
            table == "study_anki_export"
            and isinstance(value, str)
            and value.startswith("anki_download:")
        ):
            record = RecordID(table, value.split(":", 1)[1])
        else:
            record = ensure_record_id(value)
    except Exception as exc:
        raise ValueError("invalid Anki metadata ID") from exc
    if getattr(record, "table_name", None) != table:
        raise ValueError("invalid Anki metadata ID")
    return record


class AnkiJobRepository:
    """Persistence and atomic claim boundary for import jobs."""

    async def create(self, metadata: AnkiJobMetadata) -> AnkiJobMetadata:
        now = datetime.now(UTC)
        value = metadata.model_copy(update={"created_at": now, "updated_at": now})
        try:
            result = await repo_query(
                "BEGIN TRANSACTION; "
                "LET $active = SELECT count() AS total FROM study_anki_job "
                "WHERE expires_at > time::now() GROUP ALL; "
                "IF $active[0].total >= $limit { THROW 'study_anki_job_capacity'; }; "
                "CREATE $job_record CONTENT $job; COMMIT TRANSACTION; RETURN $job;",
                {
                    "job_record": _canonical_record("study_anki_job", value.job_id),
                    "job": value.model_dump(mode="python"),
                    "limit": MAX_METADATA_ROWS,
                },
            )
        except Exception as exc:
            if "study_anki_job_capacity" in str(exc):
                raise AnkiMetadataCapacityError("study_anki_job_capacity") from exc
            total = await _active_job_count()
            if total is not None and total >= MAX_METADATA_ROWS:
                raise AnkiMetadataCapacityError("study_anki_job_capacity") from exc
            raise
        persisted = _metadata(result, AnkiJobMetadata)
        if persisted is None:
            persisted = await self.get(value.job_id, value.plan_id)
        if persisted is None:
            raise RuntimeError("Anki import job did not persist")
        return persisted

    async def get(self, job_id: str, plan_id: str) -> AnkiJobMetadata | None:
        rows = await repo_query(
            "SELECT schema_version, job_id, plan_id, file_token, package_sha256, "
            "collection_sha256, collection_member, card_count, transformed_count, "
            "skipped_count, rejected_count, status, claim_request_id, "
            "claim_options_sha256, claim_package_sha256, claim_payload_sha256, claim_owner_token, "
            "claim_expires_at, receipt_id, created_at, updated_at, expires_at "
            "FROM $job WHERE job_id = $job_id AND plan_id = $plan_id LIMIT 1;",
            {
                "job": _canonical_record("study_anki_job", job_id),
                "job_id": job_id,
                "plan_id": plan_id,
            },
        )
        return _metadata(rows, AnkiJobMetadata)  # type: ignore[return-value]

    async def claim(
        self,
        job_id: str,
        plan_id: str,
        package_sha256: str,
        request_id: str,
        options_sha256: str,
        payload_sha256: str,
    ) -> "AnkiClaimResult":
        """Atomically bind request/options/package/payload to one job.

        The owner token distinguishes the first claimant from a same-request
        retry without exposing it through the API.  A different request or
        options hash can never replace an existing claim.
        """
        owner_token = secrets.token_hex(32)
        record = _canonical_record("study_anki_job", job_id)
        updated = await repo_query(
            "UPDATE $job SET claim_request_id = $request_id, "
            "claim_options_sha256 = $options_sha256, claim_package_sha256 = $package_sha256, "
            "claim_payload_sha256 = $payload_sha256, "
            "claim_owner_token = $owner_token, claim_expires_at = $claim_expires_at, "
            "status = 'publishing', updated_at = time::now() "
            "WHERE plan_id = $plan_id AND package_sha256 = $package_sha256 "
            "AND (claim_request_id = NONE OR "
            "(claim_request_id = $request_id AND claim_options_sha256 = $options_sha256 "
            "AND claim_payload_sha256 = $payload_sha256 "
            "AND status IN ['failed', 'cancelled']) OR "
            "(claim_expires_at != NONE AND claim_expires_at <= time::now() "
            "AND claim_request_id = $request_id AND claim_options_sha256 = $options_sha256 "
            "AND claim_payload_sha256 = $payload_sha256)) "
            "AND status IN ['preview_ready', 'processing', 'publishing', 'failed', 'cancelled'] "
            "RETURN AFTER;",
            {
                "job": record,
                "plan_id": plan_id,
                "package_sha256": package_sha256,
                "request_id": request_id,
                "options_sha256": options_sha256,
                "payload_sha256": payload_sha256,
                "owner_token": owner_token,
                "claim_expires_at": datetime.now(UTC) + CLAIM_TTL,
            },
        )
        row = _metadata(updated, AnkiJobMetadata)
        if row is not None:
            return (
                AnkiClaimResult("owner", owner_token)
                if row.claim_owner_token == owner_token
                else AnkiClaimResult("replay")
            )
        current = await self.get(job_id, plan_id)
        if current is None:
            return AnkiClaimResult("missing")
        if (
            current.status == "published"
            and current.package_sha256 == package_sha256
            and current.claim_package_sha256 == package_sha256
            and current.claim_request_id == request_id
            and current.claim_options_sha256 == options_sha256
            and current.claim_payload_sha256 == payload_sha256
        ):
            return AnkiClaimResult("replay")
        if (
            current.package_sha256 == package_sha256
            and current.claim_package_sha256 == package_sha256
            and current.claim_request_id == request_id
            and current.claim_options_sha256 == options_sha256
            and current.claim_payload_sha256 == payload_sha256
        ):
            return AnkiClaimResult("replay")
        return AnkiClaimResult("conflict")

    async def complete(
        self,
        job_id: str,
        plan_id: str,
        request_id: str,
        options_sha256: str,
        receipt_id: str,
        owner_token: str,
        *,
        package_sha256: str,
        payload_sha256: str,
    ) -> AnkiJobMetadata | None:
        result = await repo_query(
            "UPDATE $job SET status = 'published', receipt_id = $receipt_id, "
            "updated_at = time::now() WHERE plan_id = $plan_id "
            "AND package_sha256 = $package_sha256 "
            "AND claim_request_id = $request_id AND claim_options_sha256 = $options_sha256 "
            "AND claim_package_sha256 = $package_sha256 "
            "AND claim_payload_sha256 = $payload_sha256 "
            "AND claim_owner_token = $owner_token AND claim_expires_at > time::now() "
            "AND status = 'publishing' "
            "RETURN AFTER;",
            {
                "job": _canonical_record("study_anki_job", job_id),
                "plan_id": plan_id,
                "package_sha256": package_sha256,
                "request_id": request_id,
                "options_sha256": options_sha256,
                "payload_sha256": payload_sha256,
                "receipt_id": receipt_id,
                "owner_token": owner_token,
            },
        )
        return _metadata(result, AnkiJobMetadata)  # type: ignore[return-value]

    async def fail(
        self,
        job_id: str,
        plan_id: str,
        request_id: str,
        options_sha256: str,
        owner_token: str,
        *,
        package_sha256: str,
        payload_sha256: str,
    ) -> AnkiJobMetadata | None:
        result = await repo_query(
            "UPDATE $job SET status = 'failed', updated_at = time::now() "
            "WHERE plan_id = $plan_id AND package_sha256 = $package_sha256 "
            "AND claim_request_id = $request_id "
            "AND claim_options_sha256 = $options_sha256 AND claim_owner_token = $owner_token "
            "AND claim_package_sha256 = $package_sha256 "
            "AND claim_payload_sha256 = $payload_sha256 "
            "AND claim_expires_at > time::now() AND status = 'publishing' "
            "RETURN AFTER;",
            {
                "job": _canonical_record("study_anki_job", job_id),
                "plan_id": plan_id,
                "package_sha256": package_sha256,
                "request_id": request_id,
                "options_sha256": options_sha256,
                "payload_sha256": payload_sha256,
                "owner_token": owner_token,
            },
        )
        return _metadata(result, AnkiJobMetadata)  # type: ignore[return-value]

    async def list_expired(
        self, *, limit: int = MAX_METADATA_ROWS
    ) -> tuple[tuple[str, str], ...]:
        """List bounded expired job rows before two-phase file cleanup."""
        bounded = max(1, min(int(limit), MAX_METADATA_ROWS))
        rows = await repo_query(
            "SELECT job_id, file_token, expires_at FROM study_anki_job WHERE expires_at <= time::now() "
            "ORDER BY expires_at LIMIT $limit;",
            {"limit": bounded},
        )
        return tuple(
            (row["job_id"], row["file_token"])
            for row in _rows(rows)
            if isinstance(row.get("job_id"), str)
            and isinstance(row.get("file_token"), str)
        )

    async def delete_expired(self, job_id: str) -> bool:
        """Delete one row only while it remains expired."""
        deleted = await repo_query(
            "DELETE $job WHERE expires_at <= time::now() RETURN BEFORE;",
            {"job": _canonical_record("study_anki_job", job_id)},
        )
        return bool(_rows(deleted))

    async def has_file_token(self, file_token: str) -> bool:
        rows = await repo_query(
            "SELECT file_token FROM study_anki_job WHERE file_token = $file_token LIMIT 1;",
            {"file_token": file_token},
        )
        return bool(_rows(rows))


class AnkiExportRepository:
    """Durable opaque download metadata; package bytes stay on disk."""

    async def create(self, metadata: AnkiExportMetadata) -> AnkiExportMetadata:
        try:
            result = await repo_query(
                "BEGIN TRANSACTION; "
                "LET $active = SELECT count() AS total FROM study_anki_export "
                "WHERE expires_at > time::now() GROUP ALL; "
                "IF $active[0].total >= $limit { THROW 'study_anki_export_capacity'; }; "
                "CREATE $export_record CONTENT $export; COMMIT TRANSACTION; RETURN $export;",
                {
                    "export_record": _canonical_record(
                        "study_anki_export", metadata.download_id
                    ),
                    "export": metadata.model_dump(mode="python"),
                    "limit": MAX_METADATA_ROWS,
                },
            )
        except Exception as exc:
            if "study_anki_export_capacity" in str(exc):
                raise AnkiMetadataCapacityError("study_anki_export_capacity") from exc
            total = await _active_export_count()
            if total is not None and total >= MAX_METADATA_ROWS:
                raise AnkiMetadataCapacityError("study_anki_export_capacity") from exc
            raise
        persisted = _metadata(result, AnkiExportMetadata)
        if persisted is None:
            persisted = await self.get(metadata.download_id)
        if persisted is None:
            raise RuntimeError("Anki export metadata did not persist")
        return persisted

    async def get(self, download_id: str) -> AnkiExportMetadata | None:
        rows = await repo_query(
            "SELECT schema_version, download_id, plan_id, file_token, plan_revision, "
            "syllabus_version, package_sha256, receipt_id, card_count, stable_note_guids, "
            "stable_model_ids, stable_deck_ids, created_at, expires_at "
            "FROM $export WHERE download_id = $download_id LIMIT 1;",
            {
                "export": _canonical_record("study_anki_export", download_id),
                "download_id": download_id,
            },
        )
        return _metadata(rows, AnkiExportMetadata)  # type: ignore[return-value]

    async def list_expired(
        self, *, limit: int = MAX_METADATA_ROWS
    ) -> tuple[tuple[str, str], ...]:
        """List bounded expired export rows before two-phase file cleanup."""
        bounded = max(1, min(int(limit), MAX_METADATA_ROWS))
        rows = await repo_query(
            "SELECT download_id, file_token, expires_at FROM study_anki_export WHERE expires_at <= time::now() "
            "ORDER BY expires_at LIMIT $limit;",
            {"limit": bounded},
        )
        return tuple(
            (row["download_id"], row["file_token"])
            for row in _rows(rows)
            if isinstance(row.get("download_id"), str)
            and isinstance(row.get("file_token"), str)
        )

    async def delete_expired(self, download_id: str) -> bool:
        """Delete one row only while it remains expired."""
        deleted = await repo_query(
            "DELETE $export WHERE expires_at <= time::now() RETURN BEFORE;",
            {"export": _canonical_record("study_anki_export", download_id)},
        )
        return bool(_rows(deleted))

    async def has_file_token(self, file_token: str) -> bool:
        rows = await repo_query(
            "SELECT file_token FROM study_anki_export WHERE file_token = $file_token LIMIT 1;",
            {"file_token": file_token},
        )
        return bool(_rows(rows))


__all__ = [
    "AnkiExportMetadata",
    "AnkiExportRepository",
    "AnkiJobMetadata",
    "AnkiJobRepository",
    "AnkiMetadataCapacityError",
    "EXPORT_TTL",
    "JOB_TTL",
    "MAX_METADATA_ROWS",
]


class AnkiClaimResult(str):
    """String-compatible decision carrying an owner fence when claimed."""

    def __new__(cls, decision: str, owner_token: str | None = None):
        value = str.__new__(cls, decision)
        value.owner_token = owner_token  # type: ignore[attr-defined]
        return value

    owner_token: str | None
