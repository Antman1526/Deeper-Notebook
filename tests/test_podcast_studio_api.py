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

    async def list_documents(self, *, space_id, limit, offset):
        assert (space_id, limit, offset) == ("knowledge_engine_space:second_brain", 500, 0)
        return [_document()]


class _Navigation:
    async def get_bookmark(self, bookmark_id: str):
        assert bookmark_id == "knowledge_bookmark:research"
        return type(
            "Bookmark",
            (),
            {
                "target": type(
                    "DocumentTarget",
                    (),
                    {
                        "kind": "document",
                        "document_id": "knowledge_engine_document:external",
                    },
                )(),
            },
        )()

    async def list_folders(self):
        return [
            type(
                "Folder",
                (),
                {
                    "id": "knowledge_bookmark_folder:research",
                    "parent_folder_id": None,
                },
            )()
        ]

    async def list_bookmarks(self, filters, cursor, limit):
        assert filters.folder_id == "knowledge_bookmark_folder:research"
        assert cursor is None
        assert limit == 100
        return type(
            "BookmarkPage",
            (),
            {
                "items": [
                    type(
                        "Bookmark",
                        (),
                        {
                            "target": type(
                                "DocumentTarget",
                                (),
                                {
                                    "kind": "document",
                                    "document_id": "knowledge_engine_document:external",
                                },
                            )(),
                        },
                    )()
                ],
                "next_cursor": None,
            },
        )()

    async def get_workspace(self, workspace_id):
        assert workspace_id == "named_knowledge_workspace:research"
        return type(
            "Workspace",
            (),
            {
                "snapshot": type(
                    "Snapshot",
                    (),
                    {
                        "panes": {
                            "pane": type(
                                "Pane",
                                (),
                                {
                                    "tabs": [
                                        type(
                                            "Tab",
                                            (),
                                            {
                                                "target": type(
                                                    "DocumentTarget",
                                                    (),
                                                    {
                                                        "kind": "document",
                                                        "document_id": "knowledge_engine_document:external",
                                                    },
                                                )(),
                                            },
                                        )()
                                    ]
                                },
                            )()
                        }
                    },
                )()
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


class _Note:
    id = "note:research"
    title = "Research note"
    content = "Private app-owned note material"
    canonical_external = False


async def _load_note(note_id: str) -> _Note | None:
    assert note_id == "note:research"
    return _Note()


class _Insight:
    content = "Stored source insight"


class _Source:
    id = "source:research"
    title = "Research source"
    full_text = "Private app-owned source material"

    async def get_insights(self) -> list[_Insight]:
        return [_Insight()]


async def _load_source(source_id: str) -> _Source | None:
    assert source_id == "source:research"
    return _Source()


@pytest.fixture()
def app_with_knowledge_engine() -> FastAPI:
    from api.routers.podcasts import router

    app = FastAPI()
    app.state.knowledge_engine_service = _Engine()
    app.state.knowledge_navigation_service = _Navigation()
    app.state.podcast_notebook_loader = _load_notebook
    app.state.podcast_note_loader = _load_note
    app.state.podcast_source_loader = _load_source
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
            context_tokens=32_768,
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
async def test_preview_resolves_a_saved_bookmark_without_exposing_target_body(
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
                        "collection_kind": "bookmark",
                        "collection_id": "knowledge_bookmark:research",
                    }
                ]
            },
        )

    assert response.status_code == 200
    assert response.json()["entries"][0]["stable_id"] == "knowledge_engine_document:external"
    assert response.json()["entries"][0]["authority_kind"] == "external_read_only"
    assert "This body is server-resolved only." not in response.text


@pytest.mark.asyncio
async def test_preview_resolves_a_saved_folder_without_exposing_target_body(
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
                        "collection_id": "knowledge_bookmark_folder:research",
                    }
                ]
            },
        )

    assert response.status_code == 200
    assert response.json()["entries"][0]["stable_id"] == "knowledge_engine_document:external"
    assert "This body is server-resolved only." not in response.text


@pytest.mark.asyncio
async def test_preview_resolves_a_saved_workspace_without_exposing_target_body(
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
                        "collection_kind": "workspace",
                        "collection_id": "named_knowledge_workspace:research",
                    }
                ]
            },
        )

    assert response.status_code == 200
    assert response.json()["entries"][0]["stable_id"] == "knowledge_engine_document:external"
    assert "This body is server-resolved only." not in response.text


@pytest.mark.asyncio
async def test_preview_resolves_a_unified_text_search_without_exposing_body(
    app_with_knowledge_engine: FastAPI,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app_with_knowledge_engine), base_url="http://test") as client:
        response = await client.post("/api/podcasts/selection/preview", json={"selections": [{"kind": "saved_search", "query": "server-resolved", "search_mode": "text", "space_ids": ["knowledge_engine_space:second_brain"], "authority_kinds": ["external_read_only"]}]})

    assert response.status_code == 200
    assert response.json()["entries"][0]["stable_id"] == "knowledge_engine_document:external"
    assert "This body is server-resolved only." not in response.text


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
async def test_preview_resolves_an_app_note_without_exposing_content(
    app_with_knowledge_engine: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_knowledge_engine),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/podcasts/selection/preview",
            json={"selections": [{"kind": "app_note", "note_id": "note:research"}]},
        )

    assert response.status_code == 200
    assert response.json()["entries"][0]["authority_kind"] == "app_owned"
    assert "Private app-owned note material" not in response.text


@pytest.mark.asyncio
async def test_preview_resolves_source_insights_without_exposing_content(
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
                        "kind": "app_source",
                        "source_id": "source:research",
                        "inclusion_mode": "insights",
                    }
                ]
            },
        )

    assert response.status_code == 200
    assert response.json()["entries"][0]["authority_kind"] == "app_owned"
    assert "Stored source insight" not in response.text


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
async def test_studio_submit_persists_full_editorial_intent_and_validated_overrides(
    app_with_knowledge_engine: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.podcast_service import PodcastService

    app_with_knowledge_engine.state.local_model_route_candidates = (
        *app_with_knowledge_engine.state.local_model_route_candidates,
        LocalModelRouteCandidate(
            model_id="local-podcast-alt",
            provider="openai_compatible",
            fingerprint="d" * 64,
            modalities=("text",),
            accepted_roles=("podcast_outline", "podcast_script"),
            context_tokens=32_768,
            supports_structured_output=True,
            readiness="ready_verified",
            health_healthy=True,
            accepted_quality=0.95,
            benchmarked_at=time(),
            peak_memory_bytes=1,
            latency_ms=1,
        ),
        LocalModelRouteCandidate(
            model_id="local-voice-alt",
            provider="piper",
            fingerprint="e" * 64,
            modalities=("audio",),
            accepted_roles=("text_to_speech",),
            context_tokens=1,
            supports_structured_output=False,
            readiness="ready_verified",
            health_healthy=True,
            accepted_quality=0.95,
            benchmarked_at=time(),
            peak_memory_bytes=1,
            latency_ms=1,
        ),
        LocalModelRouteCandidate(
            model_id="local-stt-alt",
            provider="whisper",
            fingerprint="f" * 64,
            modalities=("audio",),
            accepted_roles=("speech_to_text",),
            context_tokens=32_768,
            supports_structured_output=False,
            readiness="ready_verified",
            health_healthy=True,
            accepted_quality=0.95,
            benchmarked_at=time(),
            peak_memory_bytes=1,
            latency_ms=1,
        ),
    )
    calls: list[dict[str, object]] = []

    async def submit_generation_job(**kwargs) -> str:
        calls.append(kwargs)
        return "command:podcast-full-intent"

    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)
    async with AsyncClient(
        transport=ASGITransport(app=app_with_knowledge_engine),
        base_url="http://test",
    ) as client:
        selection = {"kind": "notebook", "notebook_id": "notebook:research"}
        preview = await client.post(
            "/api/podcasts/selection/preview", json={"selections": [selection]}
        )
        editorial_brief = {
            "central_question": "What changed?",
            "audience": "expert",
            "purpose": "analyze",
            "format": "critique",
            "target_minutes": 42,
            "required_takeaway": "Use the new evidence threshold.",
            "include_unanswered_questions": True,
            "evidence_policy": "interpretation",
            "episode_profile_name": "Local Episode",
            "speaker_profile_name": "Local Voice",
            "outline": ["Context", "Finding", "Decision"],
        }
        production_overrides = {
            "podcast_outline": "local-podcast-alt",
            "podcast_script": "local-podcast-alt",
            "text_to_speech": "local-voice-alt",
            "speech_to_text": "local-stt-alt",
        }
        readiness = await client.post(
            "/api/podcasts/readiness",
            json={
                "selections": [selection],
                "include_transcription": True,
                "production_overrides": production_overrides,
            },
        )
        payload = {
            "selections": [selection],
            "selection_fingerprint": preview.json()["selection_fingerprint"],
            "idempotency_key": "podcast-full-intent-1",
            "confirmed": True,
            "episode_profile": "Local Episode",
            "speaker_profile": "Local Voice",
            "episode_name": "Research synthesis",
            "mode": "critique",
            "include_transcription": True,
            "production_overrides": production_overrides,
            "editorial_brief": editorial_brief,
        }
        response = await client.post("/api/podcasts/studio/submit", json=payload)

    assert readiness.status_code == 200
    assert readiness.json()["ready"] is True
    assert all(
        plan["selection_source"] == "production_override"
        for plan in readiness.json()["stage_plans"]
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["editorial_brief"] == editorial_brief
    assert calls[0]["model_plan_receipts"][-1]["selection_source"] == "production_override"


def test_readiness_rejects_unknown_or_path_production_overrides() -> None:
    from api.schemas.podcast_studio import PodcastReadinessRequest

    with pytest.raises(ValueError):
        PodcastReadinessRequest(
            selections=[{"kind": "notebook", "notebook_id": "notebook:research"}],
            production_overrides={"unknown_role": "model"},
        )
    with pytest.raises(ValueError):
        PodcastReadinessRequest(
            selections=[{"kind": "notebook", "notebook_id": "notebook:research"}],
            production_overrides={"podcast_outline": "/Users/Antman/model"},
        )


def test_submit_rejects_mismatched_editorial_top_level_values() -> None:
    from api.schemas.podcast_studio import PodcastStudioSubmitRequest

    with pytest.raises(ValueError, match="match submission mode"):
        PodcastStudioSubmitRequest(
            selections=[{"kind": "notebook", "notebook_id": "notebook:research"}],
            selection_fingerprint="a" * 64,
            idempotency_key="podcast-mismatch-1",
            confirmed=True,
            episode_profile="Local Episode",
            speaker_profile="Local Voice",
            episode_name="Research synthesis",
            mode="deep_dive",
            editorial_brief={
                "central_question": "What changed?",
                "audience": "expert",
                "purpose": "analyze",
                "format": "critique",
                "target_minutes": 30,
                "required_takeaway": "Use the finding.",
                "include_unanswered_questions": False,
                "evidence_policy": "strict",
                "episode_profile_name": "Local Episode",
                "speaker_profile_name": "Local Voice",
                "outline": ["Finding"],
            },
        )


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
            "editorial_brief": {
                "central_question": "What does the research change?",
                "audience": "Research team",
                "outline": ["Context", "Finding", "Implication"],
            },
        }
        first = await client.post("/api/podcasts/studio/submit", json=payload)
        second = await client.post("/api/podcasts/studio/submit", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.json()["job_id"] == "command:podcast-one"
    assert len(calls) == 1
    assert calls[0]["content"] == "Private app-owned notebook material"
    assert calls[0]["selection_fingerprint"] == preview.json()["selection_fingerprint"]
    assert calls[0]["selection_summary"] == {
        "authority_counts": {"app_owned": 1},
        "included_count": 1,
        "total_count": 1,
        "version": 1,
    }
    assert calls[0]["editorial_brief"] == payload["editorial_brief"]
    receipts = calls[0]["model_plan_receipts"]
    assert [receipt["role"] for receipt in receipts] == [
        "podcast_outline",
        "podcast_script",
        "text_to_speech",
    ]
    assert all(receipt["outcome"] == "ready" for receipt in receipts)
    assert all(receipt["version"] == 1 for receipt in receipts)
    assert all(
        set(receipt).issubset(
            {
                "outcome",
                "provider",
                "reason",
                "resource_tier",
                "role",
                "selection_source",
                "version",
            }
        )
        for receipt in receipts
    )
    for metadata_key in (
        "selection_summary",
        "editorial_brief",
        "model_plan_receipts",
    ):
        serialized = str(calls[0][metadata_key])
        assert "Private app-owned notebook material" not in serialized
        assert "relative_locator" not in serialized
        assert "model_id" not in serialized
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
async def test_preview_reports_a_missing_saved_folder_without_side_effects(
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

    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "podcast_selection_not_found"}}
