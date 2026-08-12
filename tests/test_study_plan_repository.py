"""Unit contracts for additive Study Workbench plan persistence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deeper_notebook.study import plan_repository
from deeper_notebook.study.plan_repository import (
    StudyPlanRepository,
    StudyPlanRepositoryError,
)
from deeper_notebook.study.plans import (
    StudyPlan,
    StudyPlanPreferences,
    StudyPlanSourceLink,
    StudySyllabus,
    StudySyllabusUnit,
)

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
PLAN_RECORD = {
    "id": "study_plan:one",
    "schema_version": 1,
    "plan_id": "study_plan:one",
    "goal": "Understand mechanics",
    "starting_level": "beginner",
    "target_date": None,
    "preferences": {"weekly_minutes": 120, "session_minutes": 30},
    "source_links": [],
    "source_manifest_sha256": "a" * 64,
    "active_syllabus_version": None,
    "state": "draft",
    "revision": 1,
    "created_at": NOW,
    "updated_at": NOW,
    "private_source_body": "must not be projected",
}


def _plan(**updates: object) -> StudyPlan:
    values = {
        "plan_id": "study_plan:one",
        "goal": "Understand mechanics",
        "starting_level": "beginner",
        "preferences": StudyPlanPreferences(
            weekly_minutes=120,
            session_minutes=30,
        ),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(updates)
    return StudyPlan(**values)


def _syllabus(version: int = 1) -> StudySyllabus:
    return StudySyllabus(
        plan_id="study_plan:one",
        version=version,
        source_manifest_sha256="a" * 64,
        units=[
            StudySyllabusUnit(
                unit_id="foundations",
                title="Foundations",
                objectives=["Explain the core idea"],
                estimated_minutes=60,
                source_ids=["source:one"],
            )
        ],
    )


@pytest.mark.asyncio
async def test_approval_uses_expected_plan_and_syllabus_versions(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(sql, params):
        calls.append((sql, params))
        return [
            {
                **PLAN_RECORD,
                "state": "approved",
                "active_syllabus_version": 1,
                "revision": 3,
            }
        ]

    monkeypatch.setattr(plan_repository, "repo_query", query)

    result = await StudyPlanRepository().approve_syllabus(
        "study_plan:one",
        syllabus_version=1,
        expected_revision=2,
    )

    assert "revision = $expected_revision" in calls[0][0]
    assert "version = $version" in calls[0][0]
    assert calls[0][1]["expected_revision"] == 2
    assert calls[0][1]["version"] == 1
    assert result.state == "approved"
    assert result.version == 3
    assert result.approved_syllabus_version == 1


@pytest.mark.asyncio
async def test_list_caps_pagination_and_decodes_only_plan_projection(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(sql, params):
        calls.append((sql, params))
        return [PLAN_RECORD]

    monkeypatch.setattr(plan_repository, "repo_query", query)

    result = await StudyPlanRepository().list(limit=10_000, offset=4)

    assert calls[0][1] == {"limit": 500, "offset": 4}
    assert "LIMIT $limit" in calls[0][0]
    assert "START $offset" in calls[0][0]
    assert result[0].plan_id == "study_plan:one"
    assert not hasattr(result[0], "private_source_body")


@pytest.mark.asyncio
async def test_get_missing_record_is_safe_and_malformed_id_is_a_domain_error(monkeypatch):
    async def query(sql, params):
        return []

    monkeypatch.setattr(plan_repository, "repo_query", query)
    repository = StudyPlanRepository()

    assert await repository.get("study_plan:missing") is None

    with pytest.raises(StudyPlanRepositoryError, match="invalid study plan ID"):
        await repository.get("not a record id")


@pytest.mark.asyncio
async def test_add_source_uses_unique_link_and_never_mutates_source(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(sql, params):
        calls.append((sql, params))
        return [{"id": "study_plan_source:one", "plan_id": "study_plan:one", "source_id": "source:one"}]

    monkeypatch.setattr(plan_repository, "repo_query", query)

    link = await StudyPlanRepository().add_source("study_plan:one", "source:one")

    assert link.source_id == "source:one"
    assert "CREATE $link" in calls[0][0]
    assert "DELETE source" not in calls[0][0]
    assert "UPDATE source" not in calls[0][0]
    assert calls[0][1]["source_id"] == "source:one"
    assert calls[0][1]["link_data"]["source_id"] == "source:one"


@pytest.mark.asyncio
async def test_remove_source_only_deletes_owned_link(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(sql, params):
        calls.append((sql, params))
        return [{"id": "study_plan_source:one", "plan_id": "study_plan:one", "source_id": "source:one"}]

    monkeypatch.setattr(plan_repository, "repo_query", query)

    assert await StudyPlanRepository().remove_source("study_plan:one", "source:one") is True
    assert "DELETE study_plan_source" in calls[0][0]
    assert "DELETE source" not in calls[0][0]


@pytest.mark.asyncio
async def test_save_syllabus_writes_versioned_units_without_overwriting(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(sql, params):
        calls.append((sql, params))
        return [{"id": "study_syllabus:one", "plan_id": "study_plan:one", "version": 1}]

    monkeypatch.setattr(plan_repository, "repo_query", query)

    saved = await StudyPlanRepository().save_syllabus(_syllabus())

    assert saved.version == 1
    assert "CREATE $syllabus" in calls[0][0]
    assert "CREATE $unit_0" in calls[0][0]
    assert "UPDATE study_syllabus" not in calls[0][0]
    assert calls[0][1]["syllabus_data"]["version"] == 1
    assert calls[0][1]["unit_data_0"]["source_ids"] == ["source:one"]


@pytest.mark.asyncio
async def test_update_requires_exact_revision_and_returns_safe_conflict(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(sql, params):
        calls.append((sql, params))
        return []

    monkeypatch.setattr(plan_repository, "repo_query", query)

    with pytest.raises(StudyPlanRepositoryError, match="revision conflict"):
        await StudyPlanRepository().update(
            "study_plan:one",
            {"goal": "New goal"},
            expected_revision=2,
        )

    assert "revision = $expected_revision" in calls[0][0]
    assert calls[0][1]["expected_revision"] == 2


@pytest.mark.asyncio
async def test_create_projects_contract_and_source_links(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(sql, params):
        calls.append((sql, params))
        return PLAN_RECORD

    monkeypatch.setattr(plan_repository, "repo_query", query)

    plan = _plan(source_links=[StudyPlanSourceLink(source_id="source:one")])
    created = await StudyPlanRepository().create(plan)

    assert created.plan_id == "study_plan:one"
    assert calls[0][0].startswith("CREATE $plan")
    assert calls[0][1]["data"]["source_links"] == ["source:one"]
    assert "private_source_body" not in calls[0][1]["data"]
