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


class StudyCardArtifactOwnerError(StudyRepositoryError):
    """Base class for typed Study-card artifact-owner conflicts."""


class StudyCardArtifactOwnerConflict(StudyCardArtifactOwnerError):
    """The artifact owner changed or could not be linked atomically."""


class StudyCardArtifactOwnerAmbiguous(StudyCardArtifactOwnerError):
    """More than one Study plan owns the referenced artifact."""


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

    async def _artifact_owner(self, artifact_id: str) -> tuple[str, str | None] | None:
        """Resolve one plan owner without exposing driver rows to callers."""
        try:
            owner_rows = await repo_query(
                "SELECT plan_id, metadata.unit_id AS syllabus_unit_id "
                "FROM study_plan_artifact WHERE artifact_id = $artifact_id "
                "LIMIT 2",
                {"artifact_id": artifact_id},
            )
        except Exception as exc:
            logger.exception("Failed to resolve study card artifact owner")
            raise StudyCardArtifactOwnerConflict(
                "Failed to resolve card artifact owner"
            ) from exc
        if not isinstance(owner_rows, list):
            raise StudyCardArtifactOwnerConflict(
                "Failed to resolve card artifact owner"
            )
        owners = [
            row
            for row in owner_rows
            if isinstance(row, dict) and isinstance(row.get("plan_id"), str)
        ]
        if not owners:
            if owner_rows:
                raise StudyCardArtifactOwnerConflict(
                    "Card artifact owner data is malformed"
                )
            return None
        if len(owners) != len(owner_rows):
            raise StudyCardArtifactOwnerConflict(
                "Card artifact owner data is malformed"
            )
        if len(owners) != 1:
            raise StudyCardArtifactOwnerAmbiguous("card artifact owner is ambiguous")
        return str(owners[0]["plan_id"]), owners[0].get("syllabus_unit_id")

    async def create_card_version_with_artifact_owner(self, card: StudyCard) -> StudyCard:
        """Create a card snapshot and owner edge in one DB transaction.

        The transaction reads the owner and current snapshot, retires a
        predecessor, creates the next version, and publishes the plan-card
        edge before committing. A failed owner guard or version race rolls
        back the complete unit; no compensating delete can remove a card that
        another concurrent request has already linked.
        """
        card_data = self._card_data(card)
        # Resolve the expected owner before opening the write transaction, then
        # bind that exact result as a transaction parameter.  The transaction
        # repeats the read and refuses both disappearance and cross-plan
        # replacement before it can retire/create any card snapshot.
        owner = await self._artifact_owner(card.artifact_id)
        expected_plan_id = owner[0] if owner is not None else None
        transaction = (
            "BEGIN TRANSACTION; "
            "LET $owners = (SELECT plan_id, metadata.unit_id AS syllabus_unit_id "
            "FROM study_plan_artifact WHERE artifact_id = $artifact_id LIMIT 2); "
            "IF $expected_plan_id = NONE { "
            'IF array::len($owners) != 0 { THROW "study_card_artifact_owner_conflict"; }; '
            "} ELSE { "
            'IF array::len($owners) != 1 OR $owners[0].plan_id != $expected_plan_id { THROW "study_card_artifact_owner_conflict"; }; '
            "}; "
            "LET $current = (SELECT * FROM study_card "
            "WHERE artifact_id = $artifact_id AND artifact_card_id = $artifact_card_id "
            "AND current = true ORDER BY version DESC LIMIT 1)[0]; "
            "LET $same = $current != NONE AND $current.front = $card_data.front "
            "AND $current.back = $card_data.back "
            "AND $current.citations = $card_data.citations; "
            "IF $same = false AND $current != NONE { UPDATE $current SET current = false; }; "
            "LET $card = IF $same THEN $current ELSE (CREATE study_card SET "
            "schema_version = $card_data.schema_version, "
            "artifact_id = $card_data.artifact_id, "
            "artifact_card_id = $card_data.artifact_card_id, "
            "version = IF $current = NONE THEN 1 ELSE $current.version + 1 END, "
            "front = $card_data.front, back = $card_data.back, "
            "citations = $card_data.citations, fsrs_state = $card_data.fsrs_state, "
            "due = $card_data.due, stability = $card_data.stability, "
            "difficulty = $card_data.difficulty, lapse_count = $card_data.lapse_count, "
            "current = true RETURN AFTER)[0] END; "
            "LET $card_id = type::string($card.id); "
            "IF $expected_plan_id != NONE { "
            "LET $existing = (SELECT id FROM study_plan_card "
            "WHERE plan_id = $expected_plan_id AND card_id = $card_id)[0]; "
            "IF $existing = NONE { CREATE study_plan_card CONTENT { "
            "plan_id: $expected_plan_id, card_id: $card_id, "
            "syllabus_unit_id: $owners[0].syllabus_unit_id, created_at: time::now() }; }; "
            "}; COMMIT TRANSACTION; RETURN $card;"
        )
        try:
            result = await repo_query(
                transaction,
                {
                    "artifact_id": card.artifact_id,
                    "artifact_card_id": card.artifact_card_id,
                    "card_data": card_data,
                    "expected_plan_id": expected_plan_id,
                },
            )
            if result:
                try:
                    return self._card_from_record(_one_record(result))
                except StudyRepositoryError:
                    # A driver may omit a multi-statement RETURN projection;
                    # the committed read below remains authoritative.
                    pass
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
        except StudyCardArtifactOwnerError:
            raise
        except Exception as exc:
            marker = str(exc)
            if "study_card_artifact_owner_ambiguous" in marker:
                raise StudyCardArtifactOwnerAmbiguous(
                    "card artifact owner is ambiguous"
                ) from exc
            if "study_card_artifact_owner_conflict" in marker:
                raise StudyCardArtifactOwnerConflict(
                    "card artifact owner changed"
                ) from exc
            logger.exception("Failed to create/link study card atomically")
            raise StudyCardArtifactOwnerConflict(
                "Failed to create/link card artifact owner atomically"
            ) from exc

    async def _link_card_to_owner_transaction(
        self, card: StudyCard, *, expected_plan_id: str
    ) -> None:
        try:
            card_record = ensure_record_id(card.id or "")
        except Exception as exc:
            raise StudyCardArtifactOwnerConflict(
                "card artifact owner has invalid card ID"
            ) from exc
        try:
            await repo_query(
                "BEGIN TRANSACTION; "
                "LET $owners = (SELECT plan_id, metadata.unit_id AS syllabus_unit_id "
                "FROM study_plan_artifact WHERE artifact_id = $artifact_id LIMIT 2); "
                "IF array::len($owners) != 1 OR $owners[0].plan_id != $expected_plan_id { "
                'THROW "study_card_artifact_owner_conflict"; }; '
                "LET $card_guard = (SELECT id FROM $card_record)[0]; "
                'IF $card_guard = NONE { THROW "study_card_artifact_owner_conflict"; }; '
                "LET $existing = (SELECT id FROM study_plan_card "
                "WHERE plan_id = $expected_plan_id AND card_id = $card_id)[0]; "
                "IF $existing = NONE { "
                "CREATE study_plan_card CONTENT { "
                "plan_id: $expected_plan_id, card_id: $card_id, "
                "syllabus_unit_id: $owners[0].syllabus_unit_id, "
                "created_at: time::now() }; }; "
                "COMMIT TRANSACTION;",
                {
                    "artifact_id": card.artifact_id,
                    "expected_plan_id": expected_plan_id,
                    "card_record": card_record,
                    "card_id": str(card_record),
                },
            )
        except Exception as exc:
            if "study_card_artifact_owner_conflict" in str(exc):
                raise StudyCardArtifactOwnerConflict(
                    "card artifact owner changed"
                ) from exc
            logger.exception("Failed to link study card to artifact owner")
            raise StudyCardArtifactOwnerConflict(
                "Failed to link card artifact owner"
            ) from exc

    async def link_card_to_artifact_owner(self, card: StudyCard) -> str | None:
        """Link a card to its unique Study plan artifact owner, if one exists.

        Legacy cards may reference artifacts that predate Study Workbench and
        therefore have no ``study_plan_artifact`` owner; those cards remain
        intentionally unlinked.  When an owner exists, the link is published
        in an idempotent transaction that re-checks the artifact owner and card
        identity, preventing a cross-plan link during concurrent changes.
        """
        if not isinstance(card.id, str) or not card.id.strip():
            raise StudyRepositoryError("card artifact owner requires a persisted card")
        owner = await self._artifact_owner(card.artifact_id)
        if owner is None:
            return None
        expected_plan_id = owner[0]
        await self._link_card_to_owner_transaction(
            card,
            expected_plan_id=expected_plan_id,
        )
        return expected_plan_id

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
