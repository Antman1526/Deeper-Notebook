"""Strict HTTP contracts for the bounded Study assistant API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from deeper_notebook.study.assistants import (
    StudyAssistantInvocation,
    StudyAssistantResponse,
    StudyAssistantRole,
    StudyAuthority,
)


class InvokeStudyAssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: StudyAuthority
    prompt: StrictStr = Field(min_length=1, max_length=16_384)
    unit_id: StrictStr | None = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$"
    )
    selected_source_ids: tuple[StrictStr, ...] = Field(
        default_factory=tuple, max_length=100
    )
    model_route: Literal["local", "cloud"] = "local"
    network_allowed: StrictBool = False
    approved_network_scope: tuple[StrictStr, ...] = Field(
        default_factory=tuple, max_length=8
    )
    timeout_seconds: StrictInt = Field(default=120, ge=1, le=120)
    request_id: StrictStr | None = Field(default=None, min_length=1, max_length=256)
    created_at: datetime | None = None

    @field_validator("prompt")
    @classmethod
    def prompt_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value

    @field_validator("selected_source_ids")
    @classmethod
    def sources_are_nonblank_and_unique(
        cls, values: tuple[str, ...]
    ) -> tuple[str, ...]:
        if any(not value.strip() for value in values):
            raise ValueError("selected source IDs must not be blank")
        if len(set(values)) != len(values):
            raise ValueError("selected source IDs must be unique")
        return values

    @model_validator(mode="after")
    def network_authority_is_explicit(self) -> "InvokeStudyAssistantRequest":
        if self.network_allowed != bool(self.approved_network_scope):
            raise ValueError("network authority and scope must be supplied together")
        if self.model_route == "cloud" and not self.network_allowed:
            raise ValueError("cloud route requires network authority")
        return self

    def to_invocation(
        self, plan_id: str, role: StudyAssistantRole
    ) -> StudyAssistantInvocation:
        request_id = self.request_id or uuid4().hex
        return StudyAssistantInvocation(
            invocation_id=request_id,
            request_id=request_id,
            plan_id=plan_id,
            unit_id=self.unit_id,
            role=role,
            authority=self.authority,
            prompt=self.prompt,
            selected_source_ids=self.selected_source_ids,
            network_allowed=self.network_allowed,
            approved_network_scope=self.approved_network_scope,
            model_route=self.model_route,
            timeout_seconds=self.timeout_seconds,
            created_at=self.created_at or datetime.now(UTC),
        )


class StudyAssistantResponseBody(StudyAssistantResponse):
    model_config = ConfigDict(extra="forbid", strict=True)


class SynthesizeStudyVoiceRequest(BaseModel):
    """Strict assistant prose input for local Study speech synthesis."""

    model_config = ConfigDict(extra="forbid", strict=True)

    text: StrictStr = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def text_is_bounded_and_nonblank(cls, value: str) -> str:
        if not value.strip() or len(value.encode("utf-8")) > 8 * 1024:
            raise ValueError("voice text must be nonblank and at most 8 KiB UTF-8")
        return value


class StudyVoiceTranscriptionResponse(BaseModel):
    """Bounded transcript projection; provider metadata never crosses HTTP."""

    model_config = ConfigDict(extra="forbid", strict=True)

    transcript: StrictStr = Field(min_length=1, max_length=16 * 1024)


class StudyVoiceCapabilityResponse(BaseModel):
    """Persisted local speech readiness; no provider details cross HTTP."""

    model_config = ConfigDict(extra="forbid", strict=True)

    stt: Literal["ready", "unavailable"]
    tts: Literal["ready", "unavailable"]


__all__ = [
    "InvokeStudyAssistantRequest",
    "StudyAssistantResponseBody",
    "StudyVoiceCapabilityResponse",
    "StudyVoiceTranscriptionResponse",
    "SynthesizeStudyVoiceRequest",
]
