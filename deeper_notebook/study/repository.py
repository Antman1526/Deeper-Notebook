"""SurrealDB persistence for versioned cards and immutable review receipts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from deeper_notebook.database.repository import (
    ensure_record_id,
    repo_create,
    repo_query,
)

from .contracts import StudyCard, StudyRating, StudyReview
from .scheduler import StudyScheduler


class StudyRepositoryError(RuntimeError):
    """A safe study persistence failure suitable for API callers."""


def _one_record(value: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    if isinstance(value, list):
        if len(value) != 1:
            raise StudyRepositoryError("Study persistence returned an invalid record")
        value = value[0]
    if not isinstance(value, dict) or "id" not in value:
        raise StudyRepositoryError("Study persistence returned an invalid record")
    return value


class StudyRepository:
    """Keep card snapshots immutable while allowing scheduling fields to advance."""

    async def create_card_version(self, card: StudyCard) -> StudyCard:
        """Create a new version only when an artifact's card snapshot changed."""
        try:
            previous_rows = await repo_query(
                "SELECT * FROM study_card WHERE artifact_id = $artifact_id "
                "AND artifact_card_id = $artifact_card_id AND current = true "
                "ORDER BY version DESC LIMIT 1",
                {"artifact_id": card.artifact_id, "artifact_card_id": card.artifact_card_id},
            )
            if previous_rows:
                previous = self._card_from_record(previous_rows[0])
                if self._snapshot_matches(previous, card):
                    return previous
                version = previous.version + 1
                next_card = card.model_copy(update={"version": version, "current": True})
                await repo_query(
                    "BEGIN TRANSACTION; "
                    "UPDATE $previous SET current = false; "
                    "CREATE study_card CONTENT $next_card; "
                    "COMMIT TRANSACTION;",
                    {
                        "previous": ensure_record_id(previous.id or ""),
                        "next_card": self._card_data(next_card),
                    },
                )
                current_rows = await repo_query(
                    "SELECT * FROM study_card WHERE artifact_id = $artifact_id "
                    "AND artifact_card_id = $artifact_card_id AND current = true "
                    "ORDER BY version DESC LIMIT 1",
                    {
                        "artifact_id": card.artifact_id,
                        "artifact_card_id": card.artifact_card_id,
                    },
                )
                return self._card_from_record(_one_record(current_rows))
            else:
                version = 1
            created = await repo_create(
                "study_card",
                self._card_data(card.model_copy(update={"version": version, "current": True})),
            )
            return self._card_from_record(_one_record(created))
        except StudyRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to create study card version")
            raise StudyRepositoryError("Failed to create study card") from exc

    async def get(self, card_id: str) -> StudyCard | None:
        try:
            rows = await repo_query("SELECT * FROM $card", {"card": ensure_record_id(card_id)})
            return self._card_from_record(rows[0]) if rows else None
        except Exception as exc:
            logger.exception("Failed to load study card")
            raise StudyRepositoryError("Failed to load study card") from exc

    async def list_due(self, now: datetime, *, limit: int = 100) -> list[StudyCard]:
        if now.tzinfo is None:
            raise ValueError("due-time lookup must use a timezone-aware value")
        try:
            rows = await repo_query(
                "SELECT * FROM study_card WHERE current = true AND due <= $now "
                "ORDER BY due ASC LIMIT $limit",
                {"now": now, "limit": min(max(limit, 1), 500)},
            )
            return [self._card_from_record(row) for row in rows]
        except Exception as exc:
            logger.exception("Failed to list due study cards")
            raise StudyRepositoryError("Failed to list due study cards") from exc

    async def review(
        self,
        card_id: str,
        *,
        rating: StudyRating,
        request_id: str,
        reviewed_at: datetime | None = None,
    ) -> tuple[StudyCard, StudyReview]:
        """Apply one request exactly once and write its immutable receipt atomically."""
        try:
            existing_rows = await repo_query(
                "SELECT * FROM study_review WHERE request_id = $request_id LIMIT 1",
                {"request_id": request_id},
            )
            if existing_rows:
                existing = self._review_from_record(existing_rows[0])
                if existing.card_id != card_id or existing.rating != rating:
                    raise StudyRepositoryError("Review request ID was already used")
                card = await self.get(card_id)
                if card is None:
                    raise StudyRepositoryError("Study card no longer exists")
                return card, existing

            card = await self.get(card_id)
            if card is None:
                raise StudyRepositoryError("Study card no longer exists")
            scheduled = StudyScheduler().schedule(card, rating, reviewed_at=reviewed_at)
            review = scheduled.review.model_copy(update={"request_id": request_id})
            card_data = self._card_data(scheduled.card)
            review_data = self._review_data(review)
            # The unique request-id index converts concurrent replays into one
            # transaction winner; a caller that loses re-reads that receipt.
            await repo_query(
                "BEGIN TRANSACTION; "
                "UPDATE $card MERGE $card_data; "
                "CREATE study_review CONTENT $review_data; "
                "COMMIT TRANSACTION;",
                {
                    "card": ensure_record_id(card_id),
                    "card_data": card_data,
                    "review_data": review_data,
                },
            )
            return scheduled.card, review
        except StudyRepositoryError:
            raise
        except Exception as exc:
            # A simultaneous duplicate can lose the unique-index race after
            # the initial read. Re-read once so genuine replays remain stable.
            try:
                replay_rows = await repo_query(
                    "SELECT * FROM study_review WHERE request_id = $request_id LIMIT 1",
                    {"request_id": request_id},
                )
                if replay_rows:
                    replay = self._review_from_record(replay_rows[0])
                    if replay.card_id == card_id and replay.rating == rating:
                        current = await self.get(card_id)
                        if current is not None:
                            return current, replay
            except Exception:
                pass
            logger.exception("Failed to record study review")
            raise StudyRepositoryError("Failed to record study review") from exc

    @staticmethod
    def _snapshot_matches(left: StudyCard, right: StudyCard) -> bool:
        return (
            left.front,
            left.back,
            left.citations,
        ) == (
            right.front,
            right.back,
            right.citations,
        )

    @staticmethod
    def _card_data(card: StudyCard) -> dict[str, Any]:
        # Surreal schema fields ``due``/FSRS timestamps are native datetimes;
        # JSON mode turns them into strings that Surreal rejects.  Keep Python
        # datetime values for the driver while still dumping nested contracts.
        return card.model_dump(exclude={"id", "created", "updated"}, mode="python")

    @staticmethod
    def _review_data(review: StudyReview) -> dict[str, Any]:
        data = review.model_dump(exclude={"id", "created"}, mode="python")
        data["card_id"] = ensure_record_id(review.card_id)
        return data

    @staticmethod
    def _card_from_record(record: object) -> StudyCard:
        if not isinstance(record, dict):
            raise StudyRepositoryError("Study persistence returned an invalid card")
        fields = StudyCard.model_fields
        return StudyCard.model_validate({field: record[field] for field in fields if field in record})

    @staticmethod
    def _review_from_record(record: object) -> StudyReview:
        if not isinstance(record, dict):
            raise StudyRepositoryError("Study persistence returned an invalid review")
        fields = StudyReview.model_fields
        return StudyReview.model_validate({field: record[field] for field in fields if field in record})
