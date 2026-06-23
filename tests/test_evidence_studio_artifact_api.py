"""Evidence Studio artifact API tests."""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import studio as studio_mod
from open_notebook.exceptions import NotFoundError


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(studio_mod.router, prefix="/api")
    return TestClient(app)


class _FakeArtifact:
    records: dict[str, "_FakeArtifact"] = {}
    deleted: list[str] = []
    saved_ids: list[str] = []

    def __init__(self, **kwargs):
        self.id = kwargs.pop("id", None)
        self.created = kwargs.pop("created", None)
        self.updated = kwargs.pop("updated", None)
        self.notebook_id = kwargs.pop("notebook_id")
        self.artifact_type = kwargs.pop("artifact_type")
        self.title = kwargs.pop("title")
        self.status = kwargs.pop("status", "pending")
        self.source_ids = kwargs.pop("source_ids", [])
        self.prompt = kwargs.pop("prompt", None)
        self.model_id = kwargs.pop("model_id", None)
        self.provider = kwargs.pop("provider", None)
        self.output_format = kwargs.pop("output_format", None)
        self.output_payload = kwargs.pop("output_payload", {})
        self.citations = kwargs.pop("citations", [])
        self.export_paths = kwargs.pop("export_paths", {})
        self.revision_of_id = kwargs.pop("revision_of_id", None)

    async def save(self):
        if not self.id:
            self.id = f"studio_artifact:{len(self.records) + 1}"
        now = datetime(2026, 6, 23, tzinfo=timezone.utc)
        self.created = self.created or now
        self.updated = now
        self.records[self.id] = self
        self.saved_ids.append(self.id)

    async def delete(self):
        self.deleted.append(self.id)
        self.records.pop(self.id, None)
        return True

    @classmethod
    async def get(cls, artifact_id: str):
        return cls.records[artifact_id]

    @classmethod
    async def get_for_notebook(cls, notebook_id: str):
        return [
            item
            for item in cls.records.values()
            if item.notebook_id == notebook_id
        ]

    @classmethod
    async def get_revisions(cls, artifact_id: str):
        return [
            item
            for item in cls.records.values()
            if item.revision_of_id == artifact_id
        ]


class _FakeWorkflowRun:
    records: dict[str, "_FakeWorkflowRun"] = {}
    saved_ids: list[str] = []

    def __init__(self, **kwargs):
        self.id = kwargs.pop("id", None)
        self.created = kwargs.pop("created", None)
        self.updated = kwargs.pop("updated", None)
        self.artifact_id = kwargs.pop("artifact_id")
        self.notebook_id = kwargs.pop("notebook_id")
        self.title = kwargs.pop("title")
        self.status = kwargs.pop("status", "queued")
        self.source_ids = kwargs.pop("source_ids", [])
        self.approval_required = kwargs.pop("approval_required", False)
        self.steps = kwargs.pop("steps", [])
        self.command_id = kwargs.pop("command_id", None)

    async def save(self):
        if not self.id:
            self.id = f"studio_workflow_run:{len(self.records) + 1}"
        now = datetime(2026, 6, 23, tzinfo=timezone.utc)
        self.created = self.created or now
        self.updated = now
        self.records[self.id] = self
        self.saved_ids.append(self.id)

    @classmethod
    async def get(cls, run_id: str):
        return cls.records[run_id]

    @classmethod
    async def get_for_artifact(cls, artifact_id: str):
        return [
            item
            for item in cls.records.values()
            if item.artifact_id == artifact_id
        ]


def _install_fake_artifacts(monkeypatch):
    _FakeArtifact.records = {}
    _FakeArtifact.deleted = []
    _FakeArtifact.saved_ids = []
    monkeypatch.setattr(studio_mod, "StudioArtifact", _FakeArtifact)
    monkeypatch.setattr(
        studio_mod,
        "repo_query",
        AsyncMock(return_value=[{"id": "notebook:alpha"}]),
    )

    class _NotebookMock:
        @classmethod
        async def get(cls, _notebook_id):
            return cls()

    monkeypatch.setattr(studio_mod, "Notebook", _NotebookMock)


def _install_fake_workflow_runs(monkeypatch):
    _FakeWorkflowRun.records = {}
    _FakeWorkflowRun.saved_ids = []
    monkeypatch.setattr(studio_mod, "StudioWorkflowRun", _FakeWorkflowRun)


def test_artifact_routes_are_hidden_when_feature_flag_disabled(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "0")

    response = _client().get("/api/studio/notebooks/notebook:alpha/artifacts")

    assert response.status_code == 404
    assert response.json()["detail"] == "Evidence Studio is not enabled"


def test_create_artifact_saves_and_returns_response(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)

    response = _client().post(
        "/api/studio/artifacts",
        json={
            "notebook_id": "notebook:alpha",
            "artifact_type": "study_guide",
            "title": "Study guide",
            "source_ids": ["source:one"],
            "prompt": "Make a guide",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "studio_artifact:1"
    assert body["notebook_id"] == "notebook:alpha"
    assert body["artifact_type"] == "study_guide"
    assert body["status"] == "pending"
    assert body["source_ids"] == ["source:one"]


def test_create_training_guide_artifact(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)

    response = _client().post(
        "/api/studio/artifacts",
        json={
            "notebook_id": "notebook:training",
            "artifact_type": "training_guide",
            "title": "User onboarding training",
            "source_ids": ["source:video", "source:pdf"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["artifact_type"] == "training_guide"
    assert body["title"] == "User onboarding training"
    assert body["source_ids"] == ["source:video", "source:pdf"]


def test_create_course_pack_artifact(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)

    response = _client().post(
        "/api/studio/artifacts",
        json={
            "notebook_id": "notebook:training",
            "artifact_type": "course_pack",
            "title": "Course Pack",
            "source_ids": ["source:video", "source:pdf", "source:link"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["artifact_type"] == "course_pack"
    assert body["title"] == "Course Pack"
    assert body["source_ids"] == ["source:video", "source:pdf", "source:link"]


def test_list_artifacts_for_notebook(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    _FakeArtifact.records = {
        "studio_artifact:1": _FakeArtifact(
            id="studio_artifact:1",
            notebook_id="notebook:alpha",
            artifact_type="report",
            title="Report",
        ),
        "studio_artifact:2": _FakeArtifact(
            id="studio_artifact:2",
            notebook_id="notebook:beta",
            artifact_type="quiz",
            title="Quiz",
        ),
    }

    response = _client().get("/api/studio/notebooks/notebook:alpha/artifacts")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == ["studio_artifact:1"]


def test_list_artifacts_for_missing_notebook_returns_404(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    studio_mod.repo_query.return_value = []

    response = _client().get("/api/studio/notebooks/notebook:gone/artifacts")

    assert response.status_code == 404
    assert response.json()["detail"] == "Notebook not found"


def test_list_artifacts_for_notebook_excludes_revision_snapshots(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    _FakeArtifact.records = {
        "studio_artifact:primary": _FakeArtifact(
            id="studio_artifact:primary",
            notebook_id="notebook:alpha",
            artifact_type="report",
            title="Report",
        ),
        "studio_artifact:revision": _FakeArtifact(
            id="studio_artifact:revision",
            notebook_id="notebook:alpha",
            artifact_type="report",
            title="Report revision",
            revision_of_id="studio_artifact:primary",
        ),
    }

    response = _client().get("/api/studio/notebooks/notebook:alpha/artifacts")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["studio_artifact:primary"]


def test_list_artifact_revisions(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    _FakeArtifact.records = {
        "studio_artifact:primary": _FakeArtifact(
            id="studio_artifact:primary",
            notebook_id="notebook:alpha",
            artifact_type="report",
            title="Report",
        ),
        "studio_artifact:revision": _FakeArtifact(
            id="studio_artifact:revision",
            notebook_id="notebook:alpha",
            artifact_type="report",
            title="Report revision",
            revision_of_id="studio_artifact:primary",
            output_payload={"content": "# Previous"},
        ),
        "studio_artifact:other": _FakeArtifact(
            id="studio_artifact:other",
            notebook_id="notebook:alpha",
            artifact_type="report",
            title="Other revision",
            revision_of_id="studio_artifact:other-primary",
        ),
    }

    response = _client().get("/api/studio/artifacts/studio_artifact:primary/revisions")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == ["studio_artifact:revision"]
    assert body[0]["revision_of_id"] == "studio_artifact:primary"


def test_create_workflow_run_for_artifact_requires_approval(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    _install_fake_workflow_runs(monkeypatch)
    _FakeArtifact.records = {
        "studio_artifact:1": _FakeArtifact(
            id="studio_artifact:1",
            notebook_id="notebook:alpha",
            artifact_type="report",
            title="Report",
            source_ids=["source:one"],
        ),
    }

    response = _client().post(
        "/api/studio/artifacts/studio_artifact:1/workflow-runs",
        json={
            "title": "Generate Report",
            "source_ids": ["source:one"],
            "approval_required": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "studio_workflow_run:1"
    assert body["artifact_id"] == "studio_artifact:1"
    assert body["notebook_id"] == "notebook:alpha"
    assert body["status"] == "awaiting_approval"
    assert body["approval_required"] is True
    assert body["steps"][0]["id"] == "context"
    assert body["steps"][1]["id"] == "privacy_gate"
    assert body["steps"][1]["status"] == "pending"


def test_list_workflow_runs_for_artifact(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    _install_fake_workflow_runs(monkeypatch)
    _FakeArtifact.records = {
        "studio_artifact:1": _FakeArtifact(
            id="studio_artifact:1",
            notebook_id="notebook:alpha",
            artifact_type="report",
            title="Report",
        ),
    }
    _FakeWorkflowRun.records = {
        "studio_workflow_run:1": _FakeWorkflowRun(
            id="studio_workflow_run:1",
            artifact_id="studio_artifact:1",
            notebook_id="notebook:alpha",
            title="Generate Report",
            status="queued",
        ),
    }

    response = _client().get("/api/studio/artifacts/studio_artifact:1/workflow-runs")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["studio_workflow_run:1"]


def test_approve_workflow_run_releases_privacy_gate(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    _install_fake_workflow_runs(monkeypatch)
    _FakeWorkflowRun.records = {
        "studio_workflow_run:1": _FakeWorkflowRun(
            id="studio_workflow_run:1",
            artifact_id="studio_artifact:1",
            notebook_id="notebook:alpha",
            title="Generate Report",
            status="awaiting_approval",
            approval_required=True,
            steps=[
                {"id": "context", "label": "Context built", "status": "completed"},
                {"id": "privacy_gate", "label": "Privacy gate", "status": "pending"},
            ],
        ),
    }

    response = _client().post("/api/studio/workflow-runs/studio_workflow_run:1/approve")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["approval_required"] is False
    assert body["steps"][1]["status"] == "completed"


def test_update_artifact_patches_only_supplied_fields(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    _FakeArtifact.records = {
        "studio_artifact:1": _FakeArtifact(
            id="studio_artifact:1",
            notebook_id="notebook:alpha",
            artifact_type="report",
            title="Draft",
            status="pending",
        )
    }

    response = _client().patch(
        "/api/studio/artifacts/studio_artifact:1",
        json={"title": "Final", "status": "completed"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Final"
    assert body["status"] == "completed"
    assert body["artifact_type"] == "report"


def test_delete_artifact_deletes_record(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    _FakeArtifact.records = {
        "studio_artifact:1": _FakeArtifact(
            id="studio_artifact:1",
            notebook_id="notebook:alpha",
            artifact_type="report",
            title="Report",
        )
    }

    response = _client().delete("/api/studio/artifacts/studio_artifact:1")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": "studio_artifact:1"}
    assert "studio_artifact:1" in _FakeArtifact.deleted


def test_generate_artifact_is_hidden_when_feature_flag_disabled(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "0")

    response = _client().post("/api/studio/artifacts/studio_artifact:1/generate")

    assert response.status_code == 404
    assert response.json()["detail"] == "Evidence Studio is not enabled"


def test_generate_artifact_uses_selected_sources_and_saves_markdown(monkeypatch, tmp_path):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    monkeypatch.setenv("OPEN_NOTEBOOK_ARTIFACT_EXPORT_DIR", str(tmp_path))
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:1",
        notebook_id="notebook:alpha",
        artifact_type="report",
        title="Report",
        source_ids=["source:one"],
        prompt="Make an executive report.",
    )
    _FakeArtifact.records = {artifact.id: artifact}

    class _SourceMock:
        @classmethod
        async def get(cls, source_id):
            assert source_id == "source:one"
            return SimpleNamespace(
                id="source:one",
                title="Source One",
                full_text="Important source text.",
            )

    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content="# Generated Report\n\nGrounded answer.")
    )
    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    response = _client().post("/api/studio/artifacts/studio_artifact:1/generate")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["output_format"] == "markdown"
    assert body["output_payload"]["content"].startswith("# Generated Report")
    assert body["export_paths"]["markdown"].endswith(".md")
    assert body["export_paths"]["json"].endswith(".json")
    markdown_export = tmp_path / body["export_paths"]["markdown"].split("/")[-1]
    json_export = tmp_path / body["export_paths"]["json"].split("/")[-1]
    assert markdown_export.exists()
    assert json_export.exists()
    assert "# Generated Report" in markdown_export.read_text()
    assert "Source One" in markdown_export.read_text()
    exported_metadata = json.loads(json_export.read_text())
    assert exported_metadata["export_paths"] == body["export_paths"]
    assert exported_metadata["citations"][0]["source_id"] == "source:one"
    assert exported_metadata["citations"][0]["marker"] == "[S1]"
    assert body["citations"] == [
        {
            "source_id": "source:one",
            "title": "Source One",
            "marker": "[S1]",
            "location": "Source [S1]",
            "preview": "Important source text.",
        }
    ]
    assert _FakeArtifact.records["studio_artifact:1"].status == "completed"
    assert fake_chain.ainvoke.await_count == 1
    messages = fake_chain.ainvoke.call_args.args[0]
    assert "executive report" in messages[0].content.lower()
    assert "Use source markers like [S1]" in messages[0].content
    assert "## Source [S1]: Source One" in messages[1].content
    assert "Source ID: source:one" in messages[1].content
    assert "Important source text" in messages[1].content


def test_generate_course_pack_saves_training_sidecar_exports(monkeypatch, tmp_path):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    monkeypatch.setenv("OPEN_NOTEBOOK_ARTIFACT_EXPORT_DIR", str(tmp_path))
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:course-pack",
        notebook_id="notebook:training",
        artifact_type="course_pack",
        title="Admin Course Pack",
        source_ids=["source:video", "source:pdf"],
    )
    _FakeArtifact.records = {artifact.id: artifact}

    class _SourceMock:
        @classmethod
        async def get(cls, source_id):
            return SimpleNamespace(
                id=source_id,
                title="Training Source",
                full_text="A transcript and reference reading for admins.",
            )

    generated_markdown = "\n".join([
        "# Course Pack",
        "",
        "## Audience",
        "Workspace admins. [S1]",
        "",
        "## Module 1: Local Model Orientation",
        "Duration: 20 minutes",
        "Learners map model roles to training tasks. [S1]",
        "",
        "### Learner handout",
        "- Compare source synthesis and study-fast roles. [S1]",
        "",
        "### Hands-on exercise",
        "- Select a model for course-pack generation. [S1]",
        "",
        "### Knowledge check",
        "Question: Which model role handles long-form synthesis?",
        "Answer: source_synthesis",
        "",
        "### Facilitator notes",
        "Open the local model settings page during the demo.",
        "",
        "## Final assessment",
        "- Build a source-grounded learner handout. [S2]",
    ])
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value=SimpleNamespace(content=generated_markdown))
    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    response = _client().post("/api/studio/artifacts/studio_artifact:course-pack/generate")

    assert response.status_code == 200
    body = response.json()
    assert body["artifact_type"] == "course_pack"
    assert body["export_paths"]["instructor_guide"].endswith("-instructor-guide.md")
    assert body["export_paths"]["learner_handout"].endswith("-learner-handout.md")
    assert body["export_paths"]["module_checklist"].endswith("-module-checklist.json")
    assert body["export_paths"]["assessment"].endswith("-assessment.md")
    assert body["export_paths"]["scorm_package"].endswith("-scorm.zip")
    assert body["export_paths"]["xapi_package"].endswith("-xapi.zip")
    assert body["output_payload"]["course_pack_modules"] == [
        {
            "title": "Module 1: Local Model Orientation",
            "summary": "Duration: 20 minutes",
            "has_facilitator_notes": True,
        }
    ]

    instructor_export = tmp_path / body["export_paths"]["instructor_guide"].split("/")[-1]
    learner_export = tmp_path / body["export_paths"]["learner_handout"].split("/")[-1]
    checklist_export = tmp_path / body["export_paths"]["module_checklist"].split("/")[-1]
    assessment_export = tmp_path / body["export_paths"]["assessment"].split("/")[-1]
    assert "Open the local model settings page" in instructor_export.read_text()
    assert "Open the local model settings page" not in learner_export.read_text()
    checklist = json.loads(checklist_export.read_text())
    assert checklist["modules"][0]["title"] == "Module 1: Local Model Orientation"
    assert checklist["modules"][0]["has_facilitator_notes"] is True
    assert "Build a source-grounded learner handout" in assessment_export.read_text()

    scorm_export = tmp_path / body["export_paths"]["scorm_package"].split("/")[-1]
    xapi_export = tmp_path / body["export_paths"]["xapi_package"].split("/")[-1]
    with zipfile.ZipFile(scorm_export) as package:
        assert set(package.namelist()) >= {
            "imsmanifest.xml",
            "index.html",
            "instructor-guide.md",
            "learner-handout.md",
            "module-checklist.json",
            "assessment.md",
        }
        assert "Admin Course Pack" in package.read("imsmanifest.xml").decode()
        assert "Course Pack" in package.read("index.html").decode()
    with zipfile.ZipFile(xapi_export) as package:
        assert set(package.namelist()) >= {
            "tincan.xml",
            "xapi-statements.json",
            "instructor-guide.md",
            "learner-handout.md",
            "module-checklist.json",
            "assessment.md",
        }
        statements = json.loads(package.read("xapi-statements.json").decode())
        assert statements["activity"]["id"].endswith("studio_artifact:course-pack")
        assert statements["modules"][0]["title"] == "Module 1: Local Model Orientation"


def test_generate_artifact_uses_role_routed_registered_model(monkeypatch, tmp_path):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    monkeypatch.setenv("OPEN_NOTEBOOK_MODEL_DIR", str(tmp_path))
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:1",
        notebook_id="notebook:alpha",
        artifact_type="report",
        title="Report",
        source_ids=["source:one"],
    )
    _FakeArtifact.records = {artifact.id: artifact}
    model = tmp_path / "GGUF" / "Qwen3-Coder-30B-A3B-Q4_K_M.gguf"
    model.parent.mkdir()
    model.write_bytes(b"x" * 4096)

    class _SourceMock:
        @classmethod
        async def get(cls, _source_id):
            return SimpleNamespace(
                id="source:one",
                title="Source One",
                full_text="Important source text.",
            )

    class _ModelMock:
        @classmethod
        async def get_models_by_type(cls, model_type):
            assert model_type == "language"
            return [
                SimpleNamespace(
                    id="model:qwen-coder",
                    name="Qwen3-Coder-30B-A3B-Q4_K_M",
                    provider="openai_compatible",
                )
            ]

    captured: list[dict] = []
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value=SimpleNamespace(content="# Report"))

    async def _fake_provision(content, model_id, default_type, **kwargs):
        captured.append({
            "content": content,
            "model_id": model_id,
            "default_type": default_type,
            "kwargs": kwargs,
        })
        return fake_chain

    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(studio_mod, "Model", _ModelMock)
    monkeypatch.setattr(studio_mod, "provision_langchain_model", _fake_provision)

    response = _client().post("/api/studio/artifacts/studio_artifact:1/generate")

    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == "model:qwen-coder"
    assert body["provider"] == "openai_compatible"
    assert captured[0]["model_id"] == "model:qwen-coder"
    assert captured[0]["default_type"] == "chat"


def test_generate_artifact_keeps_explicit_model_over_role_routing(monkeypatch, tmp_path):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    monkeypatch.setenv("OPEN_NOTEBOOK_MODEL_DIR", str(tmp_path))
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:manual",
        notebook_id="notebook:alpha",
        artifact_type="quiz",
        title="Quiz",
        source_ids=["source:one"],
        model_id="model:manual",
        provider="anthropic",
    )
    _FakeArtifact.records = {artifact.id: artifact}
    model = tmp_path / "GGUF" / "gemma-3-4b-it-Q4_K_M.gguf"
    model.parent.mkdir()
    model.write_bytes(b"x" * 4096)

    class _SourceMock:
        @classmethod
        async def get(cls, _source_id):
            return SimpleNamespace(
                id="source:one",
                title="Source One",
                full_text="Important source text.",
            )

    class _ModelMock:
        @classmethod
        async def get_models_by_type(cls, _model_type):
            return [
                SimpleNamespace(
                    id="model:gemma",
                    name="gemma-3-4b-it-Q4_K_M",
                    provider="openai_compatible",
                )
            ]

    captured: list[str | None] = []
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value=SimpleNamespace(content="# Quiz"))

    async def _fake_provision(_content, model_id, _default_type, **_kwargs):
        captured.append(model_id)
        return fake_chain

    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(studio_mod, "Model", _ModelMock)
    monkeypatch.setattr(studio_mod, "provision_langchain_model", _fake_provision)

    response = _client().post("/api/studio/artifacts/studio_artifact:manual/generate")

    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == "model:manual"
    assert body["provider"] == "anthropic"
    assert captured == ["model:manual"]


def test_generate_artifact_preserves_previous_output_as_revision(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:primary",
        notebook_id="notebook:alpha",
        artifact_type="report",
        title="Report",
        status="completed",
        source_ids=["source:one"],
        prompt="Keep it concise.",
        model_id="model:local",
        provider="llamacpp",
        output_format="markdown",
        output_payload={"content": "# Previous Report"},
        citations=[
            {
                "source_id": "source:old",
                "title": "Old Source",
                "preview": "Old excerpt.",
            }
        ],
        export_paths={"markdown": "/tmp/report.md"},
    )
    _FakeArtifact.records = {artifact.id: artifact}

    class _SourceMock:
        @classmethod
        async def get(cls, _source_id):
            return SimpleNamespace(
                id="source:one",
                title="Source One",
                full_text="New source text.",
            )

    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content="# New Report\n\nUpdated answer.")
    )
    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    response = _client().post("/api/studio/artifacts/studio_artifact:primary/generate")

    assert response.status_code == 200
    assert response.json()["output_payload"]["content"].startswith("# New Report")
    revisions = [
        row
        for row in _FakeArtifact.records.values()
        if row.revision_of_id == "studio_artifact:primary"
    ]
    assert len(revisions) == 1
    revision = revisions[0]
    assert revision.status == "completed"
    assert revision.title == "Report revision"
    assert revision.source_ids == ["source:one"]
    assert revision.prompt == "Keep it concise."
    assert revision.model_id == "model:local"
    assert revision.provider == "llamacpp"
    assert revision.output_format == "markdown"
    assert revision.output_payload == {"content": "# Previous Report"}
    assert revision.citations == [
        {
            "source_id": "source:old",
            "title": "Old Source",
            "preview": "Old excerpt.",
        }
    ]
    assert revision.export_paths == {"markdown": "/tmp/report.md"}


def test_generate_artifact_supports_first_text_artifact_types(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)

    class _SourceMock:
        @classmethod
        async def get(cls, _source_id):
            return SimpleNamespace(
                id="source:one",
                title="Source One",
                full_text="Important source text.",
            )

    monkeypatch.setattr(studio_mod, "Source", _SourceMock)

    for artifact_type, expected_instruction in [
        ("briefing", "short briefing"),
        ("faq", "source-grounded FAQ"),
        ("timeline", "chronological timeline"),
        ("course_pack", "instructor-ready Course Pack"),
        ("training_guide", "legacy alias for Course Pack"),
        ("flashcards", "flashcards"),
        ("quiz", "quiz"),
        ("data_table", "Data Table"),
    ]:
        artifact = _FakeArtifact(
            id=f"studio_artifact:{artifact_type}",
            notebook_id="notebook:alpha",
            artifact_type=artifact_type,
            title=artifact_type,
            source_ids=["source:one"],
        )
        _FakeArtifact.records = {artifact.id: artifact}

        fake_chain = MagicMock()
        fake_chain.ainvoke = AsyncMock(
            return_value=SimpleNamespace(content=f"# {artifact_type}")
        )
        monkeypatch.setattr(
            studio_mod,
            "provision_langchain_model",
            AsyncMock(return_value=fake_chain),
        )

        response = _client().post(f"/api/studio/artifacts/{artifact.id}/generate")

        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        messages = fake_chain.ainvoke.call_args.args[0]
        assert expected_instruction in messages[0].content


def test_generate_artifact_supports_mind_map_instruction(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:mind-map",
        notebook_id="notebook:alpha",
        artifact_type="mind_map",
        title="Mind map",
        source_ids=["source:one"],
    )
    _FakeArtifact.records = {artifact.id: artifact}

    class _SourceMock:
        @classmethod
        async def get(cls, _source_id):
            return SimpleNamespace(
                id="source:one",
                title="Source One",
                full_text="The project has source ingestion, citations, and local models.",
            )

    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=(
                "# Mind Map\n\n"
                "- Open Notebook Plus [S1]\n"
                "  - Source ingestion [S1]\n"
                "  - Citations [S1]\n"
                "  - Local models [S1]"
            )
        )
    )
    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    response = _client().post("/api/studio/artifacts/studio_artifact:mind-map/generate")

    assert response.status_code == 200
    body = response.json()
    assert body["artifact_type"] == "mind_map"
    assert body["output_payload"]["content"].startswith("# Mind Map")
    messages = fake_chain.ainvoke.call_args.args[0]
    assert "mind map" in messages[0].content.lower()
    assert "nested markdown outline" in messages[0].content.lower()
    assert "relationships" in messages[0].content.lower()


def test_generate_artifact_supports_visual_study_artifact_instructions(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)

    class _SourceMock:
        @classmethod
        async def get(cls, _source_id):
            return SimpleNamespace(
                id="source:one",
                title="Source One",
                full_text="Evidence Studio creates research outputs with citations.",
            )

    monkeypatch.setattr(studio_mod, "Source", _SourceMock)

    for artifact_type, expected_terms in [
        ("slide_deck", ("slide deck", "speaker notes", "slide")),
        ("infographic", ("infographic", "sections", "data callouts")),
    ]:
        artifact = _FakeArtifact(
            id=f"studio_artifact:{artifact_type}",
            notebook_id="notebook:alpha",
            artifact_type=artifact_type,
            title=artifact_type,
            source_ids=["source:one"],
        )
        _FakeArtifact.records = {artifact.id: artifact}

        fake_chain = MagicMock()
        fake_chain.ainvoke = AsyncMock(
            return_value=SimpleNamespace(content=f"# {artifact_type}")
        )
        monkeypatch.setattr(
            studio_mod,
            "provision_langchain_model",
            AsyncMock(return_value=fake_chain),
        )

        response = _client().post(f"/api/studio/artifacts/{artifact.id}/generate")

        assert response.status_code == 200
        assert response.json()["artifact_type"] == artifact_type
        messages = fake_chain.ainvoke.call_args.args[0]
        lower_prompt = messages[0].content.lower()
        for term in expected_terms:
            assert term in lower_prompt


def test_generate_artifact_supports_podcast_outline_instruction(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:podcast-outline",
        notebook_id="notebook:alpha",
        artifact_type="podcast_outline",
        title="Podcast outline",
        source_ids=["source:one"],
    )
    _FakeArtifact.records = {artifact.id: artifact}

    class _SourceMock:
        @classmethod
        async def get(cls, _source_id):
            return SimpleNamespace(
                id="source:one",
                title="Source One",
                full_text="Open Notebook Plus creates citation-backed research artifacts.",
            )

    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=(
                "# Podcast Outline\n\n"
                "## Cold open\n"
                "Introduce citation-backed research artifacts. [S1]"
            )
        )
    )
    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    response = _client().post("/api/studio/artifacts/studio_artifact:podcast-outline/generate")

    assert response.status_code == 200
    body = response.json()
    assert body["artifact_type"] == "podcast_outline"
    assert body["output_payload"]["content"].startswith("# Podcast Outline")
    messages = fake_chain.ainvoke.call_args.args[0]
    lower_prompt = messages[0].content.lower()
    assert "podcast outline" in lower_prompt
    assert "host segments" in lower_prompt
    assert "audio overview" in lower_prompt
    assert "citation markers" in lower_prompt


def test_generate_artifact_supports_research_run_instruction(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:research-run",
        notebook_id="notebook:alpha",
        artifact_type="research_run",
        title="Research run",
        source_ids=["source:one"],
    )
    _FakeArtifact.records = {artifact.id: artifact}

    class _SourceMock:
        @classmethod
        async def get(cls, _source_id):
            return SimpleNamespace(
                id="source:one",
                title="Source One",
                full_text="Open Notebook Plus needs competitive research synthesis.",
            )

    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=(
                "# Research Run\n\n"
                "## Research plan\n"
                "- Compare NotebookLM-style capabilities. [S1]"
            )
        )
    )
    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    response = _client().post("/api/studio/artifacts/studio_artifact:research-run/generate")

    assert response.status_code == 200
    body = response.json()
    assert body["artifact_type"] == "research_run"
    assert body["output_payload"]["content"].startswith("# Research Run")
    messages = fake_chain.ainvoke.call_args.args[0]
    lower_prompt = messages[0].content.lower()
    assert "research run" in lower_prompt
    assert "multi-step" in lower_prompt
    assert "hypotheses" in lower_prompt
    assert "follow-up questions" in lower_prompt
    assert "citation markers" in lower_prompt


def test_generate_research_run_persists_structured_stage_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    monkeypatch.setenv("OPEN_NOTEBOOK_ARTIFACT_EXPORT_DIR", str(tmp_path))
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:research-stages",
        notebook_id="notebook:alpha",
        artifact_type="research_run",
        title="Research run",
        source_ids=["source:one"],
    )
    _FakeArtifact.records = {artifact.id: artifact}

    class _SourceMock:
        @classmethod
        async def get(cls, _source_id):
            return SimpleNamespace(
                id="source:one",
                title="Source One",
                full_text="Open Notebook Plus can route local models and generate artifacts.",
            )

    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=(
                "# Research Run\n\n"
                "## Research objective\n"
                "Compare Open Notebook Plus with NotebookLM. [S1]\n\n"
                "## Working hypotheses\n"
                "- Local model routing is a differentiator. [S1]\n\n"
                "## Evidence-backed findings\n"
                "- Evidence Studio can generate study artifacts. [S1]\n\n"
                "## Follow-up questions\n"
                "- Which local model handles source synthesis best?"
            )
        )
    )
    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    response = _client().post("/api/studio/artifacts/studio_artifact:research-stages/generate")

    assert response.status_code == 200
    body = response.json()
    stages = body["output_payload"]["research_stages"]
    assert stages == [
        {
            "title": "Research objective",
            "items": ["Compare Open Notebook Plus with NotebookLM. [S1]"],
        },
        {
            "title": "Working hypotheses",
            "items": ["Local model routing is a differentiator. [S1]"],
        },
        {
            "title": "Evidence-backed findings",
            "items": ["Evidence Studio can generate study artifacts. [S1]"],
        },
        {
            "title": "Follow-up questions",
            "items": ["Which local model handles source synthesis best?"],
        },
    ]
    json_export = tmp_path / body["export_paths"]["json"].split("/")[-1]
    exported_metadata = json.loads(json_export.read_text())
    assert exported_metadata["output_payload"]["research_stages"] == stages


def test_generate_data_table_persists_rows_and_csv_export(monkeypatch, tmp_path):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    monkeypatch.setenv("OPEN_NOTEBOOK_ARTIFACT_EXPORT_DIR", str(tmp_path))
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:data-table",
        notebook_id="notebook:alpha",
        artifact_type="data_table",
        title="Data Table",
        source_ids=["source:one"],
    )
    _FakeArtifact.records = {artifact.id: artifact}

    class _SourceMock:
        @classmethod
        async def get(cls, _source_id):
            return SimpleNamespace(
                id="source:one",
                title="Source One",
                full_text="Open Notebook Plus supports local models and Evidence Studio.",
            )

    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=(
                "# Data Table\n\n"
                "| Topic | Evidence | Source | Confidence | Notes |\n"
                "|---|---|---|---|---|\n"
                "| Local models | Scans AI_Models and routes roles [S1] | Source One | High | User-owned runtime |\n"
                "| Evidence Studio | Generates citation-backed artifacts [S1] | Source One | High | Exportable |\n"
            )
        )
    )
    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    response = _client().post("/api/studio/artifacts/studio_artifact:data-table/generate")

    assert response.status_code == 200
    body = response.json()
    assert body["artifact_type"] == "data_table"
    assert body["export_paths"]["csv"].endswith("-data-table.csv")
    assert body["output_payload"]["data_table_rows"] == [
        {
            "Topic": "Local models",
            "Evidence": "Scans AI_Models and routes roles [S1]",
            "Source": "Source One",
            "Confidence": "High",
            "Notes": "User-owned runtime",
        },
        {
            "Topic": "Evidence Studio",
            "Evidence": "Generates citation-backed artifacts [S1]",
            "Source": "Source One",
            "Confidence": "High",
            "Notes": "Exportable",
        },
    ]
    csv_export = tmp_path / body["export_paths"]["csv"].split("/")[-1]
    assert csv_export.exists()
    assert "Topic,Evidence,Source,Confidence,Notes" in csv_export.read_text()
    json_export = tmp_path / body["export_paths"]["json"].split("/")[-1]
    exported_metadata = json.loads(json_export.read_text())
    assert exported_metadata["output_payload"]["data_table_rows"] == (
        body["output_payload"]["data_table_rows"]
    )
    messages = fake_chain.ainvoke.call_args.args[0]
    lower_prompt = messages[0].content.lower()
    assert "data table" in lower_prompt
    assert "markdown table" in lower_prompt
    assert "source marker" in lower_prompt


def test_generate_artifact_uses_all_notebook_sources_when_none_selected(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:2",
        notebook_id="notebook:alpha",
        artifact_type="study_guide",
        title="Guide",
        source_ids=[],
    )
    _FakeArtifact.records = {artifact.id: artifact}

    class _NotebookMock:
        @classmethod
        async def get(cls, notebook_id):
            assert notebook_id == "notebook:alpha"
            return cls()

        async def get_sources(self):
            return [
                SimpleNamespace(
                    id="source:a",
                    title="A",
                    full_text="Alpha text.",
                ),
                SimpleNamespace(
                    id="source:b",
                    title="B",
                    full_text="Beta text.",
                ),
            ]

    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value=SimpleNamespace(content="# Guide"))
    monkeypatch.setattr(studio_mod, "Notebook", _NotebookMock)
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    response = _client().post("/api/studio/artifacts/studio_artifact:2/generate")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["source_ids"] == ["source:a", "source:b"]
    assert "Alpha text" in fake_chain.ainvoke.call_args.args[0][1].content
    assert "Beta text" in fake_chain.ainvoke.call_args.args[0][1].content


def test_generate_artifact_returns_404_when_artifact_notebook_is_missing(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:missing-notebook",
        notebook_id="notebook:gone",
        artifact_type="study_guide",
        title="Guide",
        source_ids=[],
    )
    _FakeArtifact.records = {artifact.id: artifact}

    class _NotebookMock:
        @classmethod
        async def get(cls, _notebook_id):
            raise NotFoundError("notebook not found")

    monkeypatch.setattr(studio_mod, "Notebook", _NotebookMock)
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(),
    )

    response = _client().post(
        "/api/studio/artifacts/studio_artifact:missing-notebook/generate"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Notebook not found: notebook:gone"
    assert _FakeArtifact.records["studio_artifact:missing-notebook"].status == "failed"
    assert not studio_mod.provision_langchain_model.called


def test_generate_artifact_marks_failed_when_model_errors(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:3",
        notebook_id="notebook:alpha",
        artifact_type="report",
        title="Report",
        source_ids=["source:one"],
    )
    _FakeArtifact.records = {artifact.id: artifact}

    class _SourceMock:
        @classmethod
        async def get(cls, _source_id):
            return SimpleNamespace(
                id="source:one",
                title="Source One",
                full_text="Important source text.",
            )

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(studio_mod, "provision_langchain_model", _boom)

    response = _client().post("/api/studio/artifacts/studio_artifact:3/generate")

    assert response.status_code == 502
    assert response.json()["detail"] == "Artifact generation failed"
    assert _FakeArtifact.records["studio_artifact:3"].status == "failed"


def test_generate_artifact_marks_failed_when_model_returns_blank_output(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:blank",
        notebook_id="notebook:alpha",
        artifact_type="report",
        title="Report",
        source_ids=["source:one"],
    )
    _FakeArtifact.records = {artifact.id: artifact}

    class _SourceMock:
        @classmethod
        async def get(cls, _source_id):
            return SimpleNamespace(
                id="source:one",
                title="Source One",
                full_text="Important source text.",
            )

    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value=SimpleNamespace(content="   \n\t  "))
    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    response = _client().post("/api/studio/artifacts/studio_artifact:blank/generate")

    assert response.status_code == 502
    assert response.json()["detail"] == "Artifact generation failed"
    saved = _FakeArtifact.records["studio_artifact:blank"]
    assert saved.status == "failed"
    assert "empty" in saved.output_payload["error"].lower()
    assert saved.export_paths == {}


def test_generate_artifact_returns_404_when_selected_source_is_missing(monkeypatch):
    monkeypatch.setenv("ONP_EVIDENCE_STUDIO", "1")
    _install_fake_artifacts(monkeypatch)
    artifact = _FakeArtifact(
        id="studio_artifact:missing-source",
        notebook_id="notebook:alpha",
        artifact_type="report",
        title="Report",
        source_ids=["source:gone"],
    )
    _FakeArtifact.records = {artifact.id: artifact}

    class _SourceMock:
        @classmethod
        async def get(cls, _source_id):
            raise NotFoundError("source not found")

    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(),
    )

    response = _client().post("/api/studio/artifacts/studio_artifact:missing-source/generate")

    assert response.status_code == 404
    assert response.json()["detail"] == "Source not found: source:gone"
    assert _FakeArtifact.records["studio_artifact:missing-source"].status == "failed"
    assert not studio_mod.provision_langchain_model.called
