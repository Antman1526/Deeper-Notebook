"""Unit contracts for additive Study Workbench plan persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from deeper_notebook.study import plan_repository
from deeper_notebook.study.plan_repository import (
    StudyPlanConflictError,
    StudyPlanNotFoundError,
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
    assert "LET $plan_guard" in calls[0][0]
    assert "LET $syllabus_guard" in calls[0][0]
    assert "THROW" in calls[0][0]


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

    with pytest.raises(StudyPlanNotFoundError, match="invalid study plan ID"):
        await repository.get("not a record id")


@pytest.mark.asyncio
async def test_get_syllabus_projects_latest_or_exact_immutable_ordered_units(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []
    syllabus_record = {
        "id": "study_syllabus:one",
        "schema_version": 1,
        "plan_id": "study_plan:one",
        "version": 2,
        "source_manifest_sha256": "a" * 64,
        "approved_at": None,
        "private_source_body": "must not be projected",
    }
    unit_record = {
        "id": "study_unit:one",
        "schema_version": 1,
        "plan_id": "study_plan:one",
        "syllabus_version": 2,
        "unit_id": "motion",
        "position": 0,
        "title": "Motion",
        "objectives": ["Explain velocity"],
        "prerequisite_unit_ids": [],
        "estimated_minutes": 30,
        "source_ids": ["source:one"],
        "activities": [],
        "private_notes": "must not be projected",
    }

    async def query(sql, params):
        calls.append((sql, params))
        if "FROM study_syllabus" in sql:
            return [syllabus_record]
        return [unit_record]

    monkeypatch.setattr(plan_repository, "repo_query", query)
    repository = StudyPlanRepository()

    latest = await repository.get_syllabus("study_plan:one")
    exact = await repository.get_syllabus("study_plan:one", version=2)

    assert latest == exact
    assert latest is not None
    assert latest.version == 2
    assert latest.units[0].unit_id == "motion"
    assert not hasattr(latest, "private_source_body")
    assert "ORDER BY version DESC" in calls[0][0]
    assert "LIMIT 1" in calls[0][0]
    assert "ORDER BY position ASC" in calls[1][0]
    assert "LIMIT 64" in calls[1][0]
    assert calls[2][1]["version"] == 2


@pytest.mark.asyncio
async def test_get_syllabus_missing_or_invalid_plan_is_safe_and_non_disclosing(monkeypatch):
    async def query(sql, params):
        return []

    monkeypatch.setattr(plan_repository, "repo_query", query)
    repository = StudyPlanRepository()

    assert await repository.get_syllabus("study_plan:missing") is None
    with pytest.raises(StudyPlanNotFoundError, match="invalid study plan ID"):
        await repository.get_syllabus("not a record id")


@pytest.mark.asyncio
async def test_add_source_uses_unique_link_and_never_mutates_source(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(sql, params):
        calls.append((sql, params))
        return [{**PLAN_RECORD, "source_links": ["source:one"], "revision": 2}]

    monkeypatch.setattr(plan_repository, "repo_query", query)

    link = await StudyPlanRepository().add_source("study_plan:one", "source:one")

    assert link.source_id == "source:one"
    assert "CREATE $link" in calls[0][0]
    assert "DELETE source" not in calls[0][0]
    assert "UPDATE source" not in calls[0][0]
    assert calls[0][1]["source_id"] == "source:one"
    assert calls[0][1]["link_data"]["source_id"] == "source:one"
    assert "LET $plan_guard" in calls[0][0]
    assert "THROW" in calls[0][0]


@pytest.mark.asyncio
async def test_remove_source_only_deletes_owned_link(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []
    select_count = 0

    async def query(sql, params):
        nonlocal select_count
        calls.append((sql, params))
        if sql.startswith("SELECT"):
            select_count += 1
            links = ["source:one"] if select_count == 1 else []
            return {**PLAN_RECORD, "source_links": links}
        return [{"removed": True}]

    monkeypatch.setattr(plan_repository, "repo_query", query)

    assert await StudyPlanRepository().remove_source("study_plan:one", "source:one") is True
    transaction_sql = next(sql for sql, _ in calls if sql.startswith("BEGIN"))
    assert "DELETE study_plan_source" in transaction_sql
    assert "DELETE source" not in transaction_sql
    assert "LET $plan_guard" in transaction_sql
    assert "THROW" in transaction_sql


@pytest.mark.asyncio
async def test_save_syllabus_writes_versioned_units_without_overwriting(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(sql, params):
        calls.append((sql, params))
        if sql.startswith("SELECT"):
            return [{"id": "study_syllabus:one", "plan_id": "study_plan:one", "version": 1}]
        return [{"saved": True}]

    monkeypatch.setattr(plan_repository, "repo_query", query)

    saved = await StudyPlanRepository().save_syllabus(_syllabus(), expected_revision=1)

    assert saved.version == 1
    assert "CREATE $syllabus" in calls[0][0]
    assert "CREATE $unit_0" in calls[0][0]
    assert "UPDATE study_syllabus" not in calls[0][0]
    assert calls[0][1]["syllabus_data"]["version"] == 1
    assert calls[0][1]["unit_data_0"]["source_ids"] == ["source:one"]
    assert "LET $plan_guard" in calls[0][0]
    assert "THROW" in calls[0][0]


@pytest.mark.asyncio
async def test_update_requires_exact_revision_and_returns_safe_conflict(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(sql, params):
        calls.append((sql, params))
        return PLAN_RECORD if sql.startswith("SELECT") else []

    monkeypatch.setattr(plan_repository, "repo_query", query)

    with pytest.raises(StudyPlanConflictError, match="revision conflict"):
        await StudyPlanRepository().update(
            "study_plan:one",
            {"goal": "New goal"},
            expected_revision=2,
        )

    assert len(calls) == 2
    assert calls[1][0].startswith("UPDATE $plan")
    assert "revision = $expected_revision" in calls[1][0]
    assert calls[1][1]["expected_revision"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["add_source", "save_syllabus"])
async def test_driver_outages_are_not_misclassified_as_domain_conflicts(
    monkeypatch, operation
):
    async def query(sql, params):
        raise RuntimeError(f"database transport unavailable while executing query: {sql}")

    monkeypatch.setattr(plan_repository, "repo_query", query)
    repository = StudyPlanRepository()

    with pytest.raises(StudyPlanRepositoryError) as caught:
        if operation == "add_source":
            await repository.add_source(
                "study_plan:one", "source:one", expected_revision=1
            )
        else:
            await repository.save_syllabus(_syllabus(), expected_revision=1)

    assert not isinstance(caught.value, StudyPlanConflictError)


@pytest.mark.asyncio
async def test_repository_owned_transaction_guard_is_a_typed_conflict(monkeypatch):
    async def query(sql, params):
        raise RuntimeError("study_plan_guard_failed")

    monkeypatch.setattr(plan_repository, "repo_query", query)

    with pytest.raises(StudyPlanConflictError, match="revision conflict"):
        await StudyPlanRepository().add_source(
            "study_plan:one", "source:one", expected_revision=1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"goal": "   "},
        {"starting_level": "\t"},
        {"preferences": {"weekly_minutes": "not-an-int", "session_minutes": 30}},
        {"target_date": "not-a-date"},
    ],
)
async def test_update_revalidates_candidate_before_query(monkeypatch, changes):
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(sql, params):
        calls.append((sql, params))
        return [PLAN_RECORD]

    monkeypatch.setattr(plan_repository, "repo_query", query)

    with pytest.raises(StudyPlanRepositoryError, match="invalid study plan update"):
        await StudyPlanRepository().update(
            "study_plan:one", changes, expected_revision=1
        )
    assert all("UPDATE $plan" not in sql for sql, _ in calls)


@pytest.mark.asyncio
async def test_mutating_transactions_reject_zero_row_guards(monkeypatch):
    async def query(sql, params):
        # A guarded transaction must report the domain failure; this fake
        # emulates the driver returning no mutation result for a failed guard.
        return []

    monkeypatch.setattr(plan_repository, "repo_query", query)
    repository = StudyPlanRepository()

    with pytest.raises(StudyPlanRepositoryError):
        await repository.approve_syllabus(
            "study_plan:one", syllabus_version=9, expected_revision=1
        )
    with pytest.raises(StudyPlanRepositoryError):
        await repository.add_source("study_plan:one", "source:one", expected_revision=1)
    with pytest.raises(StudyPlanRepositoryError):
        await repository.remove_source(
            "study_plan:one", "source:one", expected_revision=1
        )
    with pytest.raises(StudyPlanRepositoryError):
        await repository.save_syllabus(_syllabus(), expected_revision=1)


def test_task3_migration_contracts_are_schemafull_and_tightly_bounded():
    migration = Path(__file__).parents[1] / "deeper_notebook/database/migrations/41.surrealql"
    sql = migration.read_text()
    assert "SCHEMAFULL" in sql
    assert "string::len($value) >= 1" in sql
    assert "string::len($value) <= 512" in sql
    assert 'string::matches($value, "^[0-9a-f]{64}$")' in sql
    assert "source_links ON TABLE study_plan TYPE array<string> ASSERT" in sql
    assert "prerequisite_unit_ids ON TABLE study_unit TYPE array<string> ASSERT" in sql
    assert "source_ids ON TABLE study_unit TYPE array<string> ASSERT" in sql
    assert "activities ON TABLE study_unit FLEXIBLE TYPE array<object> ASSERT" in sql
    assert "$value >= 5" in sql
    assert "$value <= 10080" in sql


def test_task3_migration_mirrors_strict_task2_text_and_id_contracts():
    migration = Path(__file__).parents[1] / "deeper_notebook/database/migrations/41.surrealql"
    sql = migration.read_text()
    nonblank = 'string::trim($value) != ""'
    stable_id = 'string::matches($value, "^[a-z0-9][a-z0-9_-]{0,63}$")'
    activity_kinds = (
        '$value IN ["reading", "lesson", "tutor_session", "quiz", "recall", '
        '"exam", "project", "review", "custom"]'
    )
    assert sql.count(nonblank) >= 8
    assert stable_id in sql
    assert 'string::matches($item, "^[a-z0-9][a-z0-9_-]{0,63}$")' in sql
    assert 'string::matches($activity.activity_id, "^[a-z0-9][a-z0-9_-]{0,63}$")' in sql
    assert '"reading", "lesson", "tutor_session", "quiz", "recall", "exam", "project", "review", "custom"' in sql
    assert "array::every($value, |$item| string::trim($item) != \"\" AND" in sql
    assert "array::every($value, |$item| string::matches($item" in sql
    assert "array::every($value, |$activity|" in sql
    assert "string::len($value) <= 32" not in sql


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
