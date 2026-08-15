"""Strict HTTP contracts for source-derived visual operations and receipts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deeper_notebook.source_visuals.contracts import (
    SHA256,
    SourceVisualLocator,
    SourceVisualOrigin,
    validate_source_visual_origin_locator,
)

ERROR_CODE = r"^[a-z0-9][a-z0-9_.-]{0,63}$"
SourceVisualStatusState = Literal[
    "queued", "processing", "unavailable", "failed"
]
SourceVisualOperationOutcome = Literal["queued", "replayed", "deleted", "failed"]


class _StrictSourceVisualSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceVisualRefreshRequest(_StrictSourceVisualSchema):
    request_id: str = Field(min_length=1, max_length=256)


class SourceVisualDeleteRequest(_StrictSourceVisualSchema):
    request_id: str = Field(min_length=1, max_length=256)


class SourceVisualReceiptResponse(_StrictSourceVisualSchema):
    source_id: str = Field(min_length=1, max_length=512)
    content_sha256: str = Field(pattern=SHA256)
    asset_sha256: str = Field(pattern=SHA256)
    origin: SourceVisualOrigin
    source_locator: SourceVisualLocator
    alt_text: str = Field(min_length=1, max_length=300)
    width: int = Field(ge=1, le=1280)
    height: int = Field(ge=1, le=720)
    mime_type: Literal["image/webp"] = "image/webp"
    asset_url: str = Field(min_length=1, max_length=4096)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def origin_matches_source_locator(self) -> "SourceVisualReceiptResponse":
        validate_source_visual_origin_locator(self.origin, self.source_locator)
        return self


class SourceVisualStatusResponse(_StrictSourceVisualSchema):
    state: SourceVisualStatusState
    command_id: str | None = Field(default=None, min_length=1, max_length=512)
    error_code: str | None = Field(
        default=None, pattern=ERROR_CODE, max_length=64
    )
    updated_at: datetime


class SourceVisualJobResponse(_StrictSourceVisualSchema):
    source_id: str = Field(min_length=1, max_length=512)
    command_id: str | None = Field(default=None, min_length=1, max_length=512)
    content_sha256: str = Field(pattern=SHA256)
    asset_sha256: str | None = Field(default=None, pattern=SHA256)
    origin: SourceVisualOrigin | None = None
    width: int | None = Field(default=None, ge=1, le=1280)
    height: int | None = Field(default=None, ge=1, le=720)
    duration_ms: int | None = Field(default=None, ge=0, le=60_000)
    outcome: SourceVisualOperationOutcome
    error_code: str | None = Field(
        default=None, pattern=ERROR_CODE, max_length=64
    )
