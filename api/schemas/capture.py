"""Public contracts for personal local Capture Inbox configuration and state."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from deeper_notebook.capture.contracts import CaptureState
from deeper_notebook.capture.routing import CaptureRouteResult


class RegisterCaptureRootRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=4096)

    @field_validator("path")
    @classmethod
    def non_blank_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("path must not be blank")
        return value


class CaptureRootResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str


class CaptureItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    root_path: str
    relative_path: str
    filename: str
    extension: str
    state: CaptureState
    sha256: str | None = None
    byte_size: int | None = None
    modified_ns: int | None = None
    reason: str | None = None
    linked_source: dict[str, Any] | None = None


class CaptureScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_path: str | None = Field(default=None, max_length=4096)


class CaptureScanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CaptureItemResponse]


class CaptureRouteRequest(BaseModel):
    """Request a local-only transcription and notebook route preview."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=4096)

    @field_validator("path")
    @classmethod
    def non_blank_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("path must not be blank")
        return value


class CaptureRouteResponse(CaptureRouteResult):
    """Route preview only; importing remains a separate approved action."""
