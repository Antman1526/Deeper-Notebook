"""Strict, metadata-only HTTP contracts for Study Anki portability."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _visible(value: str, *, maximum: int, field_name: str) -> str:
    if value != value.strip() or not value or len(value) > maximum:
        raise ValueError(f"{field_name} must be bounded visible text")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{field_name} must be bounded visible text")
    return value


class AnkiHttpOptions(_Strict):
    schema_version: Literal[1] = 1
    syllabus_unit_id: StrictStr | None = Field(default=None, max_length=64)
    deck_names: tuple[StrictStr, ...] = Field(default_factory=tuple, max_length=100)

    @field_validator("syllabus_unit_id")
    @classmethod
    def unit_id_is_safe(cls, value: str | None) -> str | None:
        if value is not None:
            _visible(value, maximum=64, field_name="syllabus_unit_id")
            if not value[0].islower() and not value[0].isdigit():
                raise ValueError("invalid syllabus_unit_id")
            if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in value):
                raise ValueError("invalid syllabus_unit_id")
        return value

    @field_validator("deck_names", mode="before")
    @classmethod
    def tuple_deck_names(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("deck_names")
    @classmethod
    def deck_names_are_safe(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("duplicate deck_names")
        for value in values:
            _visible(value, maximum=200, field_name="deck_name")
        return values


class AnkiImportPublishRequest(_Strict):
    upload_id: StrictStr = Field(min_length=1, max_length=128)
    request_id: StrictStr = Field(min_length=1, max_length=256)
    options: AnkiHttpOptions = Field(default_factory=AnkiHttpOptions)

    @field_validator("upload_id", "request_id")
    @classmethod
    def ids_are_safe(cls, value: str, info: object) -> str:
        return _visible(value, maximum=256, field_name=str(getattr(info, "field_name", "id")))


class AnkiImportPreviewResponse(_Strict):
    schema_version: Literal[1] = 1
    job_id: StrictStr = Field(min_length=1, max_length=128)
    status: Literal["preview_ready", "processing", "failed", "published"]
    card_count: StrictInt = Field(ge=0, le=10_000)
    transformed_count: StrictInt = Field(ge=0, le=10_000)
    skipped_count: StrictInt = Field(ge=0, le=10_000)
    rejected_count: StrictInt = Field(ge=0, le=10_000)
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collection_member: Literal["collection.anki2", "collection.anki21"]
    message: str | None = Field(default=None, max_length=200)


class AnkiImportStatusResponse(AnkiImportPreviewResponse):
    receipt_id: str | None = Field(default=None, max_length=512)


class AnkiCompatibilityReceiptResponse(_Strict):
    schema_version: Literal[1] = 1
    receipt_id: str = Field(min_length=1, max_length=512)
    plan_id: str = Field(min_length=1, max_length=512)
    request_id: str = Field(min_length=1, max_length=256)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collection_member: Literal["collection.anki2", "collection.anki21"]
    card_count: StrictInt = Field(ge=0, le=10_000)
    transformed_count: StrictInt = Field(ge=0, le=10_000)
    skipped_count: StrictInt = Field(ge=0, le=10_000)
    card_ids: tuple[str, ...] = Field(max_length=10_000)
    deck_names: tuple[str, ...] = Field(max_length=1_000)
    tags: tuple[str, ...] = Field(max_length=1_000)
    media_names: tuple[str, ...] = Field(max_length=500)
    syllabus_unit_id: str | None = Field(default=None, max_length=64)
    created_at: datetime


class AnkiImportPublishResponse(_Strict):
    schema_version: Literal[1] = 1
    status: Literal["published", "replayed"]
    receipt: AnkiCompatibilityReceiptResponse


class AnkiExportRequest(_Strict):
    schema_version: Literal[1] = 1
    options: AnkiHttpOptions = Field(default_factory=AnkiHttpOptions)


class AnkiExportReceipt(_Strict):
    schema_version: Literal[1] = 1
    receipt_id: str = Field(min_length=1, max_length=512)
    plan_id: str = Field(min_length=1, max_length=512)
    plan_revision: StrictInt = Field(ge=1)
    syllabus_version: StrictInt = Field(ge=1)
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    card_count: StrictInt = Field(ge=0, le=10_000)
    stable_note_guids: tuple[str, ...] = Field(max_length=10_000)
    stable_model_ids: tuple[StrictInt, ...] = Field(max_length=16)
    stable_deck_ids: tuple[StrictInt, ...] = Field(max_length=1_000)
    created_at: datetime


class AnkiExportResponse(_Strict):
    schema_version: Literal[1] = 1
    download_id: str = Field(min_length=1, max_length=128)
    receipt: AnkiExportReceipt


__all__ = [
    "AnkiCompatibilityReceiptResponse",
    "AnkiExportReceipt",
    "AnkiExportRequest",
    "AnkiExportResponse",
    "AnkiHttpOptions",
    "AnkiImportPreviewResponse",
    "AnkiImportPublishRequest",
    "AnkiImportPublishResponse",
    "AnkiImportStatusResponse",
]
