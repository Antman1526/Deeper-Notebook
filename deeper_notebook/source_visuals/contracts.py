"""Strict internal contracts for source-derived visual metadata and jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SHA256 = r"^[0-9a-f]{64}$"
SourceVisualOrigin = Literal["embedded", "video_frame", "audio_artwork"]
SourceVisualOperation = Literal["refresh", "delete"]
SourceVisualOutcome = Literal["queued", "replayed", "deleted", "failed"]
SourceVisualState = Literal["queued", "processing", "unavailable", "failed"]


class SourceVisualLocator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page: int | None = Field(default=None, ge=1, le=24)
    timestamp_ms: int | None = Field(default=None, ge=0)
    resource_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def exactly_one_locator(self) -> "SourceVisualLocator":
        if (
            sum(
                value is not None
                for value in (self.page, self.timestamp_ms, self.resource_id)
            )
            != 1
        ):
            raise ValueError("source visual locator must contain exactly one value")
        return self


def validate_source_visual_origin_locator(
    origin: SourceVisualOrigin, source_locator: SourceVisualLocator
) -> None:
    """Bind each source visual origin to its supported locator kind."""

    supported_locator_fields = {
        "embedded": {"page", "resource_id"},
        "video_frame": {"timestamp_ms"},
        "audio_artwork": {"resource_id"},
    }
    locator_field = next(
        (
            field
            for field in ("page", "timestamp_ms", "resource_id")
            if getattr(source_locator, field) is not None
        ),
        None,
    )
    if locator_field is None:
        raise ValueError("source visual locator must contain exactly one value")
    if locator_field not in supported_locator_fields[origin]:
        raise ValueError(
            f"source visual origin {origin!r} does not support {locator_field!r}"
        )


class SourceVisualAuthority(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(pattern=r"^source:[A-Za-z0-9_-]+$", max_length=512)
    source_updated_at: datetime
    normalized_source_type: str = Field(min_length=1, max_length=64)
    asset_url: str | None = Field(default=None, max_length=4096)
    controlled_file_path: str | None = Field(default=None, max_length=4096)
    source_file_sha256: str | None = Field(default=None, pattern=SHA256)
    full_text_sha256: str | None = Field(default=None, pattern=SHA256)
    content_sha256: str = Field(pattern=SHA256)
    extractor_version: str = Field(min_length=1, max_length=64)


class SourceVisualRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    source_id: str
    source_updated_at: datetime
    source_file_sha256: str | None = Field(default=None, pattern=SHA256)
    content_sha256: str = Field(pattern=SHA256)
    asset_sha256: str = Field(pattern=SHA256)
    asset_relpath: str = Field(min_length=1, max_length=512)
    origin: SourceVisualOrigin
    source_locator: SourceVisualLocator
    extractor_version: str = Field(min_length=1, max_length=64)
    alt_text: str = Field(min_length=1, max_length=300)
    width: int = Field(ge=1, le=1280)
    height: int = Field(ge=1, le=720)
    mime_type: Literal["image/webp"] = "image/webp"
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def origin_matches_source_locator(self) -> "SourceVisualRecord":
        validate_source_visual_origin_locator(self.origin, self.source_locator)
        return self


class SourceVisualClaim(BaseModel):
    """One durable owner-fenced lease for a source fingerprint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(pattern=SHA256)
    source_id: str = Field(min_length=1, max_length=512)
    content_sha256: str = Field(pattern=SHA256)
    extractor_version: str = Field(min_length=1, max_length=64)
    owner_token: str = Field(pattern=SHA256)
    lease_until: datetime
    command_id: str | None = Field(default=None, min_length=1, max_length=512)
    created_at: datetime
    updated_at: datetime

    @property
    def identity(self) -> str:
        return self.claim_id


class SourceVisualOperationReceipt(BaseModel):
    """Durable idempotency receipt with no path or source-text payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str = Field(pattern=SHA256)
    source_id: str = Field(min_length=1, max_length=512)
    request_id: str = Field(min_length=1, max_length=256)
    source_updated_at: datetime
    content_sha256: str = Field(pattern=SHA256)
    operation: SourceVisualOperation
    command_id: str | None = Field(default=None, min_length=1, max_length=512)
    outcome: SourceVisualOutcome
    error_code: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$",
        max_length=64,
    )
    created_at: datetime
    updated_at: datetime

    @property
    def receipt_id(self) -> str:
        return self.operation_id


class PreparedVisualAsset(BaseModel):
    """Verified static WebP bytes ready for controlled-root publication."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    encoded_bytes: bytes = Field(min_length=1, max_length=1_572_864)
    asset_sha256: str = Field(pattern=SHA256)
    width: int = Field(ge=1, le=1280)
    height: int = Field(ge=1, le=720)
    mime_type: Literal["image/webp"] = "image/webp"

    @property
    def byte_size(self) -> int:
        return len(self.encoded_bytes)
