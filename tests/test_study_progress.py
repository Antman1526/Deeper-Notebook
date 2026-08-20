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
    decision_claim_request_id,
    decision_terminal_request_id,
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


def test_future_decision_receipts_do_not_change_current_proposal_status() -> None:
    baseline = project_mastery((_assessment("assessment-future"),), (), now=NOW)
    proposal_id = baseline.proposals[0].proposal_id
    future = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id="future-dismiss",
        event="decision",
        created_at=NOW + timedelta(minutes=5),
        details={
            "decision": "dismissed",
            "phase": "completion",
            "proposal_id": proposal_id,
        },
    )

    projection = project_mastery(
        (_assessment("assessment-future"), future), (), now=NOW
    )

    assert (
        next(
            item for item in projection.proposals if item.proposal_id == proposal_id
        ).status
        == "proposed"
    )


def _api_plan(
    *, weekly_minutes: int = 60, version: int = 1, goal: str = "Learn motion"
) -> StudyPlan:
    return StudyPlan(
        plan_id=PLAN_ID,
        goal=goal,
        starting_level="beginner",
        preferences=StudyPlanPreferences(
            weekly_minutes=weekly_minutes, session_minutes=30
        ),
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
        if (
            receipt.request_id.startswith("study_decision_completion:")
            and self.fail_completion_once
        ):
            self.fail_completion_once = False
            raise progress_repository_module.StudyProgressRepositoryError(
                "simulated append outage"
            )
        existing = self.receipts.get(receipt.request_id)
        if existing is not None:
            if existing.details != receipt.details:
                raise StudyAssistantConflictError(
                    "progress request ID was already used"
                )
            return existing
        self.receipts[receipt.request_id] = receipt
        return receipt


class _FailAfterClaimProgressRepository(_ApiProgressRepository):
    def __init__(self) -> None:
        super().__init__()
        self.fail_claim_after_store = True

    async def append_progress(self, receipt):
        result = await super().append_progress(receipt)
        if (
            self.fail_claim_after_store
            and receipt.request_id
            == decision_claim_request_id(PLAN_ID, "study_adaptation:extra")
        ):
            self.fail_claim_after_store = False
            raise progress_repository_module.StudyProgressRepositoryError(
                "simulated claim response loss"
            )
        return result


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
    assert any(
        key.startswith("study_decision_completion:") for key in progress.receipts
    )
    intent = progress.receipts["decision-one"]
    assert "target_preferences" not in (study_plans._progress_details(intent) or {})
    assert (study_plans._progress_details(intent) or {}).get(
        "target_weekly_minutes"
    ) == 90


def test_api_accept_with_maximum_network_scope_keeps_intent_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    plans.plan = _api_plan()
    plans.plan = plans.plan.model_copy(
        update={
            "preferences": plans.plan.preferences.model_copy(
                update={
                    "network_allowed": True,
                    "model_route": "cloud",
                    "approved_network_scope": tuple(
                        f"https://example.edu/{index}/{'x' * 470}" for index in range(8)
                    ),
                }
            )
        }
    )
    progress = _ApiProgressRepository()
    client = _api_client(monkeypatch, plans, progress)

    response = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": "study_adaptation:extra",
            "decision": "accepted",
            "request_id": "decision-scopes",
            "expected_revision": 1,
        },
    )

    assert response.status_code == 200
    intent = progress.receipts["decision-scopes"]
    assert len(intent.details.encode("utf-8")) <= 2_000
    assert "target_preferences" not in intent.details


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

    first = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )
    second = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )

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

    first = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )
    progress.projection = _api_projection().model_copy(update={"proposals": ()})
    second = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )

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

    first = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )
    second = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )

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

    first = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )
    second = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )

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


def test_api_distinct_dismiss_requests_share_one_proposal_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    client = _api_client(monkeypatch, plans, progress)

    first = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": "study_adaptation:extra",
            "decision": "dismissed",
            "request_id": "dismiss-client-one",
        },
    )
    second = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": "study_adaptation:extra",
            "decision": "dismissed",
            "request_id": "dismiss-client-two",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert (
        decision_claim_request_id(PLAN_ID, "study_adaptation:extra")
        in progress.receipts
    )
    assert (
        decision_terminal_request_id(PLAN_ID, "study_adaptation:extra")
        in progress.receipts
    )


def test_api_accept_and_dismiss_contend_on_one_claim_without_double_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    client = _api_client(monkeypatch, plans, progress)

    accepted = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": "study_adaptation:extra",
            "decision": "accepted",
            "request_id": "accept-client",
            "expected_revision": 1,
        },
    )
    dismissed = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": "study_adaptation:extra",
            "decision": "dismissed",
            "request_id": "dismiss-client",
        },
    )

    assert accepted.status_code == 200
    assert dismissed.status_code == 409
    assert plans.plan.preferences is not None
    assert plans.plan.preferences.weekly_minutes == 90
    assert len(plans.update_calls) == 1


def test_api_same_client_replays_after_claim_response_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _FailAfterClaimProgressRepository()
    client = _api_client(monkeypatch, plans, progress)
    payload = {
        "proposal_id": "study_adaptation:extra",
        "decision": "accepted",
        "request_id": "accept-after-claim-loss",
        "expected_revision": 1,
    }

    first = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )
    second = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )

    assert first.status_code == 503
    assert second.status_code == 200
    assert plans.plan.preferences is not None
    assert plans.plan.preferences.weekly_minutes == 90
    assert len(plans.update_calls) == 1


@pytest.mark.parametrize("receipt_kind", ["claim", "terminal"])
def test_api_mismatched_deterministic_decision_receipt_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    receipt_kind: str,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    proposal_id = "study_adaptation:extra"
    request_id = "decision-mismatch"
    receipt_id = (
        decision_claim_request_id(PLAN_ID, proposal_id)
        if receipt_kind == "claim"
        else decision_terminal_request_id(PLAN_ID, proposal_id)
    )
    details = (
        {
            "base_plan_sha256": "a" * 64,
            "base_revision": 1,
            "client_request_id": "different-client",
            "decision": "accepted",
            "phase": "claim",
            "proposal_id": proposal_id,
            "target_plan_sha256": "b" * 64,
            "target_weekly_minutes": 90,
        }
        if receipt_kind == "claim"
        else {
            "claim_request_id": decision_claim_request_id(PLAN_ID, proposal_id),
            "client_request_id": "different-client",
            "decision": "accepted",
            "phase": "terminal",
            "proposal_id": proposal_id,
            "target_plan_sha256": "b" * 64,
        }
    )
    progress.receipts[receipt_id] = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=receipt_id,
        event="decision",
        created_at=NOW,
        details=details,
    )
    client = _api_client(monkeypatch, plans, progress)

    response = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": proposal_id,
            "decision": "accepted",
            "request_id": request_id,
            "expected_revision": 1,
        },
    )

    assert response.status_code == 409
    assert plans.update_calls == []


@pytest.mark.parametrize("phase", ["intent", "completion"])
def test_api_corrupt_decision_receipts_fail_closed_as_conflict(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    request_id = f"decision-corrupt-{phase}"
    receipt_request_id = (
        request_id
        if phase == "intent"
        else study_plans._completion_request_id(PLAN_ID, request_id)
    )
    details = (
        {
            "base_revision": 1,
            "base_plan_sha256": "not-a-hash",
            "decision": "accepted",
            "phase": "intent",
            "proposal_id": "study_adaptation:extra",
            "target_plan_sha256": "b" * 64,
            "target_weekly_minutes": 90,
        }
        if phase == "intent"
        else {
            "base_revision": 1,
            "base_plan_sha256": "a" * 64,
            "decision": "accepted",
            "intent_request_id": request_id,
            "phase": "completion",
            "proposal_id": "study_adaptation:extra",
            "target_plan_sha256": "not-a-hash",
        }
    )
    progress.receipts[receipt_request_id] = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=receipt_request_id,
        event="decision",
        created_at=NOW,
        details=details,
    )
    client = _api_client(monkeypatch, plans, progress)

    response = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": "study_adaptation:extra",
            "decision": "accepted",
            "request_id": request_id,
            "expected_revision": 1,
        },
    )

    assert response.status_code == 409
    assert plans.update_calls == []


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

    first = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )
    append_count = progress.append_calls
    second = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )

    assert first.status_code == second.status_code == 200
    assert progress.append_calls == append_count == 2


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

    first = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )
    plans.plan = _api_plan(weekly_minutes=90, version=2, goal="Unrelated edit")
    second = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )

    assert first.status_code == 503
    assert second.status_code == 409


def test_api_dismiss_requires_proposed_and_replays_before_state_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    client = _api_client(monkeypatch, plans, progress)
    payload = {
        "proposal_id": "study_adaptation:extra",
        "decision": "dismissed",
        "request_id": "decision-dismiss-state",
    }

    first = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )
    assert first.status_code == 200
    progress.projection = _api_projection().model_copy(
        update={
            "proposals": (
                _api_projection()
                .proposals[0]
                .model_copy(update={"status": "accepted"}),
            )
        }
    )
    replay = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision", json=payload
    )
    assert replay.status_code == 200

    progress.receipts.pop("decision-dismiss-state", None)
    rejected = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={**payload, "request_id": "decision-dismiss-new"},
    )
    assert rejected.status_code == 409


def _decision_receipt_details(
    plans: _ApiPlanRepository,
    *,
    proposal_id: str,
    client_request_id: str,
    decision: str,
    base_revision: int = 1,
    target_plan_sha256: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    base_plan = _api_plan(version=base_revision)
    target_preferences = base_plan.preferences.model_copy(
        update={
            "weekly_minutes": base_plan.preferences.weekly_minutes
            + base_plan.preferences.session_minutes
        }
    )
    claim_target = target_plan_sha256 or study_plans._plan_fingerprint(
        base_plan, preferences=target_preferences
    )
    claim = study_plans._claim_payload(
        client_request_id=client_request_id,
        decision=decision,
        proposal_id=proposal_id,
        base_revision=base_revision if decision == "accepted" else None,
        base_plan_sha256=study_plans._plan_fingerprint(base_plan)
        if decision == "accepted"
        else None,
        target_plan_sha256=claim_target if decision == "accepted" else None,
        target_weekly_minutes=target_preferences.weekly_minutes
        if decision == "accepted"
        else None,
    )
    terminal = study_plans._terminal_payload(
        claim_request_id=decision_claim_request_id(PLAN_ID, proposal_id),
        client_request_id=client_request_id,
        decision=decision,
        proposal_id=proposal_id,
        base_revision=base_revision if decision == "accepted" else None,
        target_plan_sha256=claim_target if decision == "accepted" else None,
    )
    return claim, terminal


@pytest.mark.parametrize("event", ["failed", "cancelled", "assessed"])
def test_api_decision_receipts_require_decision_event(
    monkeypatch: pytest.MonkeyPatch,
    event: str,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    proposal_id = "study_adaptation:extra"
    client_request_id = "bad-event"
    claim_details, terminal_details = _decision_receipt_details(
        plans,
        proposal_id=proposal_id,
        client_request_id=client_request_id,
        decision="accepted",
    )
    claim_id = decision_claim_request_id(PLAN_ID, proposal_id)
    terminal_id = decision_terminal_request_id(PLAN_ID, proposal_id)
    progress.receipts[claim_id] = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=claim_id,
        event=event,
        created_at=NOW,
        details=claim_details,
    )
    progress.receipts[terminal_id] = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=terminal_id,
        event=event,
        created_at=NOW + timedelta(seconds=1),
        details=terminal_details,
    )
    client = _api_client(monkeypatch, plans, progress)

    response = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": proposal_id,
            "decision": "accepted",
            "request_id": client_request_id,
            "expected_revision": 1,
        },
    )

    assert response.status_code == 409
    assert plans.update_calls == []


@pytest.mark.parametrize("envelope", ["plan_id", "request_id", "created_at"])
def test_api_decision_receipts_require_exact_envelope(
    monkeypatch: pytest.MonkeyPatch,
    envelope: str,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    proposal_id = "study_adaptation:extra"
    client_request_id = "bad-envelope"
    claim_details, terminal_details = _decision_receipt_details(
        plans,
        proposal_id=proposal_id,
        client_request_id=client_request_id,
        decision="accepted",
    )
    claim_id = decision_claim_request_id(PLAN_ID, proposal_id)
    terminal_id = decision_terminal_request_id(PLAN_ID, proposal_id)
    claim = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=claim_id,
        event="decision",
        created_at=NOW,
        details=claim_details,
    )
    terminal = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=terminal_id,
        event="decision",
        created_at=NOW + timedelta(seconds=1),
        details=terminal_details,
    )
    if envelope == "plan_id":
        claim = claim.model_copy(update={"plan_id": "study_plan:other"})
    elif envelope == "request_id":
        claim = claim.model_copy(update={"request_id": "not-the-claim-id"})
    else:
        claim = claim.model_copy(update={"created_at": NOW + timedelta(days=1)})
    progress.receipts[claim_id] = claim
    progress.receipts[terminal_id] = terminal
    client = _api_client(monkeypatch, plans, progress)

    response = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": proposal_id,
            "decision": "accepted",
            "request_id": client_request_id,
            "expected_revision": 1,
        },
    )

    assert response.status_code == 409
    assert plans.update_calls == []


def test_api_accepted_terminal_requires_matching_claim_and_mutated_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    proposal_id = "study_adaptation:extra"
    client_request_id = "orphan-terminal"
    _claim, terminal_details = _decision_receipt_details(
        plans,
        proposal_id=proposal_id,
        client_request_id=client_request_id,
        decision="accepted",
    )
    terminal_id = decision_terminal_request_id(PLAN_ID, proposal_id)
    progress.receipts[terminal_id] = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=terminal_id,
        event="decision",
        created_at=NOW,
        details=terminal_details,
    )
    client = _api_client(monkeypatch, plans, progress)

    response = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": proposal_id,
            "decision": "accepted",
            "request_id": client_request_id,
            "expected_revision": 1,
        },
    )

    assert response.status_code == 409
    assert plans.update_calls == []


@pytest.mark.parametrize(
    "mutate_plan, terminal_base_revision, target_hash",
    [
        (False, 1, None),
        (True, 2, None),
        (True, 1, "c" * 64),
    ],
)
def test_api_accepted_terminal_replay_binds_revision_and_target_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
    mutate_plan: bool,
    terminal_base_revision: int,
    target_hash: str | None,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    proposal_id = "study_adaptation:extra"
    client_request_id = "terminal-authority"
    claim_details, terminal_details = _decision_receipt_details(
        plans,
        proposal_id=proposal_id,
        client_request_id=client_request_id,
        decision="accepted",
        base_revision=1,
        target_plan_sha256=target_hash,
    )
    if mutate_plan:
        plans.plan = _api_plan(version=2, weekly_minutes=90)
    claim_id = decision_claim_request_id(PLAN_ID, proposal_id)
    terminal_id = decision_terminal_request_id(PLAN_ID, proposal_id)
    progress.receipts[claim_id] = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=claim_id,
        event="decision",
        created_at=NOW,
        details=claim_details,
    )
    if terminal_base_revision != 1:
        terminal_details["base_revision"] = terminal_base_revision
    progress.receipts[terminal_id] = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=terminal_id,
        event="decision",
        created_at=NOW + timedelta(seconds=1),
        details=terminal_details,
    )
    client = _api_client(monkeypatch, plans, progress)

    response = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": proposal_id,
            "decision": "accepted",
            "request_id": client_request_id,
            "expected_revision": 1,
        },
    )

    assert response.status_code == 409
    assert plans.update_calls == []


@pytest.mark.parametrize(
    "claim_offset, terminal_offset",
    [
        pytest.param(
            timedelta(seconds=-1),
            timedelta(seconds=-2),
            id="terminal-before-claim",
        ),
        pytest.param(
            timedelta(seconds=-1),
            timedelta(days=1),
            id="terminal-in-future",
        ),
    ],
)
def test_api_accepted_terminal_replay_requires_claim_before_terminal_and_not_future(
    monkeypatch: pytest.MonkeyPatch,
    claim_offset: timedelta,
    terminal_offset: timedelta,
) -> None:
    now = datetime.now(UTC)
    claim_at = now + claim_offset
    terminal_at = now + terminal_offset
    plans = _ApiPlanRepository(_api_plan(version=2, weekly_minutes=90))
    progress = _ApiProgressRepository()
    proposal_id = "study_adaptation:extra"
    client_request_id = "terminal-order"
    claim_details, terminal_details = _decision_receipt_details(
        plans,
        proposal_id=proposal_id,
        client_request_id=client_request_id,
        decision="accepted",
    )
    claim_id = decision_claim_request_id(PLAN_ID, proposal_id)
    terminal_id = decision_terminal_request_id(PLAN_ID, proposal_id)
    target_plan = _api_plan(version=2, weekly_minutes=90)
    terminal_details["target_plan_sha256"] = study_plans._plan_fingerprint(target_plan)
    progress.receipts[claim_id] = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=claim_id,
        event="decision",
        created_at=claim_at,
        details=claim_details,
    )
    progress.receipts[terminal_id] = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=terminal_id,
        event="decision",
        created_at=terminal_at,
        details=terminal_details,
    )
    client = _api_client(monkeypatch, plans, progress)

    response = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": proposal_id,
            "decision": "accepted",
            "request_id": client_request_id,
            "expected_revision": 1,
        },
    )

    assert response.status_code == 409


def test_api_accepted_terminal_replay_returns_valid_current_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan(version=2, weekly_minutes=90))
    progress = _ApiProgressRepository()
    proposal_id = "study_adaptation:extra"
    client_request_id = "terminal-valid-replay"
    claim_details, terminal_details = _decision_receipt_details(
        plans,
        proposal_id=proposal_id,
        client_request_id=client_request_id,
        decision="accepted",
    )
    target_plan = plans.plan
    target_hash = study_plans._plan_fingerprint(target_plan)
    claim_details["target_plan_sha256"] = target_hash
    terminal_details["target_plan_sha256"] = target_hash
    claim_id = decision_claim_request_id(PLAN_ID, proposal_id)
    terminal_id = decision_terminal_request_id(PLAN_ID, proposal_id)
    progress.receipts[claim_id] = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=claim_id,
        event="decision",
        created_at=NOW,
        details=claim_details,
    )
    progress.receipts[terminal_id] = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=terminal_id,
        event="decision",
        created_at=NOW + timedelta(seconds=1),
        details=terminal_details,
    )
    client = _api_client(monkeypatch, plans, progress)

    response = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": proposal_id,
            "decision": "accepted",
            "request_id": client_request_id,
            "expected_revision": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "accepted"
    assert plans.update_calls == []


def test_api_dismiss_terminal_replay_requires_matching_claim_and_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = _ApiPlanRepository(_api_plan())
    progress = _ApiProgressRepository()
    proposal_id = "study_adaptation:extra"
    client_request_id = "dismiss-terminal"
    claim_details, terminal_details = _decision_receipt_details(
        plans,
        proposal_id=proposal_id,
        client_request_id=client_request_id,
        decision="dismissed",
    )
    claim_id = decision_claim_request_id(PLAN_ID, proposal_id)
    terminal_id = decision_terminal_request_id(PLAN_ID, proposal_id)
    progress.receipts[terminal_id] = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=terminal_id,
        event="decision",
        created_at=NOW,
        details=terminal_details,
    )
    client = _api_client(monkeypatch, plans, progress)
    orphan = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": proposal_id,
            "decision": "dismissed",
            "request_id": client_request_id,
        },
    )
    assert orphan.status_code == 409

    progress.receipts[claim_id] = make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=claim_id,
        event="decision",
        created_at=NOW - timedelta(seconds=1),
        details=claim_details,
    )
    valid = client.post(
        "/api/study/plans/study_plan%3Aone/progress:decision",
        json={
            "proposal_id": proposal_id,
            "decision": "dismissed",
            "request_id": client_request_id,
        },
    )
    assert valid.status_code == 200


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
