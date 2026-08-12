"""Real-SurrealDB proof for Task 14's native review projection and receipt race."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from deeper_notebook.database.repository import repo_query
from deeper_notebook.evaluation.schemas import EvidenceSpan, hash_source_text
from deeper_notebook.study.assistant_repository import StudyAssistantRepository
from deeper_notebook.study.assistants import StudyProgressReceipt
from deeper_notebook.study.contracts import StudyCard, StudyRating
from deeper_notebook.study.plan_repository import StudyPlanRepository
from deeper_notebook.study.plans import StudyPlan, StudyPlanPreferences
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
