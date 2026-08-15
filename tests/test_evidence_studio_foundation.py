"""Evidence Studio foundation contract tests.

These tests intentionally cover the first implementation slice from the
competitive enhancement plan: feature flags plus a durable Studio artifact
record. They are kept DB-free where possible so the contract can stay fast
and focused.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

_REPO = Path(__file__).resolve().parent.parent
_MIG_DIR = _REPO / "deeper_notebook" / "database" / "migrations"


def test_plus_stable_feature_flags_default_on(monkeypatch):
    for name in (
        "DEEPER_NOTEBOOK_VISUAL_REFRESH",
        "DEEPER_NOTEBOOK_EVIDENCE_STUDIO",
        "DEEPER_NOTEBOOK_MODEL_FLEET",
        "DEEPER_NOTEBOOK_RESEARCH_RUNS",
    ):
        monkeypatch.delenv(name, raising=False)

    import deeper_notebook.feature_flags as feature_flags

    importlib.reload(feature_flags)

    assert feature_flags.onp_visual_refresh_enabled() is True
    assert feature_flags.evidence_studio_enabled() is True
    assert feature_flags.model_fleet_enabled() is True
    assert feature_flags.research_runs_enabled() is False


def test_evidence_studio_feature_flags_parse_truthy_and_falsey(monkeypatch):
    import deeper_notebook.feature_flags as feature_flags

    for name in (
        "DEEPER_NOTEBOOK_EVIDENCE_STUDIO",
        "DN_EVIDENCE_STUDIO",
        "DEEPER_NOTEBOOK_EVIDENCE_STUDIO",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEEPER_NOTEBOOK_EVIDENCE_STUDIO", "yes")
    assert feature_flags.evidence_studio_enabled() is True

    monkeypatch.setenv("DEEPER_NOTEBOOK_EVIDENCE_STUDIO", "0")
    assert feature_flags.evidence_studio_enabled() is False


def test_study_workbench_flag_defaults_on_and_accepts_explicit_rollback(monkeypatch):
    import deeper_notebook.feature_flags as feature_flags

    monkeypatch.delenv("DEEPER_NOTEBOOK_STUDY_WORKBENCH", raising=False)
    assert feature_flags.study_workbench_enabled() is True

    monkeypatch.setenv("DEEPER_NOTEBOOK_STUDY_WORKBENCH", "0")
    assert feature_flags.study_workbench_enabled() is False


def test_source_visual_flag_defaults_off_and_accepts_explicit_enable(monkeypatch):
    import deeper_notebook.feature_flags as flags

    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED", raising=False)
    assert flags.source_visuals_enabled() is False

    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED", "1")
    assert flags.source_visuals_enabled() is True

    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED", "0")
    assert flags.source_visuals_enabled() is False


def test_studio_artifact_domain_contract():
    from deeper_notebook.domain.notebook import StudioArtifact

    artifact = StudioArtifact(
        notebook_id="notebook:alpha",
        artifact_type="study_guide",
        title="Study guide",
        prompt="Create a study guide",
        model_id="model:local",
        provider="llamacpp",
        output_format="markdown",
    )

    assert StudioArtifact.table_name == "studio_artifact"
    assert artifact.status == "pending"
    assert artifact.source_ids == []
    assert artifact.output_payload == {}
    assert artifact.citations == []
    assert artifact.export_paths == {}

    with pytest.raises(ValidationError):
        StudioArtifact(
            notebook_id="notebook:alpha",
            artifact_type="unsupported",
            title="Bad artifact",
        )

    with pytest.raises(ValidationError):
        StudioArtifact(
            notebook_id="notebook:alpha",
            artifact_type="report",
            title="Bad status",
            status="lost",
        )


def test_studio_artifact_domain_accepts_course_pack_types():
    from deeper_notebook.domain.notebook import StudioArtifact

    for artifact_type in ("course_pack", "training_guide"):
        artifact = StudioArtifact(
            notebook_id="notebook:alpha",
            artifact_type=artifact_type,
            title="Course Pack",
            source_ids=["source:video", "source:pdf"],
        )

        data = artifact._prepare_save_data()

        assert artifact.artifact_type == artifact_type
        assert str(data["notebook_id"]) == "notebook:alpha"
        assert [str(source_id) for source_id in data["source_ids"]] == [
            "source:video",
            "source:pdf",
        ]


def test_studio_workflow_run_domain_contract():
    from deeper_notebook.domain.notebook import StudioWorkflowRun

    run = StudioWorkflowRun(
        artifact_id="studio_artifact:alpha",
        notebook_id="notebook:alpha",
        title="Report generation",
        source_ids=["source:one"],
        approval_required=True,
        steps=[{"id": "privacy_gate", "label": "Privacy gate", "status": "pending"}],
    )

    assert StudioWorkflowRun.table_name == "studio_workflow_run"
    assert run.status == "queued"
    assert run.source_ids == ["source:one"]
    assert run.steps[0]["id"] == "privacy_gate"
    assert run.command_id is None

    data = run._prepare_save_data()

    assert str(data["artifact_id"]) == "studio_artifact:alpha"
    assert str(data["notebook_id"]) == "notebook:alpha"
    assert [str(source_id) for source_id in data["source_ids"]] == ["source:one"]
    assert data["command_id"] is None

    queued = StudioWorkflowRun(
        artifact_id="studio_artifact:alpha",
        notebook_id="notebook:alpha",
        title="Queued report generation",
        command_id="command:studio_generate",
    )
    queued_data = queued._prepare_save_data()
    assert str(queued_data["command_id"]) == "command:studio_generate"

    with pytest.raises(ValidationError):
        StudioWorkflowRun(
            artifact_id="studio_artifact:alpha",
            notebook_id="notebook:alpha",
            title="Bad run",
            status="lost",
        )


def test_studio_artifact_prepare_save_preserves_nullable_revision():
    from deeper_notebook.domain.notebook import StudioArtifact

    artifact = StudioArtifact(
        notebook_id="notebook:alpha",
        artifact_type="report",
        title="Report",
        revision_of_id=None,
    )

    data = artifact._prepare_save_data()

    assert data["revision_of_id"] is None
    assert data["source_ids"] == []
    assert data["output_payload"] == {}


def test_studio_artifact_api_schemas_validate_known_types():
    from api.schemas.studio import (
        StudioArtifactCreate,
        StudioArtifactResponse,
        StudioArtifactUpdate,
        StudioWorkflowRunCreate,
        StudioWorkflowRunResponse,
    )

    create = StudioArtifactCreate(
        notebook_id="notebook:alpha",
        artifact_type="flashcards",
        title="Flashcards",
        source_ids=["source:one"],
    )
    assert create.artifact_type == "flashcards"
    assert create.source_ids == ["source:one"]

    update = StudioArtifactUpdate(status="completed", output_payload={"items": []})
    assert update.status == "completed"
    assert update.output_payload == {"items": []}

    response = StudioArtifactResponse(
        id="studio_artifact:one",
        notebook_id="notebook:alpha",
        artifact_type="report",
        title="Report",
        status="pending",
    )
    assert response.export_paths == {}

    with pytest.raises(ValidationError):
        StudioArtifactCreate(
            notebook_id="notebook:alpha",
            artifact_type="bad_kind",
            title="Nope",
        )

    run_create = StudioWorkflowRunCreate(
        title="Generate briefing",
        source_ids=["source:one"],
        approval_required=True,
    )
    assert run_create.approval_required is True

    run_response = StudioWorkflowRunResponse(
        id="studio_workflow_run:one",
        artifact_id="studio_artifact:one",
        notebook_id="notebook:alpha",
        title="Generate briefing",
        status="awaiting_approval",
    )
    assert run_response.steps == []

    with pytest.raises(ValidationError):
        StudioWorkflowRunResponse(
            id="studio_workflow_run:one",
            artifact_id="studio_artifact:one",
            notebook_id="notebook:alpha",
            title="Generate briefing",
            status="lost",
        )


def test_studio_artifact_migration_defines_all_schema_fields():
    migration = _MIG_DIR / "23.surrealql"
    assert migration.exists(), "add deeper_notebook/database/migrations/23.surrealql"
    sql = migration.read_text()

    assert "DEFINE TABLE IF NOT EXISTS studio_artifact SCHEMAFULL" in sql

    defined = set(
        re.findall(
            r"DEFINE\s+FIELD\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_]+)\s+ON(?:\s+TABLE)?\s+studio_artifact\b",
            sql,
            re.IGNORECASE,
        )
    )
    expected = {
        "notebook_id",
        "artifact_type",
        "title",
        "status",
        "source_ids",
        "prompt",
        "model_id",
        "provider",
        "output_format",
        "output_payload",
        "citations",
        "export_paths",
        "revision_of_id",
        "created",
        "updated",
    }
    assert expected <= defined


def test_studio_artifact_down_migration_removes_table():
    down = _MIG_DIR / "23_down.surrealql"
    assert down.exists(), "add deeper_notebook/database/migrations/23_down.surrealql"
    sql = down.read_text()
    assert re.search(
        r"REMOVE\s+TABLE\s+IF\s+EXISTS\s+studio_artifact",
        sql,
        re.IGNORECASE,
    )


def test_studio_workflow_run_migration_defines_run_history_table():
    migration = _MIG_DIR / "24.surrealql"
    assert migration.exists(), "add deeper_notebook/database/migrations/24.surrealql"
    sql = migration.read_text()

    assert "DEFINE TABLE IF NOT EXISTS studio_workflow_run SCHEMAFULL" in sql

    defined = set(
        re.findall(
            r"DEFINE\s+FIELD\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_]+)\s+ON(?:\s+TABLE)?\s+studio_workflow_run\b",
            sql,
            re.IGNORECASE,
        )
    )
    expected = {
        "artifact_id",
        "notebook_id",
        "title",
        "status",
        "source_ids",
        "approval_required",
        "steps",
        "command_id",
        "created",
        "updated",
    }
    assert expected <= defined

    down = _MIG_DIR / "24_down.surrealql"
    assert down.exists(), "add deeper_notebook/database/migrations/24_down.surrealql"
    assert re.search(
        r"REMOVE\s+TABLE\s+IF\s+EXISTS\s+studio_workflow_run",
        down.read_text(),
        re.IGNORECASE,
    )


def test_studio_artifact_domain_queries_separate_roots_from_revisions():
    src = (_REPO / "deeper_notebook" / "domain" / "notebook.py").read_text()

    get_for_notebook = src[src.index("async def get_for_notebook"): src.index("async def get_revisions")]
    assert "revision_of_id = NONE" in get_for_notebook
    assert "async def get_revisions" in src
    assert "WHERE revision_of_id = $artifact_id" in src


def test_studio_workflow_run_domain_queries_by_artifact():
    src = (_REPO / "deeper_notebook" / "domain" / "notebook.py").read_text()

    assert "async def get_for_artifact" in src
    get_for_artifact = src[src.index("async def get_for_artifact"): src.index("class ChatSession")]
    assert "FROM studio_workflow_run" in get_for_artifact
    assert "WHERE artifact_id = $artifact_id" in get_for_artifact


def test_studio_command_uses_service_not_router_import():
    command_src = (_REPO / "commands" / "studio_commands.py").read_text()
    service_src = (
        _REPO / "deeper_notebook" / "studio" / "artifact_generation.py"
    ).read_text()

    assert "api.routers.studio" not in command_src
    assert "api.routers.studio" not in service_src
    assert "deeper_notebook.studio.artifact_generation" in command_src
