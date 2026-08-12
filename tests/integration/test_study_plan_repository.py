"""Real-SurrealDB persistence contracts for Study Workbench plans."""

from __future__ import annotations

import pytest

from deeper_notebook.database.repository import repo_query
from deeper_notebook.study.plan_repository import StudyPlanRepository
from deeper_notebook.study.plans import (
    StudyPlan,
    StudyPlanPreferences,
    StudySyllabus,
    StudySyllabusUnit,
)

pytestmark = pytest.mark.integration_surreal


def _plan() -> StudyPlan:
    return StudyPlan(
        plan_id="study_plan:integration",
        goal="Verify persisted syllabus versions",
        starting_level="beginner",
        preferences=StudyPlanPreferences(weekly_minutes=120, session_minutes=30),
        source_manifest_sha256="a" * 64,
    )


def _syllabus(version: int) -> StudySyllabus:
    return StudySyllabus(
        plan_id="study_plan:integration",
        version=version,
        source_manifest_sha256="a" * 64,
        units=[
            StudySyllabusUnit(
                unit_id=f"foundations-{version}",
                title=f"Foundations {version}",
                objectives=["Explain the core idea"],
                estimated_minutes=60,
                source_ids=["source:read-only"],
            )
        ],
    )


async def test_plan_create_list_link_version_and_optimistic_approval(clean_namespace):
    repository = StudyPlanRepository()

    created = await repository.create(_plan())
    assert created.plan_id == "study_plan:integration"
    assert created.version == 1

    linked = await repository.add_source(created.plan_id, "source:read-only")
    assert linked.source_id == "source:read-only"

    loaded = await repository.get(created.plan_id)
    assert loaded is not None
    assert [link.source_id for link in loaded.source_links] == ["source:read-only"]
    assert loaded.version == 2

    listed = await repository.list(limit=10)
    assert [plan.plan_id for plan in listed] == ["study_plan:integration"]

    await repository.save_syllabus(_syllabus(1))
    await repository.save_syllabus(_syllabus(2))
    syllabus_rows = await repo_query(
        "SELECT plan_id, version FROM study_syllabus WHERE plan_id = $plan_id "
        "ORDER BY version ASC",
        {"plan_id": "study_plan:integration"},
    )
    assert [row["version"] for row in syllabus_rows] == [1, 2]

    approved = await repository.approve_syllabus(
        created.plan_id,
        syllabus_version=2,
        expected_revision=2,
    )
    assert approved.state == "approved"
    assert approved.approved_syllabus_version == 2
    assert approved.version == 3

    current = await repository.get(created.plan_id)
    assert current is not None
    assert current.state == "approved"
    assert current.approved_syllabus_version == 2


async def test_plan_source_removal_does_not_delete_source_record(clean_namespace):
    repository = StudyPlanRepository()
    await repository.create(_plan())
    await repository.add_source("study_plan:integration", "source:owned-elsewhere")

    removed = await repository.remove_source(
        "study_plan:integration", "source:owned-elsewhere"
    )
    assert removed is True

    source_rows = await repo_query(
        "SELECT id FROM source WHERE id = $source_id",
        {"source_id": "source:owned-elsewhere"},
    )
    assert source_rows == []
    loaded = await repository.get("study_plan:integration")
    assert loaded is not None
    assert loaded.source_links == ()
