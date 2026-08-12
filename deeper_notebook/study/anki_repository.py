"""Atomic publication of inspected Anki cards into native Study authority."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field
from surrealdb import RecordID  # type: ignore[import-untyped]

from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.evaluation.schemas import EvidenceSpan, hash_source_text

from .anki_package import (
    AnkiImportOptions,
    AnkiPackageInspection,
    inspect_anki_package,
)
from .contracts import StudyCard
from .repository import StudyRepository


class AnkiImportRepositoryError(RuntimeError):
    """Safe persistence failure for an inspected import."""


class AnkiImportConflict(AnkiImportRepositoryError):
    """An idempotency or plan authority guard rejected publication."""


class AnkiCompatibilityReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    receipt_id: str = Field(min_length=1, max_length=512)
    plan_id: str = Field(min_length=1, max_length=512)
    request_id: str = Field(min_length=1, max_length=256)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collection_member: Literal["collection.anki2", "collection.anki21"]
    card_count: int = Field(ge=0, le=10_000)
    transformed_count: int = Field(ge=0, le=10_000)
    skipped_count: int = Field(ge=0, le=10_000)
    card_ids: tuple[str, ...] = Field(max_length=10_000)
    deck_names: tuple[str, ...] = Field(max_length=1_000)
    tags: tuple[str, ...] = Field(max_length=1_000)
    media_names: tuple[str, ...] = Field(max_length=500)
    syllabus_unit_id: str | None = Field(default=None, max_length=64)
    created_at: datetime


_RECEIPT_FIELDS = (
    "receipt_id, plan_id, request_id, payload_sha256, package_sha256, "
    "collection_sha256, collection_member, card_count, transformed_count, "
    "skipped_count, card_ids, deck_names, tags, media_names, "
    "syllabus_unit_id, created_at"
)


def _canonical_payload(plan_id: str, inspection: AnkiPackageInspection, options: AnkiImportOptions) -> tuple[str, tuple[Any, ...]]:
    selected = tuple(
        card
        for card in inspection.cards
        if not options.deck_names or card.deck_name in options.deck_names
    )
    if not selected:
        raise AnkiImportRepositoryError("Anki import contains no selected cards")
    payload = {
        "schema_version": 1,
        "plan_id": plan_id,
        "inspection": inspection.model_dump(mode="json"),
        "options": options.model_dump(mode="json"),
        "selected_card_ids": [card.card_id for card in selected],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest(), selected


def _validated_inputs(
    inspection: AnkiPackageInspection, options: AnkiImportOptions
) -> tuple[AnkiPackageInspection, AnkiImportOptions]:
    """Revalidate contracts to close unchecked model-copy/construct seams."""

    try:
        return (
            AnkiPackageInspection.model_validate(
                inspection.model_dump(mode="python")
            ),
            AnkiImportOptions.model_validate(options.model_dump(mode="python")),
        )
    except Exception as exc:
        raise AnkiImportRepositoryError("Invalid Anki import payload") from exc


def _flatten(value: object) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if "result" in value and len(value) <= 3:
            return _flatten(value["result"])
        return [value]
    if isinstance(value, (list, tuple)):
        rows: list[dict[str, Any]] = []
        for item in value:
            rows.extend(_flatten(item))
        return rows
    return []


def _receipt_from(value: object) -> AnkiCompatibilityReceipt | None:
    rows = _flatten(value)
    for row in rows[:4]:
        if "request_id" in row and "payload_sha256" in row:
            try:
                decoded = {
                    field: row[field]
                    for field in AnkiCompatibilityReceipt.model_fields
                    if field in row
                }
                # SurrealDB decodes array fields as lists.  The public receipt
                # contract deliberately keeps them immutable tuples, so adapt
                # only those known projection fields before strict validation.
                for field in ("card_ids", "deck_names", "tags", "media_names"):
                    if isinstance(decoded.get(field), list):
                        decoded[field] = tuple(decoded[field])
                return AnkiCompatibilityReceipt.model_validate(
                    decoded
                )
            except Exception as exc:
                raise AnkiImportRepositoryError("Invalid persisted Anki import receipt") from exc
    return None


class AnkiImportRepository:
    async def _find_by_request(self, plan_id: str, request_id: str) -> AnkiCompatibilityReceipt | None:
        rows = await repo_query(
            f"SELECT {_RECEIPT_FIELDS} FROM study_anki_import "
            "WHERE plan_id = $plan_id AND request_id = $request_id LIMIT 1;",
            {"plan_id": plan_id, "request_id": request_id},
        )
        return _receipt_from(rows)

    async def _find_by_payload(self, plan_id: str, payload_sha256: str) -> AnkiCompatibilityReceipt | None:
        rows = await repo_query(
            f"SELECT {_RECEIPT_FIELDS} FROM study_anki_import "
            "WHERE plan_id = $plan_id AND payload_sha256 = $payload_sha256 LIMIT 1;",
            {"plan_id": plan_id, "payload_sha256": payload_sha256},
        )
        return _receipt_from(rows)

    async def find_by_receipt(self, plan_id: str, receipt_id: str) -> AnkiCompatibilityReceipt | None:
        rows = await repo_query(
            f"SELECT {_RECEIPT_FIELDS} FROM study_anki_import "
            "WHERE plan_id = $plan_id AND receipt_id = $receipt_id LIMIT 1;",
            {"plan_id": plan_id, "receipt_id": receipt_id},
        )
        return _receipt_from(rows)

    async def publish(
        self,
        plan_id: str,
        inspection: AnkiPackageInspection,
        options: AnkiImportOptions,
        request_id: str,
    ) -> AnkiCompatibilityReceipt:
        if (
            not isinstance(plan_id, str)
            or not plan_id.strip()
            or plan_id != plan_id.strip()
            or len(plan_id) > 512
            or any(ord(char) < 32 or ord(char) == 127 for char in plan_id)
        ):
            raise AnkiImportRepositoryError("Invalid Study Plan ID")
        try:
            plan_record = ensure_record_id(plan_id)
        except Exception as exc:
            raise AnkiImportRepositoryError("Invalid Study Plan ID") from exc
        if (
            getattr(plan_record, "table_name", None) != "study_plan"
            or not isinstance(getattr(plan_record, "id", None), str)
            or not getattr(plan_record, "id").strip()
        ):
            raise AnkiImportRepositoryError("Invalid Study Plan ID")
        canonical_plan_id = str(plan_record)
        if (
            not isinstance(request_id, str)
            or not request_id.strip()
            or request_id != request_id.strip()
            or len(request_id) > 256
            or any(ord(char) < 32 or ord(char) == 127 for char in request_id)
        ):
            raise AnkiImportRepositoryError("Invalid Anki import request ID")
        inspection, options = _validated_inputs(inspection, options)
        payload_sha256, selected = _canonical_payload(
            canonical_plan_id, inspection, options
        )
        try:
            existing = await self._find_by_request(canonical_plan_id, request_id)
            if existing is not None:
                if existing.payload_sha256 != payload_sha256:
                    raise AnkiImportConflict("Anki import request ID was already used")
                return existing
            same_payload = await self._find_by_payload(
                canonical_plan_id, payload_sha256
            )
            if same_payload is not None:
                return same_payload

            token = hashlib.sha256(
                f"{canonical_plan_id}|{payload_sha256}".encode()
            ).hexdigest()
            receipt_id = f"study_anki_import:{token}"
            now = datetime.now(UTC)
            card_ids: list[str] = []
            params: dict[str, Any] = {
                "plan": plan_record,
                "plan_id": canonical_plan_id,
                "request_id": request_id,
                "payload_sha256": payload_sha256,
                "receipt_record": RecordID("study_anki_import", token),
            }
            fragments = [
                "BEGIN TRANSACTION; ",
                "LET $plan_guard = SELECT VALUE active_syllabus_version FROM ONLY $plan "
                "WHERE state IN ['approved', 'generating', 'active', 'completed'] "
                "AND active_syllabus_version != NONE; ",
                "IF $plan_guard = NONE { THROW 'study_anki_plan_guard_failed'; }; ",
            ]
            if options.syllabus_unit_id is not None:
                params["syllabus_unit_id"] = options.syllabus_unit_id
                fragments.extend(
                    [
                        "LET $unit_guard = SELECT VALUE id FROM study_unit "
                        "WHERE plan_id = $plan_id "
                        "AND syllabus_version = $plan_guard "
                        "AND unit_id = $syllabus_unit_id LIMIT 1; ",
                        "IF array::len($unit_guard) != 1 { "
                        "THROW 'study_anki_unit_guard_failed'; }; ",
                    ]
                )
            for index, preview in enumerate(selected):
                snapshot = f"{preview.front}\n{preview.back}"[:1200]
                snapshot_hash = hash_source_text(snapshot)
                # Preserve the bounded native note kind for Task 16 export.
                # Basic keeps the historical identifier; transformed cards
                # carry an explicit finite marker in the opaque artifact ID.
                artifact_card_id = (
                    f"anki_card:{preview.card_id}"
                    if preview.kind == "basic"
                    else f"anki_card:{preview.kind}:{preview.card_id}"
                )
                card_token = hashlib.sha256(
                    f"{canonical_plan_id}|{payload_sha256}|{artifact_card_id}".encode()
                ).hexdigest()
                record = RecordID("study_card", f"anki_{card_token}")
                native = StudyCard(
                    artifact_id=f"anki_import:{inspection.package_sha256}",
                    artifact_card_id=artifact_card_id,
                    front=preview.front,
                    back=preview.back,
                    citations=[
                        EvidenceSpan(
                            source_id=f"anki_package:{inspection.package_sha256}",
                            source_content_sha256=snapshot_hash,
                            start=0,
                            end=len(snapshot),
                            quote=snapshot,
                        )
                    ],
                )
                params[f"card_record_{index}"] = record
                params[f"card_{index}"] = StudyRepository._card_data(native)
                params[f"link_{index}"] = {
                    "plan_id": canonical_plan_id,
                    "card_id": str(record),
                    "syllabus_unit_id": options.syllabus_unit_id,
                    "created_at": now,
                }
                source_fields = preview.source_fields or (preview.front, preview.back)
                params[f"compat_{index}"] = {
                    "plan_id": canonical_plan_id,
                    "card_id": str(record),
                    "source_note_id": preview.source_note_id or preview.note_id,
                    "source_model_kind": preview.source_model_kind or (
                        "cloze" if preview.kind == "cloze" else "basic"
                    ),
                    "template_ord": preview.template_ord if preview.template_ord is not None else 0,
                    "kind": preview.kind,
                    "source_fields": list(source_fields),
                    "deck_name": preview.deck_name,
                    "tags": list(preview.tags),
                    "package_sha256": inspection.package_sha256,
                    "created_at": now,
                }
                fragments.extend(
                    [
                        f"LET $card_guard_{index} = SELECT VALUE id FROM ONLY $card_record_{index}; ",
                        f"IF $card_guard_{index} != NONE {{ THROW 'study_anki_card_conflict'; }}; ",
                        f"CREATE $card_record_{index} CONTENT $card_{index}; ",
                        f"CREATE study_plan_card CONTENT $link_{index}; ",
                        f"CREATE study_anki_card_compat CONTENT $compat_{index}; ",
                    ]
                )
                card_ids.append(str(record))
            receipt = AnkiCompatibilityReceipt(
                receipt_id=receipt_id,
                plan_id=canonical_plan_id,
                request_id=request_id,
                payload_sha256=payload_sha256,
                package_sha256=inspection.package_sha256,
                collection_sha256=inspection.collection_sha256,
                collection_member=inspection.collection_member,
                card_count=len(selected),
                transformed_count=sum(card.kind != "basic" for card in selected),
                skipped_count=inspection.skipped_count + len(inspection.cards) - len(selected),
                card_ids=tuple(card_ids),
                deck_names=tuple(sorted({card.deck_name for card in selected})),
                tags=tuple(sorted({tag for card in selected for tag in card.tags}))[:1_000],
                media_names=tuple(sorted({name for card in selected for name in card.media_names})),
                syllabus_unit_id=options.syllabus_unit_id,
                created_at=now,
            )
            params["receipt"] = receipt.model_dump(mode="python")
            fragments.extend(
                [
                    "CREATE $receipt_record CONTENT $receipt; ",
                    "COMMIT TRANSACTION; ",
                    "RETURN $receipt;",
                ]
            )
            result = await repo_query("".join(fragments), params)
            persisted = _receipt_from(result)
            if persisted is not None:
                return persisted
            persisted = await self._find_by_request(
                canonical_plan_id, request_id
            )
            if persisted is None or persisted.payload_sha256 != payload_sha256:
                raise AnkiImportRepositoryError("Anki import did not persist")
            return persisted
        except AnkiImportConflict:
            raise
        except AnkiImportRepositoryError:
            raise
        except Exception as exc:
            try:
                replay = await self._find_by_request(
                    canonical_plan_id, request_id
                )
                if replay is not None:
                    if replay.payload_sha256 == payload_sha256:
                        return replay
                    raise AnkiImportConflict("Anki import request ID was already used")
                replay = await self._find_by_payload(
                    canonical_plan_id, payload_sha256
                )
                if replay is not None:
                    return replay
            except AnkiImportConflict:
                raise
            except Exception:
                pass
            logger.exception("Failed to publish Anki import")
            raise AnkiImportRepositoryError("Anki import is unavailable") from exc


async def import_anki_package(
    plan_id: str,
    path: str | os.PathLike[str],
    options: AnkiImportOptions,
    request_id: str,
) -> AnkiCompatibilityReceipt:
    inspection = inspect_anki_package(path)
    return await AnkiImportRepository().publish(plan_id, inspection, options, request_id)


__all__ = [
    "AnkiCompatibilityReceipt",
    "AnkiImportConflict",
    "AnkiImportRepository",
    "AnkiImportRepositoryError",
    "import_anki_package",
]
