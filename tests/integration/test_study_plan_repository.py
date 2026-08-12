"""Real-SurrealDB persistence contracts for Study Workbench plans."""

from __future__ import annotations

import pytest

from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.domain.notebook import StudioArtifact
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


def _manifestless_plan() -> StudyPlan:
    return StudyPlan(
        plan_id="study_plan:lifecycle",
        goal="Verify atomic syllabus lifecycle",
        starting_level="beginner",
        preferences=StudyPlanPreferences(weekly_minutes=120, session_minutes=30),
    )


def _manifest_syllabus(version: int, manifest: str) -> StudySyllabus:
    return StudySyllabus(
        plan_id="study_plan:lifecycle",
        version=version,
        source_manifest_sha256=manifest,
        units=[
            StudySyllabusUnit(
                unit_id=f"lifecycle-{version}",
                title=f"Lifecycle {version}",
                objectives=["Verify lifecycle binding"],
                estimated_minutes=30,
                source_ids=["source:lifecycle"],
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

    proposed = await repository.save_syllabus(
        _syllabus(1), expected_revision=2, lifecycle_action="propose"
    )
    assert proposed.version == 1
    proposed_plan = await repository.get(created.plan_id)
    assert proposed_plan is not None
    assert proposed_plan.state == "syllabus_proposed"
    assert proposed_plan.version == 3

    await repository.save_syllabus(
        _syllabus(2), expected_revision=3, lifecycle_action="edit"
    )
    editing_plan = await repository.get(created.plan_id)
    assert editing_plan is not None
    assert editing_plan.state == "editing"
    assert editing_plan.version == 4
    syllabus_rows = await repo_query(
        "SELECT plan_id, version FROM study_syllabus WHERE plan_id = $plan_id "
        "ORDER BY version ASC",
        {"plan_id": "study_plan:integration"},
    )
    assert [row["version"] for row in syllabus_rows] == [1, 2]

    approved = await repository.approve_syllabus(
        created.plan_id,
        syllabus_version=2,
        expected_revision=4,
    )
    assert approved.state == "approved"
    assert approved.approved_syllabus_version == 2
    assert approved.version == 5

    current = await repository.get(created.plan_id)
    assert current is not None
    assert current.state == "approved"
    assert current.approved_syllabus_version == 2
    assert current.source_manifest_sha256 == "a" * 64


async def test_plan_artifact_link_is_atomic_and_retry_idempotent(clean_namespace):
    repository = StudyPlanRepository()
    await repository.create(_plan())

    first = await repository.link_artifact(
        "study_plan:integration",
        "studio_artifact:quiz-one",
        artifact_kind="quiz",
        metadata={"unit_id": "foundations", "syllabus_version": 1},
    )
    retry = await repository.link_artifact(
        "study_plan:integration",
        "studio_artifact:quiz-one",
        artifact_kind="quiz",
        metadata={"unit_id": "foundations", "syllabus_version": 1},
    )
    found = await repository.find_artifact_link(
        "study_plan:integration",
        unit_id="foundations",
        artifact_kind="quiz",
        syllabus_version=1,
    )
    rows = await repo_query(
        "SELECT plan_id, artifact_id, artifact_kind, metadata "
        "FROM study_plan_artifact WHERE plan_id = $plan_id",
        {"plan_id": "study_plan:integration"},
    )

    assert first == retry
    assert found == first
    assert rows == [
        {
            "plan_id": "study_plan:integration",
            "artifact_id": "studio_artifact:quiz-one",
            "artifact_kind": "quiz",
            "metadata": {"unit_id": "foundations", "syllabus_version": 1},
        }
    ]


async def test_study_artifact_provisional_record_accepts_plan_owner_token(clean_namespace):
    await repo_query(
        "CREATE $source CONTENT $data RETURN AFTER;",
        {
            "source": ensure_record_id("source:artifact-owner"),
            "data": {"title": "Artifact evidence", "full_text": "Evidence"},
        },
    )
    artifact = StudioArtifact(
        notebook_id="notebook:study_integration",
        artifact_type="quiz",
        title="Foundations quiz",
        source_ids=["source:artifact-owner"],
    )
    await artifact.save()

    assert artifact.id is not None
    loaded = await StudioArtifact.get(artifact.id)
    assert loaded.notebook_id == "notebook:study_integration"
    assert loaded.source_ids == ["source:⟨artifact-owner⟩"]


async def test_manifestless_plan_lifecycle_binds_exact_syllabus_manifest_atomically(
    clean_namespace,
):
    repository = StudyPlanRepository()
    created = await repository.create(_manifestless_plan())
    assert created.source_manifest_sha256 is None

    await repo_query(
        "CREATE $source CONTENT $data RETURN AFTER;",
        {
            "source": ensure_record_id("source:lifecycle"),
            "data": {"title": "Lifecycle source", "full_text": "Initial evidence"},
        },
    )
    await repository.add_source(created.plan_id, "source:lifecycle", expected_revision=1)
    analyzing = await repository.get(created.plan_id)
    assert analyzing is not None
    assert analyzing.state == "analyzing_sources"
    assert analyzing.version == 2

    with pytest.raises(Exception, match="study syllabus|revision"):
        await repository.save_syllabus(
            _manifest_syllabus(99, "d" * 64),
            expected_revision=2,
            lifecycle_action="edit",
        )
    assert await repo_query(
        "SELECT id FROM study_syllabus WHERE plan_id = $plan_id",
        {"plan_id": created.plan_id},
    ) == []

    await repository.save_syllabus(
        _manifest_syllabus(1, "b" * 64),
        expected_revision=2,
        lifecycle_action="propose",
    )
    proposed = await repository.get(created.plan_id)
    assert proposed is not None
    assert proposed.state == "syllabus_proposed"
    assert proposed.version == 3

    with pytest.raises(Exception, match="study syllabus|revision"):
        await repository.approve_syllabus(
            created.plan_id, syllabus_version=1, expected_revision=3
        )
    still_proposed = await repository.get(created.plan_id)
    assert still_proposed == proposed
    assert (await repo_query(
        "SELECT approved_at FROM study_syllabus WHERE plan_id = $plan_id AND version = 1",
        {"plan_id": created.plan_id},
    ))[0].get("approved_at") is None

    await repository.save_syllabus(
        _manifest_syllabus(2, "c" * 64),
        expected_revision=3,
        lifecycle_action="edit",
    )
    editing = await repository.get(created.plan_id)
    assert editing is not None
    assert editing.state == "editing"
    assert editing.version == 4

    with pytest.raises(Exception, match="study syllabus|revision"):
        await repository.approve_syllabus(
            created.plan_id, syllabus_version=2, expected_revision=3
        )
    stale = await repository.get(created.plan_id)
    assert stale == editing
    assert (await repo_query(
        "SELECT approved_at FROM study_syllabus WHERE plan_id = $plan_id AND version = 2",
        {"plan_id": created.plan_id},
    ))[0].get("approved_at") is None

    approved = await repository.approve_syllabus(
        created.plan_id, syllabus_version=2, expected_revision=4
    )
    assert approved.state == "approved"
    assert approved.version == 5
    assert approved.approved_syllabus_version == 2
    assert approved.source_manifest_sha256 == "c" * 64


async def test_syllabus_read_projects_exact_or_latest_ordered_immutable_version(clean_namespace):
    repository = StudyPlanRepository()
    created = await repository.create(_plan())
    await repository.save_syllabus(_syllabus(1), expected_revision=created.version)
    await repository.save_syllabus(_syllabus(2), expected_revision=created.version)
    persisted_units = await repo_query(
        "SELECT plan_id, syllabus_version, unit_id, position FROM study_unit "
        "ORDER BY syllabus_version ASC, position ASC"
    )
    assert persisted_units == [
        {
            "plan_id": created.plan_id,
            "syllabus_version": 1,
            "unit_id": "foundations-1",
            "position": 0,
        },
        {
            "plan_id": created.plan_id,
            "syllabus_version": 2,
            "unit_id": "foundations-2",
            "position": 0,
        },
    ]
    exact_rows = await repo_query(
        "SELECT plan_id, syllabus_version, unit_id, position FROM study_unit "
        "WHERE type::string(plan_id) = $plan_id AND syllabus_version = $version "
        "ORDER BY position ASC LIMIT 64",
        {"plan_id": created.plan_id, "version": 1},
    )
    assert exact_rows == [persisted_units[0]]

    exact = await repository.get_syllabus(created.plan_id, version=1)
    latest = await repository.get_syllabus(created.plan_id)

    assert exact is not None
    assert exact.version == 1
    assert [unit.unit_id for unit in exact.units] == ["foundations-1"]
    assert latest is not None
    assert latest.version == 2
    assert [unit.unit_id for unit in latest.units] == ["foundations-2"]
    assert await repository.get_syllabus("study_plan:missing") is None


async def test_plan_source_removal_does_not_delete_source_record(clean_namespace):
    repository = StudyPlanRepository()
    await repository.create(_plan())
    source_id = ensure_record_id("source:owned-elsewhere")
    source_data = {
        "title": "Task-owned source",
        "full_text": "Immutable source body",
    }
    await repo_query(
        "CREATE $source CONTENT $data RETURN AFTER;",
        {"source": source_id, "data": source_data},
    )
    before = await repo_query(
        "SELECT id, title, full_text FROM source WHERE id = $source_id",
        {"source_id": source_id},
    )
    await repository.add_source("study_plan:integration", "source:owned-elsewhere", expected_revision=1)

    removed = await repository.remove_source(
        "study_plan:integration", "source:owned-elsewhere", expected_revision=2
    )
    assert removed is True

    source_rows = await repo_query(
        "SELECT id, title, full_text FROM source WHERE id = $source_id",
        {"source_id": source_id},
    )
    assert source_rows == before
    loaded = await repository.get("study_plan:integration")
    assert loaded is not None
    assert loaded.source_links == ()


async def test_guarded_approval_missing_or_stale_is_atomic(clean_namespace):
    repository = StudyPlanRepository()
    created = await repository.create(_plan())
    before = await repository.get(created.plan_id)
    assert before is not None

    with pytest.raises(Exception, match="study syllabus|revision"):
        await repository.approve_syllabus(
            created.plan_id, syllabus_version=99, expected_revision=1
        )
    after_missing = await repository.get(created.plan_id)
    assert after_missing == before
    assert await repo_query(
        "SELECT id FROM study_syllabus WHERE plan_id = $plan_id",
        {"plan_id": created.plan_id},
    ) == []

    await repository.add_source(created.plan_id, "source:guard", expected_revision=1)
    await repository.save_syllabus(
        _syllabus(1), expected_revision=2, lifecycle_action="propose"
    )
    with pytest.raises(Exception, match="study syllabus|revision"):
        await repository.approve_syllabus(
            created.plan_id, syllabus_version=1, expected_revision=99
        )
    still_pending = await repository.get(created.plan_id)
    assert still_pending is not None
    assert still_pending.version == 3
    assert still_pending.state == "syllabus_proposed"
    assert (await repo_query(
        "SELECT approved_at FROM study_syllabus WHERE plan_id = $plan_id AND version = 1",
        {"plan_id": created.plan_id},
    ))[0].get("approved_at") is None

    await repository.save_syllabus(
        _syllabus(2), expected_revision=3, lifecycle_action="edit"
    )
    approved = await repository.approve_syllabus(
        created.plan_id, syllabus_version=1, expected_revision=4
    )
    assert approved.approved_syllabus_version == 1
    with pytest.raises(Exception, match="study syllabus|revision"):
        await repository.approve_syllabus(
            created.plan_id, syllabus_version=2, expected_revision=3
        )
    unchanged = await repository.get(created.plan_id)
    assert unchanged is not None
    assert unchanged.approved_syllabus_version == 1
    assert unchanged.version == 5
    assert (await repo_query(
        "SELECT approved_at FROM study_syllabus WHERE plan_id = $plan_id AND version = 2",
        {"plan_id": created.plan_id},
    ))[0].get("approved_at") is None


async def test_guarded_link_and_syllabus_mutations_roll_back(clean_namespace):
    repository = StudyPlanRepository()
    created = await repository.create(_plan())

    with pytest.raises(Exception, match="study source|plan"):
        await repository.add_source(created.plan_id, "source:stale", expected_revision=99)
    assert await repo_query(
        "SELECT id FROM study_plan_source WHERE plan_id = $plan_id",
        {"plan_id": created.plan_id},
    ) == []

    with pytest.raises(Exception, match="study source|plan"):
        await repository.remove_source(created.plan_id, "source:stale", expected_revision=99)
    assert await repository.get(created.plan_id) == created

    with pytest.raises(Exception, match="study syllabus|plan"):
        await repository.save_syllabus(_syllabus(1), expected_revision=99)
    assert await repo_query(
        "SELECT id FROM study_syllabus WHERE plan_id = $plan_id",
        {"plan_id": created.plan_id},
    ) == []

    with pytest.raises(Exception, match="study source|plan"):
        await repository.add_source("study_plan:missing", "source:missing", expected_revision=1)
    assert await repo_query(
        "SELECT id FROM study_plan_source WHERE source_id = 'source:missing'",
    ) == []

    await repository.add_source(created.plan_id, "source:existing", expected_revision=1)
    with pytest.raises(Exception, match="study plan|source"):
        await repository.remove_source(
            "study_plan:missing", "source:existing", expected_revision=1
        )
    linked = await repository.get(created.plan_id)
    assert linked is not None
    assert [item.source_id for item in linked.source_links] == ["source:existing"]

    with pytest.raises(Exception, match="study syllabus|plan"):
        await repository.save_syllabus(
            _syllabus(2).model_copy(update={"plan_id": "study_plan:missing"}),
            expected_revision=1,
        )
    assert await repo_query(
        "SELECT id FROM study_syllabus WHERE plan_id = $plan_id",
        {"plan_id": "study_plan:missing"},
    ) == []


async def test_mapping_update_rejects_invalid_contract_without_db_change(clean_namespace):
    repository = StudyPlanRepository()
    created = await repository.create(_plan())
    for changes in (
        {"goal": " "},
        {"starting_level": ""},
        {"preferences": {"weekly_minutes": "bad", "session_minutes": 30}},
        {"target_date": "2026-99-99"},
    ):
        with pytest.raises(Exception, match="invalid study plan update"):
            await repository.update(created.plan_id, changes, expected_revision=1)
        assert await repository.get(created.plan_id) == created
