"""Owner-local endpoints for evidence-grounded spaced repetition."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from api.schemas.study import (
    CreateStudyCardRequest,
    ReviewStudyCardRequest,
    StudyCardResponse,
    StudyReviewResponse,
    StudyReviewResultResponse,
)
from deeper_notebook.study.repository import (
    StudyCardArtifactOwnerError,
    StudyRepository,
    StudyRepositoryError,
)

router = APIRouter(prefix="/study", tags=["study"])


def _repository() -> StudyRepository:
    return StudyRepository()


@router.post("/cards", response_model=StudyCardResponse, status_code=status.HTTP_201_CREATED)
async def create_study_card(payload: CreateStudyCardRequest) -> StudyCardResponse:
    repository = _repository()
    try:
        requested = payload.to_card()
        atomic_creator = getattr(repository, "create_card_version_with_artifact_owner", None)
        if callable(atomic_creator):
            card = await atomic_creator(requested)
        else:
            card = await repository.create_card_version(requested)
            linker = getattr(repository, "link_card_to_artifact_owner", None)
            if callable(linker):
                await linker(card)
    except StudyRepositoryError as exc:
        if isinstance(exc, StudyCardArtifactOwnerError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Study card artifact owner changed",
            ) from None
        raise HTTPException(status_code=503, detail="Study cards are unavailable") from None
    return StudyCardResponse.from_card(card)


@router.get("/cards/due", response_model=list[StudyCardResponse])
async def list_due_study_cards(
    limit: int = Query(default=100, ge=1, le=500),
) -> list[StudyCardResponse]:
    try:
        cards = await _repository().list_due(datetime.now(UTC), limit=limit)
    except StudyRepositoryError:
        raise HTTPException(status_code=503, detail="Study cards are unavailable") from None
    return [StudyCardResponse.from_card(card) for card in cards]


@router.post("/cards/{card_id}/reviews", response_model=StudyReviewResultResponse)
async def review_study_card(
    card_id: str, payload: ReviewStudyCardRequest
) -> StudyReviewResultResponse:
    try:
        card, review = await _repository().review(
            card_id,
            rating=payload.rating,
            request_id=payload.request_id,
            reviewed_at=payload.reviewed_at,
        )
    except StudyRepositoryError as exc:
        if str(exc) == "Study card no longer exists":
            raise HTTPException(status_code=404, detail="Study card not found") from None
        if str(exc) == "Review request ID was already used":
            raise HTTPException(status_code=409, detail=str(exc)) from None
        raise HTTPException(status_code=503, detail="Study reviews are unavailable") from None
    return StudyReviewResultResponse(
        card=StudyCardResponse.from_card(card),
        review=StudyReviewResponse.from_review(review),
    )
