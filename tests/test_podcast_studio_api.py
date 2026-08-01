"""Read-only preview boundary for Podcast Intelligence Studio."""

from __future__ import annotations

from datetime import datetime, timezone
from time import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from deeper_notebook.knowledge_engine.capabilities import capabilities_for
from deeper_notebook.knowledge_engine.contracts import KnowledgeDocument
from deeper_notebook.local_models.contracts import LocalModelRouteCandidate


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

    async def get_current_block_content(
        self, *, document_id: str, block_id: str, source_revision_id: str
    ):
        assert (document_id, block_id, source_revision_id) == (
            "knowledge_engine_document:external",
            "knowledge_engine_block:research",
            "knowledge_engine_revision:one",
        )
        return type(
            "Block",
            (),
            {
                "block_id": block_id,
                "document_id": document_id,
                "source_revision_id": source_revision_id,
                "plain_text": "Selected research block stays server-side.",
            },
        )()


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
    app.state.local_model_route_candidates = (
        LocalModelRouteCandidate(
            model_id="local-podcast",
            provider="openai_compatible",
            fingerprint="b" * 64,
            modalities=("text",),
            accepted_roles=("podcast_outline", "podcast_script"),
            context_tokens=32_768,
            supports_structured_output=True,
            readiness="ready_verified",
            health_healthy=True,
            accepted_quality=0.9,
            benchmarked_at=time(),
            peak_memory_bytes=1,
            latency_ms=1,
        ),
        LocalModelRouteCandidate(
            model_id="local-voice",
            provider="piper",
            fingerprint="c" * 64,
            modalities=("audio",),
            accepted_roles=("text_to_speech",),
            context_tokens=1,
            supports_structured_output=False,
            readiness="ready_verified",
            health_healthy=True,
            accepted_quality=0.9,
            benchmarked_at=time(),
            peak_memory_bytes=1,
            latency_ms=1,
        ),
    )
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
async def test_preview_resolves_a_current_block_without_exposing_its_text(
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
                        "kind": "knowledge_block",
                        "document_id": "knowledge_engine_document:external",
                        "block_id": "knowledge_engine_block:research",
                        "expected_revision_id": "knowledge_engine_revision:one",
                    }
                ]
            },
        )

    assert response.status_code == 200
    assert response.json()["entries"][0]["stable_id"] == "knowledge_engine_block:research"
    assert response.json()["entries"][0]["state"] == "included"
    assert "Selected research block stays server-side." not in response.text


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
async def test_readiness_returns_redacted_local_stage_routes(
    app_with_knowledge_engine: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_knowledge_engine),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/podcasts/readiness",
            json={
                "selections": [
                    {"kind": "notebook", "notebook_id": "notebook:research"}
                ],
                "execution_policy": "strict_local",
                "compute_profile": "balanced",
                "include_transcription": False,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert [plan["role"] for plan in body["stage_plans"]] == [
        "podcast_outline",
        "podcast_script",
        "text_to_speech",
    ]
    assert "Private app-owned notebook material" not in response.text
    assert "/Users/" not in response.text


@pytest.mark.asyncio
async def test_readiness_fails_closed_when_required_local_stage_roles_are_missing(
    app_with_knowledge_engine: FastAPI,
) -> None:
    app_with_knowledge_engine.state.local_model_route_candidates = ()
    async with AsyncClient(
        transport=ASGITransport(app=app_with_knowledge_engine),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/podcasts/readiness",
            json={
                "selections": [{"kind": "notebook", "notebook_id": "notebook:research"}]
            },
        )

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["blocked_reasons"] == ["podcast_stage_route_blocked"]
    assert all(plan["outcome"] == "blocked" for plan in response.json()["stage_plans"])


@pytest.mark.asyncio
async def test_confirmed_submit_uses_server_resolved_content_once_per_idempotency_key(
    app_with_knowledge_engine: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.podcast_service import PodcastService

    calls: list[dict[str, object]] = []

    async def submit_generation_job(**kwargs) -> str:
        calls.append(kwargs)
        return "command:podcast-one"

    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)
    async with AsyncClient(
        transport=ASGITransport(app=app_with_knowledge_engine),
        base_url="http://test",
    ) as client:
        selection = {"kind": "notebook", "notebook_id": "notebook:research"}
        preview = await client.post(
            "/api/podcasts/selection/preview", json={"selections": [selection]}
        )
        payload = {
            "selections": [selection],
            "selection_fingerprint": preview.json()["selection_fingerprint"],
            "idempotency_key": "podcast-submit-1",
            "confirmed": True,
            "episode_profile": "Local Episode",
            "speaker_profile": "Local Voice",
            "episode_name": "Research synthesis",
            "mode": "deep_dive",
            "review_outline": True,
        }
        first = await client.post("/api/podcasts/studio/submit", json=payload)
        second = await client.post("/api/podcasts/studio/submit", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.json()["job_id"] == "command:podcast-one"
    assert len(calls) == 1
    assert calls[0]["content"] == "Private app-owned notebook material"
    assert "Private app-owned notebook material" not in first.text


@pytest.mark.asyncio
async def test_submit_rejects_a_stale_preview_fingerprint_before_worker_submission(
    app_with_knowledge_engine: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.podcast_service import PodcastService

    async def should_not_submit(**kwargs) -> str:
        raise AssertionError(f"unexpected submission: {kwargs}")

    monkeypatch.setattr(PodcastService, "submit_generation_job", should_not_submit)
    async with AsyncClient(
        transport=ASGITransport(app=app_with_knowledge_engine),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/podcasts/studio/submit",
            json={
                "selections": [
                    {"kind": "notebook", "notebook_id": "notebook:research"}
                ],
                "selection_fingerprint": "0" * 64,
                "idempotency_key": "podcast-submit-stale",
                "confirmed": True,
                "episode_profile": "Local Episode",
                "speaker_profile": "Local Voice",
                "episode_name": "Research synthesis",
            },
        )

    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "podcast_selection_changed"}}


@pytest.mark.asyncio
async def test_submit_rejects_reusing_an_idempotency_key_for_a_different_request(
    app_with_knowledge_engine: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.podcast_service import PodcastService

    async def submit_generation_job(**kwargs) -> str:
        return "command:podcast-conflict"

    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)
    async with AsyncClient(
        transport=ASGITransport(app=app_with_knowledge_engine),
        base_url="http://test",
    ) as client:
        selection = {"kind": "notebook", "notebook_id": "notebook:research"}
        preview = await client.post(
            "/api/podcasts/selection/preview", json={"selections": [selection]}
        )
        payload = {
            "selections": [selection],
            "selection_fingerprint": preview.json()["selection_fingerprint"],
            "idempotency_key": "podcast-submit-conflict",
            "confirmed": True,
            "episode_profile": "Local Episode",
            "speaker_profile": "Local Voice",
            "episode_name": "Research synthesis",
        }
        accepted = await client.post("/api/podcasts/studio/submit", json=payload)
        conflict = await client.post(
            "/api/podcasts/studio/submit",
            json={**payload, "episode_name": "Changed title"},
        )

    assert accepted.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": {"code": "podcast_idempotency_conflict"}}


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
            json={
                    "selections": [
                        {
                            "kind": "knowledge_collection",
                            "collection_kind": "folder",
                            "collection_id": "knowledge_bookmark_folder:unavailable",
                        }
                    ]
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "podcast_selection_unavailable"}}
