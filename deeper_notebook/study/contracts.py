"""Durable, library-independent contracts for private study cards."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deeper_notebook.evaluation.schemas import EvidenceSpan


class StudyRating(str, Enum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class FsrsCardState(BaseModel):
    """A stable serialized view of an FSRS card, never an FSRS object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    state: Literal["learning", "review", "relearning"] = "learning"
    step: int | None = Field(default=0, ge=0)
    due: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_review: datetime | None = None
    stability: float | None = Field(default=None, gt=0)
    difficulty: float | None = Field(default=None, ge=1, le=10)

    @model_validator(mode="after")
    def state_requires_expected_fields(self) -> "FsrsCardState":
        if self.due.tzinfo is None:
            raise ValueError("FSRS due time must be timezone-aware")
        if self.last_review is not None and self.last_review.tzinfo is None:
            raise ValueError("FSRS review time must be timezone-aware")
        if self.state == "review" and (
            self.step is not None or self.stability is None or self.difficulty is None
        ):
            raise ValueError("review state requires stability and difficulty")
        if self.state != "review" and self.step is None:
            raise ValueError("learning states require a step")
        return self


class StudyCard(BaseModel):
    """One immutable source-card snapshot and its current scheduling state."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    id: str | None = None
    artifact_id: str = Field(min_length=1, max_length=512)
    artifact_card_id: str = Field(min_length=1, max_length=512)
    version: int = Field(default=1, ge=1)
    front: str = Field(min_length=1, max_length=8_000)
    back: str = Field(min_length=1, max_length=16_000)
    citations: list[EvidenceSpan] = Field(min_length=1, max_length=32)
    fsrs_state: FsrsCardState = Field(default_factory=FsrsCardState)
    due: datetime | None = None
    stability: float | None = None
    difficulty: float | None = None
    lapse_count: int = Field(default=0, ge=0)
    current: bool = True
    created: datetime | None = None
    updated: datetime | None = None

    @model_validator(mode="after")
    def copy_schedule_fields_from_plain_state(self) -> "StudyCard":
        self.due = self.fsrs_state.due
        self.stability = self.fsrs_state.stability
        self.difficulty = self.fsrs_state.difficulty
        citation_keys = {
            (
                citation.source_id,
                citation.source_content_sha256,
                citation.start,
                citation.end,
            )
            for citation in self.citations
        }
        if len(citation_keys) != len(self.citations):
            raise ValueError("duplicate evidence citations are not allowed")
        return self


class StudyReview(BaseModel):
    """Append-only review receipt bound to a particular card version."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    id: str | None = None
    card_id: str = Field(min_length=1, max_length=512)
    card_version: int = Field(ge=1)
    request_id: str | None = Field(default=None, min_length=1, max_length=256)
    rating: StudyRating
    reviewed_at: datetime
    fsrs_state_before: FsrsCardState
    fsrs_state_after: FsrsCardState
    lapse_count_after: int = Field(ge=0)
    created: datetime | None = None

    @model_validator(mode="after")
    def review_time_is_utc_aware(self) -> "StudyReview":
        if self.reviewed_at.tzinfo is None:
            raise ValueError("review time must be timezone-aware")
        return self


class StudyScheduleResult(BaseModel):
    """The scheduler result before a repository gives the review an ID."""

    model_config = ConfigDict(extra="forbid")

    card: StudyCard
    review: StudyReview
