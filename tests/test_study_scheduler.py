"""Focused contracts for evidence-grounded FSRS review scheduling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.routers import study as study_router
from deeper_notebook.evaluation.schemas import EvidenceSpan
from deeper_notebook.study.contracts import StudyCard, StudyRating
from deeper_notebook.study.repository import StudyRepository
from deeper_notebook.study.scheduler import StudyScheduler


def _citation() -> EvidenceSpan:
    return EvidenceSpan(
        source_id="source:one",
        source_content_sha256="a" * 64,
        start=0,
        end=12,
        quote="Private fact",
    )


def _card() -> StudyCard:
    return StudyCard(
        id="study_card:one",
        artifact_id="studio_artifact:one",
        artifact_card_id="card-1",
        front="What is the private fact?",
        back="It is cited evidence.",
        citations=[_citation()],
    )


def test_cards_require_immutable_evidence_citations() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        StudyCard(
            artifact_id="studio_artifact:one",
            artifact_card_id="card-1",
            front="What is the private fact?",
            back="It is cited evidence.",
            citations=[],
        )


def test_scheduler_returns_utc_plain_state_without_leaking_fsrs_objects() -> None:
    reviewed_at = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    scheduled = StudyScheduler().schedule(
        _card(), StudyRating.GOOD, reviewed_at=reviewed_at
    )

    assert scheduled.card.fsrs_state.state == "learning"
    assert scheduled.card.fsrs_state.due > reviewed_at
    assert scheduled.card.fsrs_state.last_review == reviewed_at
    assert scheduled.card.due == scheduled.card.fsrs_state.due
    assert scheduled.card.stability is not None
    assert scheduled.card.difficulty is not None
    assert scheduled.review.rating == "good"
    assert scheduled.review.reviewed_at == reviewed_at
    assert "fsrs." not in repr(scheduled.card.fsrs_state).lower()


def test_again_from_a_review_card_increments_lapse_count() -> None:
    scheduler = StudyScheduler()
    first_review_at = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    graduated = scheduler.schedule(_card(), StudyRating.EASY, reviewed_at=first_review_at)

    lapsed = scheduler.schedule(
        graduated.card,
        StudyRating.AGAIN,
        reviewed_at=first_review_at + timedelta(days=2),
    )

    assert graduated.card.fsrs_state.state == "review"
    assert lapsed.card.fsrs_state.state == "relearning"
    assert lapsed.card.lapse_count == 1


def test_native_persistence_keeps_fsrs_datetimes_for_surreal() -> None:
    reviewed_at = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    scheduled = StudyScheduler().schedule(
        _card(), StudyRating.GOOD, reviewed_at=reviewed_at
    )

    card_data = StudyRepository._card_data(scheduled.card)
    review_data = StudyRepository._review_data(scheduled.review)

    assert isinstance(card_data["due"], datetime)
    assert isinstance(card_data["fsrs_state"]["due"], datetime)
    assert isinstance(review_data["reviewed_at"], datetime)
    assert isinstance(review_data["fsrs_state_before"]["due"], datetime)


class _MemoryRepository:
    def __init__(self) -> None:
        self.card = _card()
        self.requests: dict[str, tuple[StudyCard, object]] = {}

    async def create_card_version(self, card: StudyCard) -> StudyCard:
        if (card.front, card.back, card.citations) == (
            self.card.front,
            self.card.back,
            self.card.citations,
        ):
            return self.card
        self.card = card.model_copy(update={"id": "study_card:two", "version": 2})
        return self.card

    async def get(self, card_id: str) -> StudyCard | None:
        return self.card if self.card.id == card_id else None

    async def list_due(self, now: datetime, *, limit: int) -> list[StudyCard]:
        return [self.card] if self.card.due <= now else []

    async def review(
        self, card_id: str, *, rating: StudyRating, request_id: str, reviewed_at: datetime
    ):
        if request_id in self.requests:
            return self.requests[request_id]
        scheduled = StudyScheduler().schedule(self.card, rating, reviewed_at=reviewed_at)
        self.card = scheduled.card
        result = (self.card, scheduled.review)
        self.requests[request_id] = result
        return result


def test_study_api_accepts_evidence_cards_and_replays_review_requests(monkeypatch) -> None:
    store = _MemoryRepository()
    monkeypatch.setattr(study_router, "_repository", lambda: store)
    app = FastAPI()
    app.include_router(study_router.router, prefix="/api")

    with TestClient(app) as client:
        card = client.post(
            "/api/study/cards",
            json={
                "artifact_id": "studio_artifact:one",
                "artifact_card_id": "card-1",
                "front": "What is the private fact?",
                "back": "It is cited evidence.",
                "citations": [_citation().model_dump(mode="json")],
            },
        )
        assert card.status_code == 201
        assert card.json()["citations"][0]["quote"] == "Private fact"

        request = {"request_id": "review-1", "rating": "good", "reviewed_at": "2026-07-18T12:00:00Z"}
        first = client.post("/api/study/cards/study_card:one/reviews", json=request)
        replay = client.post("/api/study/cards/study_card:one/reviews", json=request)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json() == replay.json()


@pytest.mark.asyncio
async def test_source_edit_creates_a_new_version_in_one_transaction(monkeypatch) -> None:
    previous = _card()
    replacement = previous.model_copy(update={"id": "study_card:two", "version": 2})
    queries: list[str] = []

    async def fake_query(query: str, values: dict[str, object]):
        queries.append(query)
        if query.startswith("SELECT * FROM study_card") and len(queries) == 1:
            return [previous.model_dump(mode="json")]
        if query.startswith("SELECT * FROM study_card"):
            return [replacement.model_dump(mode="json")]
        return []

    monkeypatch.setattr("deeper_notebook.study.repository.repo_query", fake_query)

    updated = await StudyRepository().create_card_version(
        previous.model_copy(update={"back": "Updated cited answer."})
    )

    assert updated.id == "study_card:two"
    assert updated.version == 2
    assert any("BEGIN TRANSACTION" in query for query in queries)
