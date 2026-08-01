"""Strict, source-body-free wire contracts for Podcast Intelligence Studio."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from deeper_notebook.knowledge_engine.capabilities import AuthorityKind
from deeper_notebook.podcasts.selection_contracts import PodcastSelection


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PodcastSelectionPreviewRequest(_Strict):
    """Stable selection references only; canonical source text is server-side."""

    selections: list[PodcastSelection] = Field(min_length=1, max_length=128)


class PodcastSelectionPreviewEntryResponse(_Strict):
    stable_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    authority_kind: AuthorityKind
    relative_locator: str | None = Field(default=None, max_length=1024)
    revision_id: str | None = Field(default=None, max_length=128)
    fingerprint: str | None = Field(default=None, max_length=128)
    state: Literal[
        "included",
        "duplicate",
        "unavailable",
        "changed",
        "empty",
        "failed_parse",
        "oversize",
    ]
    reason: str = Field(min_length=1, max_length=128)
    estimated_characters: int = Field(ge=0)


class PodcastSelectionPreviewResponse(_Strict):
    selection_fingerprint: str = Field(min_length=64, max_length=64)
    entries: list[PodcastSelectionPreviewEntryResponse] = Field(max_length=10_000)
    included_characters: int = Field(ge=0)
    requires_batch_engine: bool
    current_worker_eligible: bool
    blocked_reasons: list[str] = Field(default_factory=list, max_length=128)


class PodcastReadinessRequest(PodcastSelectionPreviewRequest):
    execution_policy: Literal["strict_local", "local_preferred", "custom"] = (
        "strict_local"
    )
    compute_profile: Literal["efficient", "balanced", "maximum_quality"] = "balanced"
    include_transcription: bool = False


class PodcastStageModelPlanResponse(_Strict):
    role: Literal[
        "podcast_outline", "podcast_script", "text_to_speech", "speech_to_text"
    ]
    outcome: Literal["ready", "blocked", "approval_required"]
    model_id: str | None = Field(default=None, max_length=512)
    provider: str | None = Field(default=None, max_length=128)
    resource_tier: Literal["light", "standard", "heavyweight"] | None = None
    selection_source: (
        Literal["automatic", "role_override", "production_override"] | None
    ) = None
    reason: str = Field(min_length=1, max_length=1024)
    blocked_reason: str | None = Field(default=None, max_length=1024)


class PodcastReadinessResponse(_Strict):
    preview: PodcastSelectionPreviewResponse
    stage_plans: list[PodcastStageModelPlanResponse] = Field(min_length=3, max_length=4)
    ready: bool
    blocked_reasons: list[str] = Field(default_factory=list, max_length=128)


class PodcastStudioSubmitRequest(PodcastReadinessRequest):
    selection_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$",
    )
    confirmed: Literal[True]
    episode_profile: str = Field(min_length=1, max_length=256)
    speaker_profile: str = Field(min_length=1, max_length=256)
    episode_name: str = Field(min_length=1, max_length=512)
    mode: Literal["deep_dive", "brief", "critique", "debate"] = "deep_dive"
    custom_prompt: str | None = Field(default=None, max_length=10_000)
    episode_length: Literal["short", "medium", "long"] | None = None
    review_outline: bool = True

    @field_validator("episode_profile", "speaker_profile", "episode_name")
    @classmethod
    def label_is_not_path(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized or normalized.startswith(("/", "\\")) or ":\\" in normalized:
            raise ValueError("label must not be a filesystem path")
        return normalized


class PodcastStudioSubmitResponse(_Strict):
    job_id: str = Field(min_length=1, max_length=256)
    status: Literal["submitted"]
    message: str = Field(min_length=1, max_length=256)
    episode_profile: str = Field(min_length=1, max_length=256)
    episode_name: str = Field(min_length=1, max_length=512)
    mode: Literal["deep_dive", "brief", "critique", "debate"]


__all__ = [
    "PodcastReadinessRequest",
    "PodcastReadinessResponse",
    "PodcastSelectionPreviewEntryResponse",
    "PodcastSelectionPreviewRequest",
    "PodcastSelectionPreviewResponse",
    "PodcastStageModelPlanResponse",
    "PodcastStudioSubmitRequest",
    "PodcastStudioSubmitResponse",
]
