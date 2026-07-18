"""Contract tests for server-owned interactive mind-map actions."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import studio as studio_router
from api.routers.studio import mind_maps


def _document(label: str = "Evidence <script>") -> dict:
    return {
        "schema_version": 1,
        "document": {
            "schema_version": 1,
            "artifact_type": "mind_map",
            "title": "Map",
            "root": {
                "label": label,
                "citations": ["[S1]"],
                "children": [
                    {
                        "label": "Scoped branch",
                        "relationship": "supports",
                        "citations": ["[S2]"],
                        "children": [],
                    }
                ],
            },
        },
    }


class _Artifact:
    records: dict[str, "_Artifact"] = {}
    saved: list["_Artifact"] = []

    def __init__(self, **kwargs):
        self.id = kwargs.pop("id", None)
        self.notebook_id = kwargs.pop("notebook_id")
        self.artifact_type = kwargs.pop("artifact_type")
        self.title = kwargs.pop("title")
        self.status = kwargs.pop("status", "completed")
        self.source_ids = kwargs.pop("source_ids", [])
        self.prompt = kwargs.pop("prompt", None)
        self.model_id = kwargs.pop("model_id", None)
        self.provider = kwargs.pop("provider", None)
        self.output_format = kwargs.pop("output_format", "markdown")
        self.output_payload = kwargs.pop("output_payload", {})
        self.citations = kwargs.pop("citations", [])
        self.export_paths = kwargs.pop("export_paths", {})
        self.revision_of_id = kwargs.pop("revision_of_id", None)
        self.created = self.updated = datetime(2026, 7, 17, tzinfo=timezone.utc)

    @classmethod
    async def get(cls, artifact_id: str):
        return cls.records[artifact_id]

    async def save(self):
        if self.id is None:
            self.id = f"studio_artifact:child-{len(self.saved) + 1}"
        self.records[str(self.id)] = self
        self.saved.append(self)


def _client(monkeypatch) -> TestClient:
    _Artifact.records = {
        "studio_artifact:map": _Artifact(
            id="studio_artifact:map",
            notebook_id="notebook:one",
            artifact_type="mind_map",
            title="Map",
            output_payload=_document(),
            citations=[
                {"marker": "[S1]", "source_id": "source:root"},
                {"marker": "[S2]", "source_id": "source:branch"},
                {"marker": "[S3]", "source_id": "source:unrelated"},
            ],
        )
    }
    _Artifact.saved = []
    monkeypatch.setattr(mind_maps, "StudioArtifact", _Artifact)
    monkeypatch.setattr(mind_maps, "_require_evidence_studio", lambda: None)
    monkeypatch.setattr(
        mind_maps, "_sync_artifact_generation_service_dependencies", lambda: None
    )
    monkeypatch.setattr(studio_router, "StudioArtifact", _Artifact)
    monkeypatch.setattr(studio_router, "_require_evidence_studio", lambda: None)

    async def generate(artifact_id: str):
        child = _Artifact.records[artifact_id]
        child.status = "completed"
        return child

    monkeypatch.setattr(
        mind_maps.artifact_generation_service,
        "generate_studio_artifact",
        AsyncMock(side_effect=generate),
    )
    app = FastAPI()
    app.include_router(studio_router.router, prefix="/api")
    return TestClient(app)


def test_branch_context_rebuilds_only_the_citation_resolved_source_subset(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/studio/artifacts/studio_artifact:map/mind-map/branches/0/0/context",
        json={"notebook_id": "notebook:one"},
    )

    assert response.status_code == 200
    assert response.json()["label"] == "Scoped branch"
    assert response.json()["source_ids"] == ["source:branch"]
    assert "source:unrelated" not in response.json()["prompt_context"]


def test_branch_context_rejects_other_notebook_and_stale_node(monkeypatch):
    client = _client(monkeypatch)

    ownership = client.post(
        "/api/studio/artifacts/studio_artifact:map/mind-map/branches/0/context",
        json={"notebook_id": "notebook:other"},
    )
    stale = client.post(
        "/api/studio/artifacts/studio_artifact:map/mind-map/branches/0/99/context",
        json={"notebook_id": "notebook:one"},
    )

    assert ownership.status_code == 404
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_mind_map_node"


def test_create_from_branch_uses_server_resolved_sources_and_svg_is_escaped(
    monkeypatch,
):
    client = _client(monkeypatch)

    create = client.post(
        "/api/studio/artifacts/studio_artifact:map/mind-map/branches/0/0/artifacts",
        json={"notebook_id": "notebook:one", "artifact_type": "study_guide"},
    )
    svg = client.get(
        "/api/studio/artifacts/studio_artifact:map/mind-map.svg?notebook_id=notebook:one"
    )

    assert create.status_code == 201
    child = _Artifact.saved[-1]
    assert child.source_ids == ["source:branch"]
    assert "source:unrelated" not in child.prompt
    assert svg.status_code == 200
    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert "&lt;script&gt;" in svg.text
    assert "<script>" not in svg.text
