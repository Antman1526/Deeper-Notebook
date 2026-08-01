"""Read-only preview boundary for Podcast Intelligence Studio."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from deeper_notebook.knowledge_engine.capabilities import capabilities_for
from deeper_notebook.knowledge_engine.contracts import KnowledgeDocument


def _document() -> KnowledgeDocument:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    return KnowledgeDocument(
        id="knowledge_engine_document:external",
        space_id="knowledge_engine_space:second_brain",
        source_native_id="vault_file:private",
        authority_kind="external_read_only",
        relative_locator="Research/Private.md",
        document_kind="note",
        title="Private research",
        normalized_body="This body is server-resolved only.",
        content_hash="a" * 64,
        source_revision_id="knowledge_engine_revision:one",
        provenance="obsidian",
        availability="available",
        parse_state="ready",
        capabilities=sorted(capabilities_for("external_read_only", "note")),
        created_at=now,
        observed_at=now,
        updated_at=now,
    )


class _Engine:
    async def get_document(self, document_id: str) -> KnowledgeDocument:
        assert document_id == "knowledge_engine_document:external"
        return _document()


class _Notebook:
    id = "notebook:research"
    name = "Research notebook"

    async def get_context(self) -> str:
        return "Private app-owned notebook material"


async def _load_notebook(notebook_id: str) -> _Notebook | None:
    assert notebook_id == "notebook:research"
    return _Notebook()


@pytest.fixture()
def app_with_knowledge_engine() -> FastAPI:
    from api.routers.podcasts import router

    app = FastAPI()
    app.state.knowledge_engine_service = _Engine()
    app.state.podcast_notebook_loader = _load_notebook
    app.include_router(router, prefix="/api")
    return app


@pytest.mark.asyncio
async def test_preview_resolves_a_read_only_document_without_exposing_body(
    app_with_knowledge_engine: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_knowledge_engine),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/podcasts/selection/preview",
            json={
                "selections": [
                    {
                        "kind": "knowledge_document",
                        "document_id": "knowledge_engine_document:external",
                        "expected_revision_id": "knowledge_engine_revision:one",
                    }
                ]
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["entries"][0]["authority_kind"] == "external_read_only"
    assert body["entries"][0]["state"] == "included"
    assert "normalized_body" not in response.text
    assert "This body is server-resolved only." not in response.text
    assert "source_native_id" not in response.text
    assert "/Users/" not in response.text


@pytest.mark.asyncio
async def test_preview_resolves_an_app_notebook_without_exposing_context(
    app_with_knowledge_engine: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_knowledge_engine),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/podcasts/selection/preview",
            json={
                "selections": [{"kind": "notebook", "notebook_id": "notebook:research"}]
            },
        )

    assert response.status_code == 200
    assert response.json()["entries"][0]["authority_kind"] == "app_owned"
    assert "Private app-owned notebook material" not in response.text


@pytest.mark.asyncio
async def test_preview_has_a_stable_no_engine_failure_without_source_details() -> None:
    from api.routers.podcasts import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/podcasts/selection/preview",
            json={
                "selections": [
                    {
                        "kind": "knowledge_document",
                        "document_id": "knowledge_engine_document:external",
                    }
                ]
            },
        )

    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "podcast_selection_unavailable"}}
    assert "/Users/" not in response.text


@pytest.mark.asyncio
async def test_preview_rejects_an_unavailable_selection_kind_without_side_effects(
    app_with_knowledge_engine: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_knowledge_engine),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/podcasts/selection/preview",
            json={"selections": [{"kind": "app_note", "note_id": "note:unavailable"}]},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "podcast_selection_unavailable"}}
