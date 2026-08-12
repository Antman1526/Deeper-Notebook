"""RED contracts for append-only Study progress projections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.routers import study_plans
from deeper_notebook.study import progress_repository as progress_repository_module
from deeper_notebook.study.assistant_repository import StudyAssistantConflictError
from deeper_notebook.study.contracts import (
    FsrsCardState,
    StudyRating,
    StudyReview,
)
from deeper_notebook.study.plan_repository import StudyPlanConflictError
from deeper_notebook.study.plans import StudyPlan, StudyPlanPreferences
from deeper_notebook.study.progress import (
    StudyAdaptationProposal,
    StudyMasteryProjection,
    StudyProgressAssessment,
    decode_progress_details,
    make_progress_receipt,
    project_mastery,
)

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
PLAN_ID = "study_plan:one"


def _assessment(
    request_id: str,
    *,
    concept_id: str = "concept:kinematics",
    score: float = 0.2,
    created_at: datetime = NOW,
    prerequisite_concept_ids: tuple[str, ...] = ("concept:algebra",),
) -> object:
    return make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=request_id,
        event="assessed",
        created_at=created_at,
        assessment=StudyProgressAssessment(
            concept_id=concept_id,
            unit_id="unit_motion",
            score=score,
            correct=score >= 0.5,
            weight=2.0,
            prerequisite_concept_ids=prerequisite_concept_ids,
        ),
    )


def _review(
    card_id: str = "study_card:one",
    *,
    rating: StudyRating = StudyRating.AGAIN,
    reviewed_at: datetime = NOW,
    due: datetime | None = None,
) -> StudyReview:
    before = FsrsCardState(
        state="review",
        step=None,
        due=due or reviewed_at,
        last_review=reviewed_at - timedelta(days=1),
        stability=2.0,
        difficulty=6.0,
    )
    after = FsrsCardState(
        state="relearning" if rating == StudyRating.AGAIN else "review",
        step=0 if rating == StudyRating.AGAIN else None,
        due=due or reviewed_at + timedelta(days=1),
        last_review=reviewed_at,
        stability=1.0 if rating == StudyRating.AGAIN else 3.0,
        difficulty=7.0 if rating == StudyRating.AGAIN else 5.0,
    )
    return StudyReview(
        card_id=card_id,
        card_version=1,
        request_id=f"review:{card_id}",
        rating=rating,
        reviewed_at=reviewed_at,
        fsrs_state_before=before,
        fsrs_state_after=after,
        lapse_count_after=1 if rating == StudyRating.AGAIN else 0,
    )


def test_mastery_projection_is_deterministic_and_proposal_only() -> None:
    receipts = (_assessment("assessment-one"),)

    first = project_mastery(receipts, (_review(),), now=NOW)
    second = project_mastery(receipts, (_review(),), now=NOW)

    assert isinstance(first, StudyMasteryProjection)
    assert first == second
    assert first.concepts[0].status == "needs_review"
    assert first.proposals[0].action == "prerequisite_detour"
    assert first.proposals[0].status == "proposed"
    assert first.memory_writes == ()


def test_projection_deduplicates_request_ids_and_weights_recent_quiz_outcomes() -> None:
    old = _assessment(
        "old",
        score=0.95,
        created_at=NOW - timedelta(days=40),
        prerequisite_concept_ids=(),
    )
    recent = _assessment(
        "recent",
        score=0.7,
        created_at=NOW - timedelta(days=1),
        prerequisite_concept_ids=(),
    )
    duplicate = recent.model_copy()

    projection = project_mastery((old, recent, duplicate), (), now=NOW)

    assert len(projection.concepts) == 1
    assert projection.concepts[0].attempts == 2
    assert 0.65 < projection.concepts[0].score < 0.8
    assert projection.concepts[0].status == "developing"


def test_lapse_and_due_review_make_schedule_proposal_visible() -> None:
    projection = project_mastery(
        (_assessment("assessment-one", prerequisite_concept_ids=()),),
        (
            _review(
                rating=StudyRating.AGAIN,
                reviewed_at=NOW - timedelta(days=3),
                due=NOW - timedelta(days=1),
            ),
        ),
        now=NOW,
    )

    assert projection.review_consistency.lapses == 1
    assert any(
        proposal.action == "schedule_review" for proposal in projection.proposals
    )


def test_due_review_projection_uses_latest_native_state_per_card() -> None:
    old = _review(
        reviewed_at=NOW - timedelta(days=3),
        due=NOW - timedelta(days=2),
    ).model_copy(update={"request_id": "review:old"})
    latest = _review(
        rating=StudyRating.GOOD,
        reviewed_at=NOW - timedelta(days=1),
        due=NOW + timedelta(days=3),
    ).model_copy(update={"request_id": "review:latest"})

    projection = project_mastery((), (old, latest), now=NOW)

    assert projection.review_consistency.due_reviews == 0
    assert not any(
        proposal.action == "schedule_review" for proposal in projection.proposals
    )


def test_empty_malformed_and_out_of_order_inputs_are_safe_and_stable() -> None:
    malformed = {"request_id": "bad", "event": "not-an-event"}
    projection = project_mastery((malformed,), (), now=NOW)

    assert projection.concepts == ()
    assert projection.proposals == ()
    assert project_mastery((), (), now=NOW) == projection


def test_projection_bounds_infinite_receipt_and_review_iterables() -> None:
    def receipts():
        index = 0
        while True:
            yield _assessment(f"assessment-{index}", prerequisite_concept_ids=())
            index += 1

    projection = project_mastery(receipts(), iter(()), now=NOW)

    assert len(projection.concepts) == 1
    assert projection.concepts[0].attempts == 500


def test_progress_details_are_strict_versioned_json_and_legacy_text_is_ignored() -> (
    None
):
    assessment = StudyProgressAssessment(
        concept_id="concept:one",
        unit_id="unit_one",
        score=0.75,
        correct=True,
        weight=1.0,
    )
    receipt = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id="assessment-one",
        event="assessed",
        created_at=NOW,
        assessment=assessment,
    )

    assert decode_progress_details(receipt.details) == assessment
    assert decode_progress_details("legacy details") is None
    with pytest.raises(ValidationError):
        StudyProgressAssessment(concept_id="concept:one", score=1.1)
    with pytest.raises(ValidationError):
        StudyProgressAssessment(concept_id="concept:one", score=0.5, details="x")


def test_projections_never_create_persistent_inferred_memory() -> None:
    projection = project_mastery((_assessment("assessment-one"),), (), now=NOW)

    assert (
        "memory" not in projection.model_dump(exclude_none=False)
        or projection.memory_writes == ()
    )


def _api_plan(
    *, weekly_minutes: int = 60, version: int = 1, goal: str = "Learn motion"
) -> StudyPlan:
    return StudyPlan(
        plan_id=PLAN_ID,
        goal=goal,
        starting_level="beginner",
        preferences=StudyPlanPreferences(weekly_minutes=weekly_minutes, session_minutes=30),
        source_manifest_sha256="a" * 64,
        approved_syllabus_version=1,
        state="active",
        version=version,
        created_at=NOW,
        updated_at=NOW,
    )


def _api_projection() -> StudyMasteryProjection:
    return StudyMasteryProjection(
        concepts=(
            {
                "concept_id": "concept:motion",
                "unit_id": "unit_motion",
                "score": 0.7,
                "status": "developing",
                "attempts": 1,
                "last_activity_at": NOW,
            },
        ),
        review_consistency={
            "reviews": 0,
            "lapses": 0,
            "due_reviews": 0,
            "on_time_rate": 0.0,
        },
        proposals=(
            {
                "proposal_id": "study_adaptation:extra",
                "concept_id": "concept:motion",
                "unit_id": "unit_motion",
                "action": "extra_practice",
                "title": "Add a short practice block",
                "rationale": "Recent evidence is developing.",
                "status": "proposed",
                "available": True,
            },
        ),
        generated_at=NOW,
    )


def test_decided_proposals_are_not_reenabled_by_plan_projection() -> None:
    projection = _api_projection()
    decided = projection.proposals[0].model_copy(update={"status": "accepted"})
    projected = study_plans._projection_for_plan(
        projection.model_copy(update={"proposals": (decided,)}), _api_plan()
    )

    assert projected.proposals[0].status == "accepted"
    assert projected.proposals[0].available is False


class _ApiPlanRepository:
    def __init__(self, plan: StudyPlan) -> None:
        self.plan = plan
        self.update_calls: list[dict[str, object]] = []
        self.fail_update_once = False

    async def get(self, plan_id: str) -> StudyPlan | None:
        return self.plan if plan_id == self.plan.plan_id else None

    async def update(
        self,
        plan_id: str,
        changes: dict[str, Any],
        *,
        expected_revision: int,
    ) -> StudyPlan:
        if self.fail_update_once:
            self.fail_update_once = False
            raise StudyPlanConflictError("simulated update failure")
        if self.plan.version != expected_revision:
            raise StudyPlanConflictError("study plan revision conflict")
        self.update_calls.append(changes)
        self.plan = StudyPlan.model_validate(
            self.plan.model_dump()
            | changes
            | {"version": self.plan.version + 1, "updated_at": NOW}
        )
        return self.plan


class _ApiProgressRepository:
    def __init__(self) -> None:
        self.projection = _api_projection()
        self.receipts: dict[str, object] = {}
        self.fail_completion_once = False
        self.append_calls = 0

    async def project(self, plan_id: str, *, now: datetime, limit: int = 50):
        return self.projection

    async def get_progress_by_request(self, plan_id: str, request_id: str):
        return self.receipts.get(request_id)

    async def append_progress(self, receipt):
        self.append_calls += 1
        if receipt.request_id.startswith("study_decision_completion:") and self.fail_completion_once:
            self.fail_completion_once = False
            raise progress_repository_module.StudyProgressRepositoryError(
                "simulated append outage"
            )
        existing = self.receipts.get(receipt.request_id)
        if existing is not None:
            if existing.details != receipt.details:
                raise StudyAssistantConflictError("progress request ID was already used")
            return existing
        self.receipts[receipt.request_id] = receipt
        return receipt


def _api_client(
    monkeypatch: pytest.MonkeyPatch,
    plans: _ApiPlanRepository,
    progress: _ApiProgressRepository,
) -> TestClient:
    monkeypatch.setattr(study_plans, "study_workbench_enabled", lambda: True)
    monkeypatch.setattr(study_plans, "_repository", lambda: plans)
    monkeypatch.setattr(study_plans, "_progress_repository", lambda: progress)
    app = FastAPI()
    app.include_router(study_plans.router, prefix="/api")
    return TestClient(app)


def test_api_accept_updates_existing_plan_and_appends_intent_and_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    client = _api_client(monkeypatch, plans, progress)

    response = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": "study_adaptation:extra",
            "decision": "accepted",
            "request_id": "decision-one",
            "expected_revision": 1,
        },
    )

    assert response.status_code == 200
    assert plans.plan.preferences is not None
    assert plans.plan.preferences.weekly_minutes == 90
    assert len(plans.update_calls) == 1
    assert "decision-one" in progress.receipts
    assert any(key.startswith("study_decision_completion:") for key in progress.receipts)


def test_api_accept_retry_reconciles_after_completion_append_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    progress.fail_completion_once = True
    client = _api_client(monkeypatch, plans, progress)
    payload = {
        "proposal_id": "study_adaptation:extra",
        "decision": "accepted",
        "request_id": "decision-retry",
        "expected_revision": 1,
    }

    first = client.post("/api/study/plans/study_plan%3Aone/progress:decision", json=payload)
    second = client.post("/api/study/plans/study_plan%3Aone/progress:decision", json=payload)

    assert first.status_code == 503
    assert second.status_code == 200
    assert plans.plan.version == 2
    assert plans.plan.preferences is not None
    assert plans.plan.preferences.weekly_minutes == 90
    assert len(plans.update_calls) == 1


def test_api_accept_retry_reconciles_when_projection_no_longer_lists_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    progress.fail_completion_once = True
    client = _api_client(monkeypatch, plans, progress)
    payload = {
        "proposal_id": "study_adaptation:extra",
        "decision": "accepted",
        "request_id": "decision-decayed",
        "expected_revision": 1,
    }

    first = client.post("/api/study/plans/study_plan%3Aone/progress:decision", json=payload)
    progress.projection = _api_projection().model_copy(update={"proposals": ()})
    second = client.post("/api/study/plans/study_plan%3Aone/progress:decision", json=payload)

    assert first.status_code == 503
    assert second.status_code == 200
    assert len(plans.update_calls) == 1


def test_api_accept_retry_after_pre_mutation_update_failure_replays_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    plans.fail_update_once = True
    progress = _ApiProgressRepository()
    client = _api_client(monkeypatch, plans, progress)
    payload = {
        "proposal_id": "study_adaptation:extra",
        "decision": "accepted",
        "request_id": "decision-before-update",
        "expected_revision": 1,
    }

    first = client.post("/api/study/plans/study_plan%3Aone/progress:decision", json=payload)
    second = client.post("/api/study/plans/study_plan%3Aone/progress:decision", json=payload)

    assert first.status_code == 409
    assert second.status_code == 200
    assert plans.plan.preferences is not None
    assert plans.plan.preferences.weekly_minutes == 90
    assert len(plans.update_calls) == 1


def test_api_accept_same_request_id_is_idempotent_after_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    client = _api_client(monkeypatch, plans, progress)
    payload = {
        "proposal_id": "study_adaptation:extra",
        "decision": "accepted",
        "request_id": "decision-idempotent",
        "expected_revision": 1,
    }

    first = client.post("/api/study/plans/study_plan%3Aone/progress:decision", json=payload)
    second = client.post("/api/study/plans/study_plan%3Aone/progress:decision", json=payload)

    assert first.status_code == second.status_code == 200
    assert len(plans.update_calls) == 1


def test_api_accept_completion_rejects_changed_expected_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    client = _api_client(monkeypatch, plans, progress)
    first = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": "study_adaptation:extra",
            "decision": "accepted",
            "request_id": "decision-revision-mismatch",
            "expected_revision": 1,
        },
    )
    retry = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": "study_adaptation:extra",
            "decision": "accepted",
            "request_id": "decision-revision-mismatch",
            "expected_revision": 2,
        },
    )

    assert first.status_code == 200
    assert retry.status_code == 409
    assert len(plans.update_calls) == 1


def test_api_dismiss_retry_is_receipt_idempotent_without_second_append(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    client = _api_client(monkeypatch, plans, progress)
    payload = {
        "proposal_id": "study_adaptation:extra",
        "decision": "dismissed",
        "request_id": "decision-dismiss-retry",
    }

    first = client.post("/api/study/plans/study_plan%3Aone/progress:decision", json=payload)
    append_count = progress.append_calls
    second = client.post("/api/study/plans/study_plan%3Aone/progress:decision", json=payload)

    assert first.status_code == second.status_code == 200
    assert progress.append_calls == append_count == 1


def test_api_accept_retry_rejects_unrelated_revision_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    progress.fail_completion_once = True
    client = _api_client(monkeypatch, plans, progress)
    payload = {
        "proposal_id": "study_adaptation:extra",
        "decision": "accepted",
        "request_id": "decision-conflict",
        "expected_revision": 1,
    }

    first = client.post("/api/study/plans/study_plan%3Aone/progress:decision", json=payload)
    plans.plan = _api_plan(weekly_minutes=90, version=2, goal="Unrelated edit")
    second = client.post("/api/study/plans/study_plan%3Aone/progress:decision", json=payload)

    assert first.status_code == 503
    assert second.status_code == 409


def test_api_feature_off_returns_404_before_malformed_progress_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(study_plans, "study_workbench_enabled", lambda: False)
    app = FastAPI()
    app.include_router(study_plans.router, prefix="/api")
    client = TestClient(app)

    response = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={"unexpected": True},
    )

    assert response.status_code == 404
