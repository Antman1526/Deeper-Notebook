"""HTTP contracts for private, evidence-cited study cards."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from deeper_notebook.evaluation.schemas import EvidenceSpan
from deeper_notebook.study.contracts import (
    FsrsCardState,
    StudyCard,
    StudyRating,
    StudyReview,
)


class CreateStudyCardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1, max_length=512)
    artifact_card_id: str = Field(min_length=1, max_length=512)
    front: str = Field(min_length=1, max_length=8_000)
    back: str = Field(min_length=1, max_length=16_000)
    citations: list[EvidenceSpan] = Field(min_length=1, max_length=32)

    def to_card(self) -> StudyCard:
        return StudyCard(**self.model_dump())


class ReviewStudyCardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=256)
    rating: StudyRating
    reviewed_at: datetime | None = None


class StudyCardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    artifact_id: str
    artifact_card_id: str
    version: int
    front: str
    back: str
    citations: list[EvidenceSpan]
    fsrs_state: FsrsCardState
    due: datetime
    stability: float | None = None
    difficulty: float | None = None
    lapse_count: int
    current: bool

    @classmethod
    def from_card(cls, card: StudyCard) -> "StudyCardResponse":
        return cls(**card.model_dump(exclude={"schema_version", "created", "updated"}))


class StudyReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    card_id: str
    card_version: int
    request_id: str | None = None
    rating: StudyRating
    reviewed_at: datetime
    fsrs_state_before: FsrsCardState
    fsrs_state_after: FsrsCardState
    lapse_count_after: int

    @classmethod
    def from_review(cls, review: StudyReview) -> "StudyReviewResponse":
        return cls(**review.model_dump(exclude={"schema_version", "created"}))


class StudyReviewResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card: StudyCardResponse
    review: StudyReviewResponse
