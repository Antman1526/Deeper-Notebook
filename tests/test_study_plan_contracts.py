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


def _activity(**overrides: object) -> StudyActivity:
    values: dict[str, object] = {
        "activity_id": "recall-quiz",
        "kind": "quiz",
        "title": "Recall quiz",
        "estimated_minutes": 20,
    }
    values.update(overrides)
    return StudyActivity(**values)


def _unit(unit_id: str = "foundations", **overrides: object) -> StudySyllabusUnit:
    values: dict[str, object] = {
        "unit_id": unit_id,
        "title": "Foundations",
        "objectives": ["Explain the core idea"],
        "estimated_minutes": 60,
        "activities": [_activity()],
    }
    values.update(overrides)
    return StudySyllabusUnit(**values)


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
        StudyPlan(
            plan_id="study_plan:one",
            goal="  ",
            starting_level="beginner",
        )

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


def test_collections_are_deeply_immutable_and_accept_normal_list_inputs() -> None:
    objectives = ["Explain the core idea"]
    prerequisites = ["prior-unit"]
    unit_source_ids = ["source:unit"]
    activity_source_ids = ["source:activity"]
    activities = [_activity(source_ids=activity_source_ids)]
    unit = _unit(
        objectives=objectives,
        prerequisite_unit_ids=prerequisites,
        source_ids=unit_source_ids,
        activities=activities,
    )
    units = [unit]
    syllabus = StudySyllabus(
        plan_id="study_plan:one",
        version=1,
        source_manifest_sha256="a" * 64,
        units=units,
    )
    source_links = [StudyPlanSourceLink(source_id="source:one")]
    plan = _plan(source_links=source_links)

    objectives.append("Mutated input")
    prerequisites.append("mutated-unit")
    unit_source_ids.append("source:mutated-unit")
    activity_source_ids.append("source:mutated-activity")
    activities.append(_activity(activity_id="second-activity"))
    units.append(_unit("second-unit"))
    source_links.append(StudyPlanSourceLink(source_id="source:two"))

    assert unit.objectives == ("Explain the core idea",)
    assert unit.prerequisite_unit_ids == ("prior-unit",)
    assert unit.source_ids == ("source:unit",)
    assert unit.activities[0].source_ids == ("source:activity",)
    assert syllabus.units == (unit,)
    assert plan.source_links == (StudyPlanSourceLink(source_id="source:one"),)

    with pytest.raises(AttributeError):
        unit.objectives.append("Bypass")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        unit.prerequisite_unit_ids.append("bypass")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        unit.source_ids.append("source:bypass")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        unit.activities[0].source_ids.append("source:bypass")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        unit.activities.append(_activity())  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        syllabus.units.append(_unit("bypass-unit"))  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        plan.source_links.append(StudyPlanSourceLink(source_id="source:bypass"))  # type: ignore[attr-defined]


def test_contracts_are_strict_and_bound_all_collection_string_elements() -> None:
    oversized = "x" * 1_000_000

    with pytest.raises(ValidationError):
        StudyPlanPreferences(weekly_minutes="240", session_minutes=45)  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        StudySyllabus(
            plan_id="study_plan:one",
            version="1",  # type: ignore[arg-type]
            source_manifest_sha256="a" * 64,
            units=[_unit()],
        )

    with pytest.raises(ValidationError):
        _unit(objectives=[oversized])

    with pytest.raises(ValidationError):
        _unit(prerequisite_unit_ids=["x" * 65])

    with pytest.raises(ValidationError):
        _unit(source_ids=[oversized])

    with pytest.raises(ValidationError):
        _activity(source_ids=[oversized])


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


def test_model_copy_cannot_bypass_lifecycle_or_approval_and_revalidates_updates() -> None:
    unbound_plan = _plan(
        source_manifest_sha256=None,
        approved_syllabus_version=None,
    )

    with pytest.raises(ValueError, match="transition"):
        unbound_plan.model_copy(
            update={
                "state": "approved",
                "version": 999,
                "source_manifest_sha256": "a" * 64,
                "approved_syllabus_version": 1,
            }
        )

    with pytest.raises(ValueError, match="transition"):
        unbound_plan.model_copy(update={"version": 2})

    updated_plan = _plan().model_copy(update={"goal": "A clearer goal"})
    assert updated_plan.goal == "A clearer goal"

    with pytest.raises(ValidationError, match="goal"):
        _plan().model_copy(update={"goal": " "})


def test_model_copy_revalidates_every_frozen_contract() -> None:
    activity = _activity()
    with pytest.raises(ValidationError, match="estimated_minutes"):
        activity.model_copy(update={"estimated_minutes": 0})
    copied_activity = activity.model_copy(update={"source_ids": ["source:two"]})
    assert copied_activity.source_ids == ("source:two",)

    preferences = StudyPlanPreferences(weekly_minutes=240, session_minutes=45)
    with pytest.raises(ValidationError, match="weekly_minutes"):
        preferences.model_copy(update={"weekly_minutes": 0})
    assert preferences.model_copy(update={"session_minutes": 30}).session_minutes == 30

    source_link = StudyPlanSourceLink(source_id="source:one")
    with pytest.raises(ValidationError, match="source_id"):
        source_link.model_copy(update={"source_id": ""})
    assert source_link.model_copy(update={"source_id": "source:two"}).source_id == "source:two"

    unit = _unit()
    with pytest.raises(ValidationError, match="objectives"):
        unit.model_copy(update={"objectives": []})
    copied_unit = unit.model_copy(update={"activities": [_activity()]})
    assert copied_unit.activities == (_activity(),)
    deep_copied_unit = unit.model_copy(deep=True)
    assert deep_copied_unit.activities[0] is not unit.activities[0]

    syllabus = StudySyllabus(
        plan_id="study_plan:one",
        version=1,
        source_manifest_sha256="a" * 64,
        units=[unit],
    )
    with pytest.raises(ValidationError, match="units"):
        syllabus.model_copy(update={"units": []})
    copied_syllabus = syllabus.model_copy(update={"units": [_unit("second-unit")]})
    assert copied_syllabus.units == (_unit("second-unit"),)


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


def test_plan_preferences_bind_explicit_remote_authority() -> None:
    with pytest.raises(ValueError, match="cloud model route requires network authority"):
        StudyPlanPreferences(
            weekly_minutes=120,
            session_minutes=30,
            model_route="cloud",
        )
    with pytest.raises(ValueError, match="supplied together"):
        StudyPlanPreferences(
            weekly_minutes=120,
            session_minutes=30,
            network_allowed=True,
        )
    preferences = StudyPlanPreferences(
        weekly_minutes=120,
        session_minutes=30,
        model_route="cloud",
        network_allowed=True,
        approved_network_scope=("https://research.example.edu",),
    )
    assert preferences.model_route == "cloud"
