"""A narrow FSRS adapter that persists only stable study contracts."""

from __future__ import annotations

from datetime import UTC, datetime

from fsrs import Card, Rating, Scheduler, State

from .contracts import (
    FsrsCardState,
    StudyCard,
    StudyRating,
    StudyReview,
    StudyScheduleResult,
)

_TO_FSRS_STATE = {
    "learning": State.Learning,
    "review": State.Review,
    "relearning": State.Relearning,
}
_FROM_FSRS_STATE = {value: key for key, value in _TO_FSRS_STATE.items()}
_TO_FSRS_RATING = {
    StudyRating.AGAIN: Rating.Again,
    StudyRating.HARD: Rating.Hard,
    StudyRating.GOOD: Rating.Good,
    StudyRating.EASY: Rating.Easy,
}


class StudyScheduler:
    """Schedule cards without leaking a third-party object into persistence."""

    def __init__(self, scheduler: Scheduler | None = None) -> None:
        self._scheduler = scheduler or Scheduler(enable_fuzzing=False)

    def schedule(
        self,
        card: StudyCard,
        rating: StudyRating,
        *,
        reviewed_at: datetime | None = None,
    ) -> StudyScheduleResult:
        when = reviewed_at or datetime.now(UTC)
        if when.tzinfo is None or when.utcoffset() != UTC.utcoffset(when):
            raise ValueError("review time must be timezone-aware and in UTC")

        before = card.fsrs_state
        reviewed_card, _ = self._scheduler.review_card(
            self._to_fsrs_card(before), _TO_FSRS_RATING[rating], review_datetime=when
        )
        after = self._from_fsrs_card(reviewed_card)
        updated = card.model_copy(
            update={
                "fsrs_state": after,
                "due": after.due,
                "stability": after.stability,
                "difficulty": after.difficulty,
                "lapse_count": card.lapse_count
                + int(before.state == "review" and rating == StudyRating.AGAIN),
            }
        )
        review = StudyReview(
            card_id=card.id or "unpersisted",
            card_version=card.version,
            rating=rating,
            reviewed_at=when,
            fsrs_state_before=before,
            fsrs_state_after=after,
            lapse_count_after=updated.lapse_count,
        )
        return StudyScheduleResult(card=updated, review=review)

    @staticmethod
    def _to_fsrs_card(state: FsrsCardState) -> Card:
        return Card(
            card_id=0,
            state=_TO_FSRS_STATE[state.state],
            step=state.step,
            stability=state.stability,
            difficulty=state.difficulty,
            due=state.due,
            last_review=state.last_review,
        )

    @staticmethod
    def _from_fsrs_card(card: Card) -> FsrsCardState:
        return FsrsCardState(
            state=_FROM_FSRS_STATE[card.state],
            step=card.step,
            due=card.due,
            last_review=card.last_review,
            stability=card.stability,
            difficulty=card.difficulty,
        )
