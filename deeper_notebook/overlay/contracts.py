"""Strict public contracts for app-owned Markdown overlay records."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deeper_notebook.vault.repository import VaultGraph, VaultLink

OverlaySourceAuthority = Literal["overlay"]
OverlayNoteKind = Literal["daily", "unique"]
OverlayProjectionState = Literal["pending", "current", "failed", "conflict"]
OverlayReceiptStatus = Literal[
    "started", "success", "unchanged", "conflict", "failed", "superseded"
]

_HASH = re.compile(r"^[0-9a-f]{64}$")
_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _canonical_relative_path(value: str) -> str:
    parts = value.split("/")
    if (
        value.strip() != value
        or value.startswith(("/", "\\"))
        or "\\" in value
        or "\x00" in value
        or re.match(r"^[A-Za-z]:", value)
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("path must be canonical and relative")
    return value


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OverlaySpace(_Strict):
    id: str = Field(min_length=1, max_length=128)
    slug: Literal["default"] = "default"
    display_name: Literal["Deeper Notebook Overlay"] = "Deeper Notebook Overlay"
    root_version: Literal[1] = 1
    created_at: datetime
    updated_at: datetime


class OverlayNote(_Strict):
    id: str = Field(min_length=1, max_length=128)
    source_authority: OverlaySourceAuthority = "overlay"
    space_id: str = Field(min_length=1, max_length=128)
    projected_note_id: str = Field(min_length=1, max_length=128)
    stable_id: str = Field(min_length=20, max_length=128)
    kind: OverlayNoteKind
    date_key: str | None = Field(default=None, max_length=10)
    relative_path: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=512)
    content_hash: str = Field(min_length=64, max_length=64)
    revision: int = Field(ge=1)
    projection_state: OverlayProjectionState
    encoding: Literal["utf-8"] = "utf-8"
    newline: Literal["lf"] = "lf"
    created_at: datetime
    updated_at: datetime

    @field_validator("content_hash")
    @classmethod
    def hash_is_lower_hex(cls, value: str) -> str:
        if not _HASH.fullmatch(value):
            raise ValueError("content_hash must be lowercase SHA-256")
        return value

    @field_validator("relative_path")
    @classmethod
    def path_is_canonical_relative(cls, value: str) -> str:
        return _canonical_relative_path(value)

    @model_validator(mode="after")
    def kind_matches_date_key(self) -> OverlayNote:
        if self.kind == "daily" and (
            self.date_key is None or not _DATE_KEY.fullmatch(self.date_key)
        ):
            raise ValueError("daily note requires an ISO date_key")
        if self.kind == "unique" and self.date_key is not None:
            raise ValueError("unique note cannot have date_key")
        return self


class OverlayRevision(_Strict):
    id: str
    overlay_note_id: str
    revision: int = Field(ge=1)
    relative_snapshot: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    created_at: datetime

    @field_validator("relative_snapshot")
    @classmethod
    def snapshot_is_canonical_relative(cls, value: str) -> str:
        return _canonical_relative_path(value)


class OverlayMutationReceipt(_Strict):
    id: str
    operation_id: str
    idempotency_key: str = Field(min_length=1, max_length=128)
    overlay_note_id: str | None = None
    operation: Literal["create-daily", "create-unique", "update", "recover"]
    expected_revision: int | None = Field(default=None, ge=1)
    resulting_revision: int | None = Field(default=None, ge=1)
    before_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    after_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status: OverlayReceiptStatus
    error_code: str | None = Field(default=None, max_length=64)
    started_at: datetime
    completed_at: datetime | None = None


class CreateDailyNote(_Strict):
    date_key: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class CreateUniqueNote(_Strict):
    title: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("title")
    @classmethod
    def title_is_visible(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(ord(char) < 32 for char in normalized):
            raise ValueError("title must contain visible text")
        return normalized


class UpdateOverlayNote(_Strict):
    title: str = Field(min_length=1, max_length=512)
    markdown: str = Field(max_length=10 * 1024 * 1024)
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


class OverlayPage(_Strict):
    overlay: OverlayNote
    note: dict[str, Any]
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    outgoing_links: list[VaultLink] = Field(default_factory=list)
    backlinks: list[VaultLink] = Field(default_factory=list)
    graph: VaultGraph | None = None
