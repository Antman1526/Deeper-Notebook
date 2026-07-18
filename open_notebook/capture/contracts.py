"""Durable contracts for files discovered by the local Capture Inbox."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CaptureState = Literal[
    "pending", "ready", "importing", "imported", "duplicate", "ignored", "failed"
]


class CaptureFingerprint(BaseModel):
    """Content identity, independent of a file's path or name."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_size: int = Field(ge=0)


class CaptureInboxItem(BaseModel):
    """A local inbox observation. Original files are never moved or deleted."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    id: str | None = None
    root_path: str = Field(min_length=1, max_length=4096)
    relative_path: str = Field(min_length=1, max_length=4096)
    filename: str = Field(min_length=1, max_length=1024)
    extension: str = Field(min_length=1, max_length=32)
    state: CaptureState
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    byte_size: int | None = Field(default=None, ge=0)
    modified_ns: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, max_length=160)

    @field_validator("relative_path")
    @classmethod
    def relative_path_must_not_escape_root(cls, value: str) -> str:
        cleaned = value.replace("\\", "/").lstrip("/")
        if not cleaned or any(part in {"", ".", ".."} for part in cleaned.split("/")):
            raise ValueError("relative path must stay within its capture root")
        return cleaned
