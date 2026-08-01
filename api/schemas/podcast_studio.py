"""Strict, source-body-free wire contracts for Podcast Intelligence Studio."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


__all__ = [
    "PodcastSelectionPreviewEntryResponse",
    "PodcastSelectionPreviewRequest",
    "PodcastSelectionPreviewResponse",
]
