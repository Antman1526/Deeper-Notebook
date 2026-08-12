"""Strict immutable contracts for Study Workbench plans and syllabi."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from deeper_notebook.study.plans import (
    StudyActivity,
    StudyPlan,
    StudyPlanPreferences,
    StudyPlanSourceLink,
    StudySyllabus,
    StudySyllabusUnit,
)


def _activity() -> StudyActivity:
    return StudyActivity(
        activity_id="recall-quiz",
        kind="quiz",
        title="Recall quiz",
        estimated_minutes=20,
    )


def _unit(unit_id: str = "foundations") -> StudySyllabusUnit:
    return StudySyllabusUnit(
        unit_id=unit_id,
        title="Foundations",
        objectives=["Explain the core idea"],
        estimated_minutes=60,
        activities=[_activity()],
    )


def _plan(**overrides: object) -> StudyPlan:
    values: dict[str, object] = {
        "plan_id": "study_plan:one",
        "goal": "Learn the foundations",
        "starting_level": "beginner",
        "target_date": date(2026, 9, 1),
        "preferences": StudyPlanPreferences(
            weekly_minutes=240,
            session_minutes=45,
        ),
        "source_links": [StudyPlanSourceLink(source_id="source:one")],
        "source_manifest_sha256": "b" * 64,
        "approved_syllabus_version": 1,
    }
    values.update(overrides)
    return StudyPlan(**values)


def test_syllabus_is_bounded_versioned_and_requires_unique_units() -> None:
    syllabus = StudySyllabus(
        plan_id="study_plan:one",
        version=1,
        source_manifest_sha256="a" * 64,
        units=[_unit()],
    )

    assert syllabus.schema_version == 1
    assert syllabus.units[0].unit_id == "foundations"

    with pytest.raises(ValidationError):
        StudySyllabus(
            plan_id="study_plan:one",
            version=1,
            source_manifest_sha256="a" * 64,
            units=[_unit(), _unit()],
        )

    with pytest.raises(ValidationError):
        StudySyllabus(
            plan_id="study_plan:one",
            version=1,
            source_manifest_sha256="a" * 64,
            units=[_unit(f"unit-{index}") for index in range(65)],
        )

    with pytest.raises(ValidationError):
        StudySyllabusUnit(
            unit_id="foundations",
            title="Foundations",
            objectives=[f"Objective {index}" for index in range(21)],
            estimated_minutes=60,
        )


def test_contracts_reject_blank_text_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        StudyPlan(plan_id="study_plan:one", goal="  ")

    with pytest.raises(ValidationError):
        StudySyllabusUnit(
            unit_id="foundations",
            title="Foundations",
            objectives=["\t"],
            estimated_minutes=60,
        )

    with pytest.raises(ValidationError):
        StudyActivity(
            activity_id="recall-quiz",
            kind="quiz",
            title="Recall quiz",
            estimated_minutes=20,
            untrusted=True,
        )


def test_contracts_are_frozen_and_reject_naive_datetimes() -> None:
    plan = _plan()

    with pytest.raises(ValidationError):
        plan.goal = "A different goal"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        StudySyllabus(
            plan_id="study_plan:one",
            version=1,
            source_manifest_sha256="a" * 64,
            units=[_unit()],
            approved_at=datetime(2026, 8, 11),
        )

    with pytest.raises(ValidationError):
        _plan(created_at=datetime(2026, 8, 11))

    syllabus = StudySyllabus(
        plan_id="study_plan:one",
        version=1,
        source_manifest_sha256="a" * 64,
        units=[_unit()],
        approved_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    assert syllabus.approved_at is not None


def test_plan_requires_unique_source_links() -> None:
    with pytest.raises(ValidationError):
        _plan(
            source_links=[
                StudyPlanSourceLink(source_id="source:one"),
                StudyPlanSourceLink(source_id="source:one"),
            ]
        )


def test_approval_requires_the_exact_syllabus_and_source_manifest() -> None:
    with pytest.raises(ValidationError):
        _plan(
            state="approved",
            source_manifest_sha256=None,
            approved_syllabus_version=1,
        )

    with pytest.raises(ValidationError):
        _plan(state="approved", approved_syllabus_version=None)

    editing = _plan(state="editing", approved_syllabus_version=None)
    with pytest.raises(ValueError, match="approved syllabus version"):
        editing.transition("approved", expected_version=editing.version)


def test_transition_requires_the_expected_version_and_returns_a_new_revision() -> None:
    plan = _plan()

    with pytest.raises(ValueError, match="Expected plan version"):
        plan.transition("analyzing_sources", expected_version=plan.version + 1)

    next_plan = plan.transition("analyzing_sources", expected_version=plan.version)
    assert plan.state == "draft"
    assert next_plan.state == "analyzing_sources"
    assert next_plan.version == plan.version + 1
    assert next_plan.updated_at >= plan.updated_at


def test_transition_uses_only_the_allowlisted_lifecycle() -> None:
    plan = _plan()

    with pytest.raises(ValueError, match="not allowed"):
        plan.transition("approved", expected_version=plan.version)

    for next_state in (
        "analyzing_sources",
        "syllabus_proposed",
        "editing",
        "approved",
        "generating",
        "active",
        "completed",
    ):
        plan = plan.transition(next_state, expected_version=plan.version)

    with pytest.raises(ValueError, match="not allowed"):
        plan.transition("archived", expected_version=plan.version)
