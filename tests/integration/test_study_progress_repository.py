"""Real-SurrealDB proof for Task 14's native review projection and receipt race."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from api.routers import study_plans
from api.schemas.study_plans import StudyProgressDecisionRequest
from deeper_notebook.database.repository import repo_query
from deeper_notebook.evaluation.schemas import EvidenceSpan, hash_source_text
from deeper_notebook.study.assistant_repository import StudyAssistantRepository
from deeper_notebook.study.assistants import StudyProgressReceipt
from deeper_notebook.study.contracts import StudyCard, StudyRating
from deeper_notebook.study.plan_repository import StudyPlanRepository
from deeper_notebook.study.plans import StudyPlan, StudyPlanPreferences
from deeper_notebook.study.progress import (
    decision_claim_request_id,
    decision_terminal_request_id,
    make_progress_receipt,
)
from deeper_notebook.study.progress_repository import StudyProgressRepository
from deeper_notebook.study.repository import StudyRepository

pytestmark = pytest.mark.integration_surreal

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _card() -> StudyCard:
    source_text = "Native review projection source"
    return StudyCard(
        artifact_id="studio_artifact:progress-integration",
        artifact_card_id="card-one",
        front="What is the native review?",
        back="A durable FSRS receipt.",
        citations=[
            EvidenceSpan(
                source_id="source:progress-integration",
                source_content_sha256=hash_source_text(source_text),
                start=0,
                end=len(source_text),
                quote=source_text,
            )
        ],
    )


async def test_native_review_projection_resolves_plan_card_record_ids(clean_namespace):
    plan_id = "study_plan:progress-review-integration"
    plan_repository = StudyPlanRepository()
    await plan_repository.create(
        StudyPlan(
            plan_id=plan_id,
            goal="Verify native review projection",
            starting_level="beginner",
            preferences=StudyPlanPreferences(weekly_minutes=120, session_minutes=30),
        )
    )
    card = await StudyRepository().create_card_version(_card())
    assert card.id is not None
    card_id = card.id
    await repo_query(
        "CREATE study_plan_card CONTENT $link RETURN AFTER;",
        {
            "link": {
                "plan_id": plan_id,
                "card_id": card_id,
                "syllabus_unit_id": "unit_native",
            }
        },
    )
    await StudyRepository().review(
        card_id,
        rating=StudyRating.GOOD,
        request_id="review-progress-integration",
        reviewed_at=NOW,
    )

    reviews = await StudyProgressRepository().list_reviews(plan_id)

    assert len(reviews) == 1
    assert reviews[0].card_id == card_id
    assert reviews[0].request_id == "review-progress-integration"
    assert reviews[0].rating == StudyRating.GOOD


async def test_progress_append_race_re_reads_unique_winner(clean_namespace):
    plan_id = "study_plan:progress-race-integration"
    await StudyPlanRepository().create(
        StudyPlan(
            plan_id=plan_id,
            goal="Verify append-only receipt race",
            starting_level="beginner",
        )
    )
    receipt = StudyProgressReceipt(
        plan_id=plan_id,
        request_id="progress-race-integration",
        unit_id="unit_native",
        event="started",
        details="Native append race",
        created_at=NOW,
    )
    assistant = StudyAssistantRepository()

    results = await asyncio.gather(
        assistant.append_progress(receipt),
        assistant.append_progress(receipt),
        return_exceptions=True,
    )

    assert all(not isinstance(result, BaseException) for result in results)
    assert results[0] == results[1]
    persisted = await assistant.list_progress(plan_id)
    assert len(persisted) == 1
    assert persisted[0].model_copy(update={"receipt_id": None}) == receipt


async def test_real_surreal_decision_claim_serializes_independent_clients(clean_namespace):
    """A shared deterministic claim permits at most one native mutation."""

    plan_id = "study_plan:progress-decision-concurrency"
    await StudyPlanRepository().create(
        StudyPlan(
            plan_id=plan_id,
            goal="Verify serialized adaptation decisions",
            starting_level="beginner",
            preferences=StudyPlanPreferences(weekly_minutes=60, session_minutes=30),
        )
    )
    proposal_id = "study_adaptation:extra"
    claim_id = decision_claim_request_id(plan_id, proposal_id)
    terminal_id = decision_terminal_request_id(plan_id, proposal_id)
    claim_details = tuple(
        {
            "client_request_id": f"real-client-{index}",
            "decision": "dismissed",
            "phase": "claim",
            "proposal_id": proposal_id,
        }
        for index in range(2)
    )

    async def contend(index: int):
        assistant = StudyAssistantRepository()
        claim = make_progress_receipt(
            plan_id=plan_id,
            request_id=claim_id,
            event="decision",
            created_at=NOW,
            details=claim_details[index],
        )
        try:
            await assistant.append_progress(claim)
        except Exception as exc:  # one typed loser is expected
            return index, exc
        terminal = make_progress_receipt(
            plan_id=plan_id,
            request_id=terminal_id,
            event="decision",
            created_at=NOW,
            details={
                "claim_request_id": claim_id,
                "client_request_id": claim_details[index]["client_request_id"],
                "decision": "dismissed",
                "phase": "terminal",
                "proposal_id": proposal_id,
            },
        )
        await assistant.append_progress(terminal)
        return index, None

    results = await asyncio.gather(contend(0), contend(1))
    assert sum(error is None for _index, error in results) == 1

    assistant = StudyAssistantRepository()
    persisted = await assistant.list_progress(plan_id, limit=50)
    assert [item.request_id for item in persisted].count(claim_id) == 1
    assert [item.request_id for item in persisted].count(terminal_id) == 1

    plan = await StudyPlanRepository().get(plan_id)
    assert plan is not None
    assert plan.preferences is not None
    # A dismiss-only contention must never mutate the weekly budget; this is
    # also the <=1-mutation bound for a shared proposal claim.
    assert plan.preferences.weekly_minutes == 60


async def test_real_surreal_accept_mutation_updates_plan_preferences(clean_namespace):
    """The existing plan mutation used by Accept is executable on SurrealDB."""

    plan_id = "study_plan:progress-accept-mutation"
    repository = StudyPlanRepository()
    await repository.create(
        StudyPlan(
            plan_id=plan_id,
            goal="Verify accepted practice mutation",
            starting_level="beginner",
            preferences=StudyPlanPreferences(weekly_minutes=60, session_minutes=30),
        )
    )

    updated = await repository.update(
        plan_id,
        {
            "preferences": StudyPlanPreferences(
                weekly_minutes=90, session_minutes=30
            )
        },
        expected_revision=1,
    )

    assert updated.version == 2
    assert updated.preferences is not None
    assert updated.preferences.weekly_minutes == 90


async def test_real_surreal_orphan_terminal_is_rejected_by_api_authority(
    clean_namespace,
    monkeypatch: pytest.MonkeyPatch,
):
    """A persisted terminal without its deterministic claim cannot authorize replay."""

    plan_id = "study_plan:progress-orphan-terminal"
    plan_repository = StudyPlanRepository()
    await plan_repository.create(
        StudyPlan(
            plan_id=plan_id,
            goal="Reject orphan adaptation terminal",
            starting_level="beginner",
            preferences=StudyPlanPreferences(weekly_minutes=60, session_minutes=30),
        )
    )
    proposal_id = "study_adaptation:extra"
    client_request_id = "real-orphan-terminal"
    terminal_id = decision_terminal_request_id(plan_id, proposal_id)
    claim_id = decision_claim_request_id(plan_id, proposal_id)
    terminal = make_progress_receipt(
        plan_id=plan_id,
        request_id=terminal_id,
        event="decision",
        created_at=NOW,
        details={
            "base_revision": 1,
            "claim_request_id": claim_id,
            "client_request_id": client_request_id,
            "decision": "accepted",
            "phase": "terminal",
            "proposal_id": proposal_id,
            "target_plan_sha256": "a" * 64,
        },
    )
    await StudyAssistantRepository().append_progress(terminal)

    monkeypatch.setattr(study_plans, "_repository", lambda: plan_repository)
    monkeypatch.setattr(
        study_plans,
        "_progress_repository",
        lambda: StudyProgressRepository(),
    )
    payload = StudyProgressDecisionRequest(
        proposal_id=proposal_id,
        decision="accepted",
        request_id=client_request_id,
        expected_revision=1,
    )

    with pytest.raises(HTTPException) as raised:
        await study_plans._decide_study_plan_progress(plan_id, payload)

    assert raised.value.status_code == 409
