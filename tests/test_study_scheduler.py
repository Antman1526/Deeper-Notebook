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
from deeper_notebook.study.repository import (
    StudyCardArtifactOwnerConflict,
    StudyRepository,
    StudyRepositoryError,
)
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
    graduated = scheduler.schedule(
        _card(), StudyRating.EASY, reviewed_at=first_review_at
    )

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
        self.linked_plan_id: str | None = None

    async def create_card_version(self, card: StudyCard) -> StudyCard:
        if (card.front, card.back, card.citations) == (
            self.card.front,
            self.card.back,
            self.card.citations,
        ):
            return self.card
        self.card = card.model_copy(update={"id": "study_card:two", "version": 2})
        return self.card

    async def link_card_to_artifact_owner(self, card: StudyCard) -> str:
        self.linked_plan_id = "study_plan:owner"
        return self.linked_plan_id

    async def get(self, card_id: str) -> StudyCard | None:
        return self.card if self.card.id == card_id else None

    async def list_due(self, now: datetime, *, limit: int) -> list[StudyCard]:
        return [self.card] if self.card.due <= now else []

    async def review(
        self,
        card_id: str,
        *,
        rating: StudyRating,
        request_id: str,
        reviewed_at: datetime,
    ):
        if request_id in self.requests:
            return self.requests[request_id]
        scheduled = StudyScheduler().schedule(
            self.card, rating, reviewed_at=reviewed_at
        )
        self.card = scheduled.card
        result = (self.card, scheduled.review)
        self.requests[request_id] = result
        return result


def test_study_api_accepts_evidence_cards_and_replays_review_requests(
    monkeypatch,
) -> None:
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
        assert store.linked_plan_id == "study_plan:owner"

        request = {
            "request_id": "review-1",
            "rating": "good",
            "reviewed_at": "2026-07-18T12:00:00Z",
        }
        first = client.post("/api/study/cards/study_card:one/reviews", json=request)
        replay = client.post("/api/study/cards/study_card:one/reviews", json=request)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json() == replay.json()


@pytest.mark.asyncio
async def test_source_edit_creates_a_new_version_in_one_transaction(
    monkeypatch,
) -> None:
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


@pytest.mark.asyncio
async def test_card_version_and_artifact_owner_link_share_one_atomic_transaction(
    monkeypatch,
) -> None:
    """Owner publication cannot be repaired after a version commit."""
    import deeper_notebook.study.repository as repository_module

    card_record = (
        _card().model_copy(update={"id": "study_card:atomic"}).model_dump(mode="python")
    )
    queries: list[str] = []
    repo_created = False

    async def fake_query(query: str, values: dict[str, object]):
        queries.append(query)
        if "BEGIN TRANSACTION" in query:
            return [card_record]
        if "study_plan_artifact" in query:
            return [{"plan_id": "study_plan:owner", "syllabus_unit_id": "unit-one"}]
        return []

    async def fake_create(*_args, **_kwargs):
        nonlocal repo_created
        repo_created = True
        return [card_record]

    monkeypatch.setattr(repository_module, "repo_query", fake_query)
    monkeypatch.setattr(repository_module, "repo_create", fake_create)

    await repository_module.StudyRepository().create_card_version_with_artifact_owner(
        _card()
    )

    atomic_queries = [query for query in queries if "BEGIN TRANSACTION" in query]
    assert len(atomic_queries) == 1
    assert "CREATE study_card" in atomic_queries[0]
    assert "CREATE study_plan_card" in atomic_queries[0]
    assert repo_created is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("preflight_owner", "transaction_owners", "expected_error"),
    [
        (None, [{"plan_id": "study_plan:appeared", "syllabus_unit_id": "unit"}], True),
        (("study_plan:expected", "unit"), [], True),
        (
            ("study_plan:expected", "unit"),
            [{"plan_id": "study_plan:other", "syllabus_unit_id": "unit"}],
            True,
        ),
    ],
)
async def test_card_owner_preflight_is_bound_before_any_card_mutation(
    monkeypatch, preflight_owner, transaction_owners, expected_error
) -> None:
    """Owner disappearance/appearance/cross-plan races cannot publish a card."""
    import deeper_notebook.study.repository as repository_module

    card_record = (
        _card().model_copy(update={"id": "study_card:race"}).model_dump(mode="python")
    )
    calls: list[tuple[str, dict[str, object]]] = []
    preflight_calls = 0

    async def fake_query(query: str, values: dict[str, object]):
        nonlocal preflight_calls
        calls.append((query, values))
        if "BEGIN TRANSACTION" in query:
            # The transaction must reject the owner race before returning a
            # card projection; emulate Surreal's THROW with a typed marker.
            if expected_error:
                raise RuntimeError("study_card_artifact_owner_conflict")
            return [card_record]
        if "study_plan_artifact" in query:
            preflight_calls += 1
            return (
                [
                    {
                        "plan_id": preflight_owner[0],
                        "syllabus_unit_id": preflight_owner[1],
                    }
                ]
                if preflight_owner
                else []
            )
        return []

    monkeypatch.setattr(repository_module, "repo_query", fake_query)
    repository = repository_module.StudyRepository()
    with pytest.raises(repository_module.StudyCardArtifactOwnerConflict):
        await repository.create_card_version_with_artifact_owner(_card())
    assert preflight_calls == 1
    transaction_sql, transaction_values = next(
        (query, values) for query, values in calls if "BEGIN TRANSACTION" in query
    )
    assert "$expected_plan_id" in transaction_sql
    assert "array::len($owners) != 1" in transaction_sql
    assert transaction_values["expected_plan_id"] == (
        preflight_owner[0] if preflight_owner else None
    )


@pytest.mark.asyncio
async def test_card_owner_preflight_none_preserves_legacy_unlinked_card(
    monkeypatch,
) -> None:
    import deeper_notebook.study.repository as repository_module

    card_record = (
        _card().model_copy(update={"id": "study_card:legacy"}).model_dump(mode="python")
    )
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_query(query: str, values: dict[str, object]):
        calls.append((query, values))
        if "BEGIN TRANSACTION" in query:
            return [card_record]
        if "study_plan_artifact" in query:
            return []
        if "SELECT * FROM study_card" in query:
            return [card_record]
        return []

    monkeypatch.setattr(repository_module, "repo_query", fake_query)
    created = await repository_module.StudyRepository().create_card_version_with_artifact_owner(
        _card()
    )
    assert created.id == "study_card:legacy"
    transaction_sql, transaction_values = next(
        (query, values) for query, values in calls if "BEGIN TRANSACTION" in query
    )
    assert "$expected_plan_id" in transaction_sql
    assert "array::len($owners) != 0" in transaction_sql
    assert transaction_values["expected_plan_id"] is None


@pytest.mark.asyncio
async def test_card_artifact_link_rejects_ambiguous_plan_owner(monkeypatch) -> None:
    async def fake_query(query: str, values: dict[str, object]):
        assert "study_plan_artifact" in query
        return [
            {"plan_id": "study_plan:one", "syllabus_unit_id": "unit-one"},
            {"plan_id": "study_plan:two", "syllabus_unit_id": "unit-two"},
        ]

    monkeypatch.setattr("deeper_notebook.study.repository.repo_query", fake_query)
    with pytest.raises(StudyRepositoryError, match="artifact owner"):
        await StudyRepository().link_card_to_artifact_owner(_card())


class _OrphanConflictRepository(_MemoryRepository):
    def __init__(self) -> None:
        super().__init__()
        self.created_cards: list[StudyCard] = []

    async def create_card_version_with_artifact_owner(
        self, card: StudyCard
    ) -> StudyCard:
        self.created_cards.append(card)
        raise StudyCardArtifactOwnerConflict("card artifact owner changed")

    async def list_due(self, now: datetime, *, limit: int) -> list[StudyCard]:
        return []


@pytest.mark.asyncio
async def test_study_api_does_not_expose_orphan_card_when_owner_link_conflicts(
    monkeypatch,
) -> None:
    store = _OrphanConflictRepository()
    monkeypatch.setattr(study_router, "_repository", lambda: store)
    app = FastAPI()
    app.include_router(study_router.router, prefix="/api")

    with TestClient(app) as client:
        response = client.post(
            "/api/study/cards",
            json={
                "artifact_id": "studio_artifact:one",
                "artifact_card_id": "card-1",
                "front": "What is the private fact?",
                "back": "It is cited evidence.",
                "citations": [_citation().model_dump(mode="json")],
            },
        )

    assert response.status_code == 409
    assert store.created_cards
    assert await store.list_due(datetime.now(UTC), limit=100) == []
